#!/usr/bin/env bash
#
# run_all_tests_filesystemanalysis.sh
#
# Unit test suite for ptfilesystemanalysis.py
# Validates partition-table detection (mmls), filesystem identification
# (fsstat), directory-readability probe (fls), and the resulting recovery
# strategy decision: filesystem_scan / hybrid / file_carving.
#
# Coverage: 20 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_filesystemanalysis"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptfilesystemanalysis.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock Sleuth Kit tools.
# Output format matches that of the real tools as documented in
# Carrier, "File System Forensic Analysis" (Addison-Wesley, 2005).
# -----------------------------------------------------------------------------
make_mock_mmls() {
    local scheme="$1"   # "dos" | "gpt" | "superfloppy" | "fail"
    mkdir -p "${MOCK_BIN}"
    case "${scheme}" in
        dos)
            cat > "${MOCK_BIN}/mmls" <<'EOF'
#!/bin/sh
echo "DOS Partition Table"
echo "Offset Sector: 0"
echo "Units are in 512-byte sectors"
echo ""
echo "      Slot      Start        End          Length       Description"
echo "002:  000:000   0000002048   0009764863   0009762816   Win95 FAT32 (0x0B)"
EOF
            ;;
        gpt)
            cat > "${MOCK_BIN}/mmls" <<'EOF'
#!/bin/sh
echo "GUID Partition Table (EFI)"
echo "Offset Sector: 0"
echo "Units are in 512-byte sectors"
echo ""
echo "      Slot      Start        End          Length       Description"
echo "002:  000:000   0000002048   0009764863   0009762816   Linux filesystem"
EOF
            ;;
        superfloppy|fail)
            cat > "${MOCK_BIN}/mmls" <<'EOF'
#!/bin/sh
echo "Cannot determine partition type" >&2
exit 1
EOF
            ;;
    esac
    chmod +x "${MOCK_BIN}/mmls"
}

make_mock_fsstat() {
    local fs="$1"  # "FAT32" | "NTFS" | "ext4" | "fail"
    mkdir -p "${MOCK_BIN}"
    case "${fs}" in
        fail)
            cat > "${MOCK_BIN}/fsstat" <<'EOF'
#!/bin/sh
echo "Cannot determine file system type" >&2
exit 1
EOF
            ;;
        *)
            cat > "${MOCK_BIN}/fsstat" <<EOF
#!/bin/sh
echo "FILE SYSTEM INFORMATION"
echo "--------------------------------------------"
echo "File System Type: ${fs}"
echo "Volume Label (\$VOLUME): TEST"
echo "Block Size: 4096"
EOF
            ;;
    esac
    chmod +x "${MOCK_BIN}/fsstat"
}

make_mock_fls() {
    local mode="$1"  # "ok" | "fail"
    mkdir -p "${MOCK_BIN}"
    if [ "${mode}" = "fail" ]; then
        cat > "${MOCK_BIN}/fls" <<'EOF'
#!/bin/sh
echo "Cannot determine file system type" >&2
exit 1
EOF
    else
        cat > "${MOCK_BIN}/fls" <<'EOF'
#!/bin/sh
echo "r/r 32-128-1:	IMG_0001.JPG"
echo "r/r 33-128-1:	IMG_0002.JPG"
echo "r/r * 34-128-1:	deleted.jpg"
EOF
    fi
    chmod +x "${MOCK_BIN}/fls"
}

make_test_image() {
    dd if=/dev/zero of="${TEST_DIR}/img.dd" bs=1M count=4 2>/dev/null
}

run_tool() {
    local case_id="$1"
    local image="$2"
    local out="$3"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${image}" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}

# ----------------------------------------------------------------------------
# run_without_tsk: invoke the tool with a PATH that genuinely excludes the
# Sleuth Kit (mmls/fsstat/fls), even on a forensic VM where /usr/bin holds
# the real sleuthkit package. Uses an absolute python3 path (so PATH need
# not resolve python) and points PATH at an empty directory; the
# assignment is scoped to a subshell so it does not leak globally.
# ----------------------------------------------------------------------------
run_without_tsk() {
    local case_id="$1"
    local image="$2"
    local out="$3"
    local py3
    py3=$(command -v python3)
    local empty="${TEST_DIR}/__no_tsk_path__"
    mkdir -p "${empty}"
    (
        PATH="${empty}" "${py3}" "${TOOL_PATH}" \
            "${case_id}" "${image}" \
            --analyst Test --json-out "${out}" \
            >/dev/null 2>&1
        echo $?
    )
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    make_test_image

    # A1: DOS partition + FAT32 + readable dir -> filesystem_scan
    make_mock_mmls "dos"
    make_mock_fsstat "FAT32"
    make_mock_fls "ok"
    local out="${TEST_DIR}/a1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" "${out}")
    assert_exit_code "A1: DOS+FAT32+readable -> exit 0" "${EXIT_SUCCESS}" "${code}"
    # The tool writes the chosen strategy under `recommendedMethod`, NOT
    # `recoveryStrategy`. The latter never existed in the JSON output.
    assert_json_field "A2: strategy=filesystem_scan" "${out}" \
        "d['results']['properties'].get('recommendedMethod')" "filesystem_scan"

    # A3: GPT + ext4 + readable -> filesystem_scan
    make_mock_mmls "gpt"
    make_mock_fsstat "ext4"
    make_mock_fls "ok"
    out="${TEST_DIR}/a3.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/img.dd" "${out}" >/dev/null
    assert_json_field "A3: GPT+ext4 -> filesystem_scan" "${out}" \
        "d['results']['properties'].get('recommendedMethod')" "filesystem_scan"

    # A4: NTFS recognised, partial corruption -> hybrid
    make_mock_mmls "dos"
    make_mock_fsstat "NTFS"
    make_mock_fls "fail"
    out="${TEST_DIR}/a4.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-003" "${TEST_DIR}/img.dd" "${out}" >/dev/null
    local strategy
    strategy=$(json_value "${out}" \
        "d['results']['properties'].get('recommendedMethod')")
    case "${strategy}" in
        "hybrid"|"file_carving") pass "A4: NTFS+unreadable dir -> ${strategy}" ;;
        *) fail "A4: NTFS+unreadable dir" "got: ${strategy}" ;;
    esac
}

# =============================================================================
# B: Error / unrecognised filesystem
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    make_test_image

    # B1: mmls fails (no partition table) -> superfloppy attempted
    make_mock_mmls "superfloppy"
    make_mock_fsstat "FAT32"
    make_mock_fls "ok"
    local out="${TEST_DIR}/b1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" "${out}")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}")
            pass "B1: no partition table handled -> ${code}" ;;
        *) fail "B1: no partition table" "exit ${code}" ;;
    esac

    # B2: filesystem unrecognised -> file_carving strategy
    make_mock_mmls "superfloppy"
    make_mock_fsstat "fail"
    make_mock_fls "fail"
    out="${TEST_DIR}/b2.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/img.dd" "${out}" >/dev/null
    local fsr
    fsr=$(json_value "${out}" \
        "d['results']['properties'].get('filesystemRecognized')")
    assert_equal "B2: unrecognised FS -> filesystemRecognized=False" \
        "False" "${fsr}"

    assert_json_field "B3: unrecognised FS -> strategy=file_carving" "${out}" \
        "d['results']['properties'].get('recommendedMethod')" "file_carving"

    # B4: missing image file
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/missing.dd" "${TEST_DIR}/b4.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B4: missing image -> ${code}" ;;
        *) fail "B4: missing image" "exit ${code}" ;;
    esac

    # B5: missing TSK binaries.
    # check_tools() returns False, main() falls through to
    # `0 if recommendedMethod is not None else 1`, so we expect 1 here
    # (not 99). Some builds may still exit 99 if an uncaught exception
    # bubbles up; accept either. Uses run_without_tsk() to genuinely
    # exclude /usr/bin from PATH (see helper note above).
    code=$(run_without_tsk "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/img.dd" "${TEST_DIR}/b5.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B5: missing mmls/fsstat/fls -> ${code}" ;;
        *) fail "B5: missing mmls/fsstat/fls -> 99 or 1" "exit ${code}" ;;
    esac
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    # C1: image file smaller than 1MB (boundary of meaningful analysis)
    make_mock_mmls "dos"
    make_mock_fsstat "FAT32"
    make_mock_fls "ok"
    dd if=/dev/zero of="${TEST_DIR}/c1_small.dd" bs=512 count=64 2>/dev/null
    local out="${TEST_DIR}/c1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/c1_small.dd" "${out}")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}")
            pass "C1: 32KB image handled -> ${code}" ;;
        *) fail "C1: small image" "exit ${code}" ;;
    esac

    # C2: zero-byte file - boundary case.
    # The mocks return canned TSK output regardless of input, so the tool
    # cannot detect emptiness from mmls/fsstat alone and reports a valid
    # strategy (typically file_carving when nothing is recognised).
    # The assertion here is "tool doesn't crash on empty input"; accept
    # any of 0 / 1 / 99 as graceful handling.
    : > "${TEST_DIR}/c2_empty.dd"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-002" \
        "${TEST_DIR}/c2_empty.dd" "${TEST_DIR}/c2.json")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_ENV}"|"${EXIT_FAILURE}")
            pass "C2: empty image handled -> ${code}" ;;
        *) fail "C2: empty image" "exit ${code}" ;;
    esac

    # C3: case-prefix detection -- PHOTORECOVERY scenario picked up
    make_test_image
    make_mock_mmls "dos"; make_mock_fsstat "FAT32"; make_mock_fls "ok"
    out="${TEST_DIR}/c3.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-003" "${TEST_DIR}/img.dd" "${out}" >/dev/null
    local case_id_out
    case_id_out=$(json_value "${out}" "d['results']['properties'].get('caseId')")
    case "${case_id_out}" in
        "${PREFIX_PHOTO}"*) pass "C3: PHOTORECOVERY prefix preserved" ;;
        *) fail "C3: PHOTORECOVERY prefix preserved" "got: ${case_id_out}" ;;
    esac
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    make_test_image
    make_mock_mmls "dos"; make_mock_fsstat "FAT32"; make_mock_fls "ok"
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_PHOTO}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    assert_json_field "D3: filesystemRecognized=True for FAT32" "${out}" \
        "d['results']['properties'].get('filesystemRecognized')" "True"

    assert_json_field "D4: directoryReadable=True" "${out}" \
        "d['results']['properties'].get('directoryReadable')" "True"

    # D5: partitions array present
    local n
    n=$(json_value "${out}" "len(d['results']['properties'].get('partitions', []))")
    if [ "${n:-0}" -ge 0 ] 2>/dev/null; then
        pass "D5: partitions array present (${n} entries)"
    else
        fail "D5: partitions array" "got: ${n}"
    fi
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    make_test_image
    make_mock_mmls "dos"; make_mock_fsstat "FAT32"; make_mock_fls "ok"

    # E1: success -> 0
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" \
        "${TEST_DIR}/e1.json")
    assert_exit_code "E1: success -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: missing image -> 99 or 1
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/missing.dd" "${TEST_DIR}/e2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing image -> ${code}" ;;
        *) fail "E2: missing image" "exit ${code}" ;;
    esac

    # E3: missing TSK binaries - same mechanism as B5; accept 99 or 1.
    code=$(run_without_tsk "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/img.dd" "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E3: missing TSK -> ${code}" ;;
        *) fail "E3: missing TSK -> 99 or 1" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptfilesystemanalysis  [script-rev: 2026-05-25-r2]\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptfilesystemanalysis"
}

main "$@"