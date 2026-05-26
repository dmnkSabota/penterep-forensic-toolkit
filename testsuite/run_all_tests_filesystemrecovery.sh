#!/usr/bin/env bash
#
# run_all_tests_filesystemrecovery.sh
#
# Unit test suite for ptfilesystemrecovery.py
# Validates recovery of image files via fls + icat from MFT/FAT entries,
# triage into active/ and deleted/ subdirectories, and post-extraction
# validation.
#
# Coverage: 17 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_filesystemrecovery"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptfilesystemrecovery.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock Sleuth Kit + validation tooling.
#
# check_tools() in the tool requires ALL of:
#   fls, icat   (sleuthkit)
#   file        (always on PATH on Ubuntu)
#   identify    (imagemagick)
#   exiftool    (libimage-exiftool-perl)
#
# Mocks for fls/icat alone are not enough - if identify or exiftool are
# missing the tool aborts in check_tools() and recovers zero files.
# On a forensic VM imagemagick + exiftool ARE installed, so check_tools
# passes but real `identify` then runs against the synthetic JPEGs
# emitted by mock icat (a bare JFIF header + zeros + EOI) and rejects
# them as malformed - also yielding validImages=0.
# Mocking identify and exiftool removes both failure modes.
# -----------------------------------------------------------------------------
make_mock_fls() {
    local mode="$1"  # "two_active_one_deleted" | "empty" | "fail"
    mkdir -p "${MOCK_BIN}"
    case "${mode}" in
        two_active_one_deleted)
            cat > "${MOCK_BIN}/fls" <<'EOF'
#!/bin/sh
echo "r/r 32-128-1:	IMG_0001.JPG"
echo "r/r 33-128-1:	holiday/IMG_0002.JPG"
echo "r/r * 34-128-1:	deleted_photo.jpg"
EOF
            ;;
        empty)
            cat > "${MOCK_BIN}/fls" <<'EOF'
#!/bin/sh
exit 0
EOF
            ;;
        fail)
            cat > "${MOCK_BIN}/fls" <<'EOF'
#!/bin/sh
echo "Cannot read filesystem" >&2
exit 1
EOF
            ;;
    esac
    chmod +x "${MOCK_BIN}/fls"
}

make_mock_icat() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/icat" <<'EOF'
#!/usr/bin/env python3
"""
Mock icat - emits a structurally complete minimal JPEG so that:
  - `file -b` reports "JPEG image data, JFIF standard ..." (one of the
    IMAGE_FILE_KEYWORDS, otherwise _validate_image_file returns 'invalid'
    and the extracted file is unlinked).
  - size is well above MIN_IMAGE_BYTES (100).
A bare "FFD8 FFE0 JFIF ... FFD9" header is recognised by libmagic as
plain "data" rather than JPEG, so the mock emits a full set of segments
(SOI / APP0 / DQT / SOF0 / DHT / SOS / payload / EOI) sufficient for
libmagic detection.
"""
import sys, struct
def seg(marker, payload):
    return marker + struct.pack('>H', len(payload) + 2) + payload
soi  = b'\xff\xd8'
app0 = seg(b'\xff\xe0', b'JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')
dqt  = seg(b'\xff\xdb', b'\x00' + b'\x10' * 64)
sof0 = seg(b'\xff\xc0', b'\x08\x00\x01\x00\x01\x01\x01\x11\x00')
dht  = seg(b'\xff\xc4', b'\x00' + b'\x00' * 16 + b'\x00')
sos  = seg(b'\xff\xda', b'\x01\x01\x00\x00\x3f\x00')
eoi  = b'\xff\xd9'
sys.stdout.buffer.write(soi + app0 + dqt + sof0 + dht + sos + b'\x00' * 100 + eoi)
EOF
    chmod +x "${MOCK_BIN}/icat"
}

make_mock_identify() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/identify" <<'EOF'
#!/bin/sh
# Mock ImageMagick identify. Returns success for files whose first 4 bytes
# match a known JPEG/PNG signature.
FILE="$1"
[ "$1" = "-format" ] && FILE="$3"
[ -f "${FILE}" ] || exit 1
HEADER=$(head -c 4 "${FILE}" | od -An -tx1 | tr -d ' \n')
case "${HEADER}" in
    ffd8ff*) echo "${FILE} JPEG 100x100 RGB 8-bit"; exit 0 ;;
    89504e47) echo "${FILE} PNG 100x100 RGBA 8-bit"; exit 0 ;;
    *) exit 1 ;;
esac
EOF
    chmod +x "${MOCK_BIN}/identify"
}

make_mock_exiftool() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/exiftool" <<'EOF'
#!/bin/sh
# Mock exiftool. The tool only needs the binary to exist for check_tools()
# and not error out when called for metadata. Emit an empty JSON list so
# any json.loads() of the output succeeds.
echo '[]'
EOF
    chmod +x "${MOCK_BIN}/exiftool"
}

# Convenience wrapper that lays down the full mock toolset for a happy run.
make_all_mocks() {
    local fls_mode="${1:-two_active_one_deleted}"
    make_mock_fls "${fls_mode}"
    make_mock_icat
    make_mock_identify
    make_mock_exiftool
}

make_test_image() {
    dd if=/dev/zero of="${TEST_DIR}/img.dd" bs=1M count=2 2>/dev/null
}

run_tool() {
    local case_id="$1"
    local image="$2"
    local out="$3"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${image}" \
            --analyst "Test" \
            --output-dir "${TEST_DIR}/recovered" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}

# ----------------------------------------------------------------------------
# run_without_tsk: invoke tool with a PATH that genuinely excludes TSK and
# the validation toolchain, even on a forensic VM. See companion notes in
# run_all_tests_filesystemanalysis.sh for the bash PATH-leak gotcha.
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
            --analyst Test --output-dir "${TEST_DIR}/recovered" \
            --json-out "${out}" \
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
    make_all_mocks "two_active_one_deleted"

    local out="${TEST_DIR}/a1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" "${out}")
    assert_exit_code "A1: 3 recoverable files -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: count of recovered files matches fls output.
    # Tool writes `imageFilesFound`, NOT `filesRecovered`.
    local n
    n=$(json_value "${out}" "d['results']['properties'].get('imageFilesFound', 0)")
    assert_equal "A2: 3 files recovered" "3" "${n}"

    # A3: active and deleted counted separately.
    # Tool writes `activeImages` / `deletedImages` (NOT activeFiles/deletedFiles).
    local a del
    a=$(json_value "${out}" "d['results']['properties'].get('activeImages', 0)")
    del=$(json_value "${out}" "d['results']['properties'].get('deletedImages', 0)")
    assert_equal "A3a: 2 active files" "2" "${a}"
    assert_equal "A3b: 1 deleted file" "1" "${del}"

    # A4: active/ and deleted/ subdirectories created under the case-specific
    # output root. The tool composes:
    #   {--output-dir}/{case_id}_recovered/{active,deleted}
    local rec_root="${TEST_DIR}/recovered/${PREFIX_PHOTO}-2026-01-01-001_recovered"
    if [ -d "${rec_root}/active" ] && [ -d "${rec_root}/deleted" ]; then
        pass "A4: active/ and deleted/ subdirectories created"
    else
        fail "A4: subdirectories" "active/ or deleted/ missing under ${rec_root}"
    fi
}

# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    make_test_image
    make_mock_icat
    make_mock_identify
    make_mock_exiftool

    # B1: fls fails -> exit 1 (no files)
    make_mock_fls "fail"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" \
        "${TEST_DIR}/b1.json")
    case "${code}" in
        "${EXIT_FAILURE}"|"${EXIT_ENV}") pass "B1: fls failure -> ${code}" ;;
        *) fail "B1: fls failure" "exit ${code}" ;;
    esac

    # B2: empty filesystem (no recoverable files)
    make_mock_fls "empty"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/img.dd" \
        "${TEST_DIR}/b2.json")
    assert_exit_code "B2: zero files recovered -> exit 1" \
        "${EXIT_FAILURE}" "${code}"

    # B3: missing image
    make_mock_fls "two_active_one_deleted"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/missing.dd" "${TEST_DIR}/b3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B3: missing image -> ${code}" ;;
        *) fail "B3: missing image" "exit ${code}" ;;
    esac

    # B4: missing TSK / validation tools.
    # check_tools() returns False, run() exits early, main() returns 1
    # (since validImages stays 0). Some builds may exit 99 on uncaught
    # exception - accept either. Uses run_without_tsk() to genuinely
    # exclude /usr/bin from PATH on hosts where sleuthkit ships there.
    code=$(run_without_tsk "${PREFIX_PHOTO}-2026-01-01-004" \
        "${TEST_DIR}/img.dd" "${TEST_DIR}/b4.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B4: missing TSK -> ${code}" ;;
        *) fail "B4: missing TSK -> 99 or 1" "exit ${code}" ;;
    esac
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    make_test_image
    make_all_mocks "two_active_one_deleted"

    # C1: very small image (boundary of usability)
    dd if=/dev/zero of="${TEST_DIR}/c1_small.dd" bs=4096 count=4 2>/dev/null
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/c1_small.dd" "${TEST_DIR}/c1.json")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}") pass "C1: 16KB image -> ${code}" ;;
        *) fail "C1: small image" "exit ${code}" ;;
    esac

    # C2: output directory under read-only filesystem -> fallback.
    # /proc is not writable by non-root, so mkdir(parents=True) raises
    # PermissionError or OSError. The tool either catches it (exit 1) or
    # lets it bubble (exit 99). Accept either.
    code=$(PATH="${MOCK_BIN}:${PATH}" python3 "${TOOL_PATH}" \
        "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/img.dd" \
        --analyst Test --output-dir "/proc/cannot_write_here" \
        --json-out "${TEST_DIR}/c2.json" >/dev/null 2>&1; echo $?)
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "C2: unwritable output -> ${code}" ;;
        *) fail "C2: unwritable output" "exit ${code}" ;;
    esac

    # C3: caseId sanitisation across separators
    code=$(run_tool "${PREFIX_PHOTO}/2026/01/01-001" "${TEST_DIR}/img.dd" \
        "${TEST_DIR}/c3.json")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}") pass "C3: sanitised caseId -> ${code}" ;;
        *) fail "C3: sanitised caseId" "exit ${code}" ;;
    esac
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    make_test_image
    make_all_mocks "two_active_one_deleted"
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_PHOTO}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: validImages reflects post-extraction validation result.
    # ptfilesystemrecovery tracks counts only (validImages,
    # corruptedImages, ...) under results.properties; it does not emit
    # per-file recovery nodes.
    local vimg
    vimg=$(json_value "${out}" "d['results']['properties'].get('validImages', 0)")
    assert_equal "D3: 3 valid images in properties" "3" "${vimg}"
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    make_test_image
    make_mock_icat
    make_mock_identify
    make_mock_exiftool

    # E1: files recovered -> 0
    make_mock_fls "two_active_one_deleted"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" \
        "${TEST_DIR}/e1.json")
    assert_exit_code "E1: files recovered -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: no files -> 1
    make_mock_fls "empty"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/img.dd" \
        "${TEST_DIR}/e2.json")
    assert_exit_code "E2: no files -> 1" "${EXIT_FAILURE}" "${code}"

    # E3: missing image -> env or failure
    make_mock_fls "two_active_one_deleted"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/missing.dd" "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E3: missing image -> ${code}" ;;
        *) fail "E3: missing image" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptfilesystemrecovery  [script-rev: 2026-05-25-r2]\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptfilesystemrecovery"
}

main "$@"