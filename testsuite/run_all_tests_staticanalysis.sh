#!/usr/bin/env bash
#
# run_all_tests_staticanalysis.sh
#
# Unit test suite for ptstaticanalysis.py
# Validates suspicious-file discovery (SUSPICIOUS_SCAN_PATHS x
# SUSPICIOUS_EXTENSIONS), file-type identification (file), printable
# string extraction (strings), and packer/obfuscation detection via
# PACKER_KEYWORDS and OBFUSCATION_KEYWORDS.
#
# Coverage: 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_staticanalysis"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptstaticanalysis.py"
MOCK_BIN="${TEST_DIR}/fake_bin"
FAKE_IMAGE="${TEST_DIR}/fake.dd"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock binaries
# -----------------------------------------------------------------------------
make_mock_mount() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/mount" <<'EOF'
#!/bin/sh
exit 0
EOF
    chmod +x "${MOCK_BIN}/mount"
}

make_mock_umount() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/umount" <<'EOF'
#!/bin/sh
exit 0
EOF
    chmod +x "${MOCK_BIN}/umount"
}

make_mock_file() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/file" <<'EOF'
#!/bin/sh
# Mock `file -b <path>` -- prints a plausible identification line.
FILE=""
for arg in "$@"; do
    case "$arg" in -*) ;; *) FILE="$arg" ;; esac
done
[ -f "$FILE" ] || { echo "$FILE: cannot open"; exit 1; }
case "$FILE" in
    *.exe) echo "PE32+ executable (console) x86-64, for MS Windows" ;;
    *.dll) echo "PE32+ executable (DLL) (console) x86-64" ;;
    *.ps1) echo "ASCII text, with CRLF line terminators" ;;
    *.elf|*.so) echo "ELF 64-bit LSB shared object, x86-64" ;;
    *)     echo "data" ;;
esac
EOF
    chmod +x "${MOCK_BIN}/file"
}

make_mock_strings() {
    mkdir -p "${MOCK_BIN}"
    # The fixtures contain plain ASCII, so `cat` is a faithful enough
    # approximation of `strings` for this suite. The tool reads back
    # the combined strings file in recommend_dynamic(), so whatever
    # bytes are in the fixture become the input to the packer /
    # obfuscation / low-strings heuristics.
    cat > "${MOCK_BIN}/strings" <<'EOF'
#!/bin/sh
FILE=""
for arg in "$@"; do
    case "$arg" in -*) ;; *) FILE="$arg" ;; esac
done
cat "$FILE" 2>/dev/null
EOF
    chmod +x "${MOCK_BIN}/strings"
}

make_all_mocks() {
    make_mock_mount
    make_mock_umount
    make_mock_file
    make_mock_strings
}

# -----------------------------------------------------------------------------
# Fixture helpers
# -----------------------------------------------------------------------------
ensure_fake_image() {
    : > "${FAKE_IMAGE}"
}

# Create a clean, empty mount directory for <case_id> at the location
# the tool will use: <mount_dir>/<case_id>. The tool calls
# mkdir(parents=True, exist_ok=True) on this path itself; pre-creating
# it lets us drop fixture files in advance, and the no-op mount mock
# leaves them in place.
setup_empty_mount_for() {
    local case_id="$1"
    local mount="${TEST_DIR}/${case_id}"
    rm -rf "${mount}"
    mkdir -p "${mount}"
    echo "${mount}"
}

# Populate a mount with the four canonical suspicious-path files plus
# one benign file under /Users/<u>/Downloads. The benign file is in a
# path that is NOT in SUSPICIOUS_SCAN_PATHS and has no executable bit,
# so the tool's two-pass find should never flag it.
populate_canonical_fixtures() {
    local mount="$1"
    mkdir -p "${mount}/Windows/Temp"
    mkdir -p "${mount}/Users/Public/AppData/Roaming"
    mkdir -p "${mount}/ProgramData"
    mkdir -p "${mount}/Users/victim/Downloads"

    printf 'MZ\x90\x00This program cannot be run in DOS mode\nuser32.dll kernel32.dll\nCreateProcess WriteFile' \
        > "${mount}/Windows/Temp/malware.exe"
    printf 'MZ\x90\x00binary content with printable ascii text segments here too\nGetProcAddress LoadLibrary' \
        > "${mount}/Users/Public/AppData/Roaming/dropper.exe"
    printf 'Write-Host hello world\nGet-Process | Where-Object Name -eq notepad\nStart-Process explorer' \
        > "${mount}/ProgramData/script.ps1"
    printf 'MZ\x90\x00another binary fragment with strings inside it\nVirtualAlloc CreateThread' \
        > "${mount}/Windows/Temp/library.dll"

    # Benign: extension matches but path is OUTSIDE the scan paths.
    printf 'MZ\x90\x00ordinary executable not in scan path' \
        > "${mount}/Users/victim/Downloads/legitimate.exe"
}

# Add a file whose printable contents trigger the packer branch.
# UPX is a member of PACKER_KEYWORDS; including "themida" too just
# verifies that any-of detection works.
inject_packer_strings() {
    local mount="$1"
    mkdir -p "${mount}/Windows/Temp"
    printf 'UPX!compressed payload here\nthemida-protected segment\nMPRESS markers too' \
        > "${mount}/Windows/Temp/packed.exe"
}

# Add a file whose printable contents trigger the obfuscation branch.
# Requires >=50 long lines so the low_strings branch does not fire
# first, and zero packer keywords so the packer branch does not fire.
inject_obfuscation_strings() {
    local mount="$1"
    mkdir -p "${mount}/Windows/Temp"
    python3 - "${mount}" <<'PYEOF'
import sys
mount = sys.argv[1]
lines = []
# 80 long-but-mundane lines to clear the low_strings >= 50 threshold.
for i in range(80):
    lines.append(f"padding_line_{i:03d}_with_enough_chars_to_exceed_eight_each")
# Obfuscation keywords that are typically members of
# OBFUSCATION_KEYWORDS (base64 / eval / xor are common picks).
lines.append("base64_decode of suspicious blob")
lines.append("eval(unescape(payload_string))")
lines.append("xor decoded command sequence")
with open(f"{mount}/Windows/Temp/obfuscated.exe", "w") as fh:
    fh.write("\n".join(lines))
PYEOF
}

# -----------------------------------------------------------------------------
# run_tool <case_id> <image> <json_out>
#
# Invokes the tool with mocks on PATH. --dry-run is NOT passed -- see
# header for why. `-m ${TEST_DIR}` makes the tool's mount_dir resolve
# to ${TEST_DIR}/<case_id>, which the caller has already populated.
# -----------------------------------------------------------------------------
run_tool() {
    local case_id="$1"
    local image="$2"
    local out="$3"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${image}" \
            -m "${TEST_DIR}" \
            -o "${TEST_DIR}/out" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    make_all_mocks
    ensure_fake_image

    local case_id="${PREFIX_MALWARE}-2026-01-01-A01"
    local mount
    mount=$(setup_empty_mount_for "${case_id}")
    populate_canonical_fixtures "${mount}"

    local out="${TEST_DIR}/a.json"
    local code
    code=$(run_tool "${case_id}" "${FAKE_IMAGE}" "${out}")
    assert_exit_code "A1: suspicious files found -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: count is on properties.totalFilesAnalyzed; suspiciousFiles
    # is the corresponding list.
    local found
    found=$(json_value "${out}" \
        "d['results']['properties'].get('totalFilesAnalyzed', 0)")
    if [ "${found:-0}" -ge 3 ] 2>/dev/null; then
        pass "A2: ${found} suspicious files (>=3 expected)"
    else
        fail "A2: suspicious files found" "totalFilesAnalyzed=${found}"
    fi

    # A3: nothing under /Users/<u>/Downloads should appear in the list.
    local benign_flagged
    benign_flagged=$(json_value "${out}" "
sum(1 for f in d['results']['properties'].get('suspiciousFiles', [])
    if 'Downloads' in f.get('path', ''))")
    assert_equal "A3: file outside SUSPICIOUS_SCAN_PATHS not flagged" \
        "0" "${benign_flagged}"

    # A4: each suspicious-file entry has a non-empty `type` (NOT
    # `fileType`) populated by the mocked `file -b`.
    local has_type
    has_type=$(json_value "${out}" "
sum(1 for f in d['results']['properties'].get('suspiciousFiles', [])
    if f.get('type', '').strip())")
    if [ "${has_type:-0}" -ge 3 ] 2>/dev/null; then
        pass "A4: type populated for ${has_type} entries"
    else
        fail "A4: type populated" "got: ${has_type}"
    fi
}

# =============================================================================
# B: Packer / obfuscation / low-strings detection
# =============================================================================
test_b_recommend_dynamic() {
    test_header "Category B: Dynamic-analysis recommendation"

    make_all_mocks
    ensure_fake_image

    # B1: packer branch. Fixture contains "UPX!" and "themida"; either
    # alone is enough to push has_packer=True.
    local case_id="${PREFIX_MALWARE}-2026-01-01-B01"
    local mount
    mount=$(setup_empty_mount_for "${case_id}")
    populate_canonical_fixtures "${mount}"
    inject_packer_strings "${mount}"
    local out="${TEST_DIR}/b1.json"
    run_tool "${case_id}" "${FAKE_IMAGE}" "${out}" >/dev/null
    local reason
    reason=$(json_value "${out}" \
        "d['results']['properties'].get('dynamicReason', '')")
    case "${reason}" in
        *Packer*|*packer*) pass "B1: packer branch -> '${reason}'" ;;
        *) fail "B1: packer branch" "dynamicReason='${reason}'" ;;
    esac

    # B2: low-strings branch. A single tiny fixture file with very few
    # long lines pushes lines<50, but the canonical fixtures have too
    # much content. Use a fresh mount with only one minimal file in
    # a scan path.
    case_id="${PREFIX_MALWARE}-2026-01-01-B02"
    mount=$(setup_empty_mount_for "${case_id}")
    mkdir -p "${mount}/Windows/Temp"
    printf 'MZ\x90\x00tiny binary fragment' \
        > "${mount}/Windows/Temp/tiny.exe"
    out="${TEST_DIR}/b2.json"
    run_tool "${case_id}" "${FAKE_IMAGE}" "${out}" >/dev/null
    reason=$(json_value "${out}" \
        "d['results']['properties'].get('dynamicReason', '')")
    case "${reason}" in
        *Low*string*|*low*string*) pass "B2: low-strings branch -> '${reason}'" ;;
        *) fail "B2: low-strings branch" "dynamicReason='${reason}'" ;;
    esac

    # B3: obfuscation branch. Requires >=50 long lines AND zero packer
    # keywords AND obfuscation keywords. inject_obfuscation_strings
    # produces 80 padding lines + base64/eval/xor markers.
    case_id="${PREFIX_MALWARE}-2026-01-01-B03"
    mount=$(setup_empty_mount_for "${case_id}")
    inject_obfuscation_strings "${mount}"
    out="${TEST_DIR}/b3.json"
    run_tool "${case_id}" "${FAKE_IMAGE}" "${out}" >/dev/null
    reason=$(json_value "${out}" \
        "d['results']['properties'].get('dynamicReason', '')")
    case "${reason}" in
        *Obfuscation*|*obfuscation*) pass "B3: obfuscation branch -> '${reason}'" ;;
        *) fail "B3: obfuscation branch" "dynamicReason='${reason}'" ;;
    esac
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    make_all_mocks
    ensure_fake_image

    # C1: completely empty mount.
    local case_id="${PREFIX_MALWARE}-2026-01-01-C01"
    setup_empty_mount_for "${case_id}" >/dev/null
    local out="${TEST_DIR}/c1.json"
    local code
    code=$(run_tool "${case_id}" "${FAKE_IMAGE}" "${out}")
    assert_exit_code "C1: empty mount -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # C2: scan-path directories exist but contain no matching files.
    case_id="${PREFIX_MALWARE}-2026-01-01-C02"
    local mount
    mount=$(setup_empty_mount_for "${case_id}")
    mkdir -p "${mount}/Windows/Temp"
    mkdir -p "${mount}/ProgramData"
    out="${TEST_DIR}/c2.json"
    run_tool "${case_id}" "${FAKE_IMAGE}" "${out}" >/dev/null
    local found
    found=$(json_value "${out}" \
        "d['results']['properties'].get('totalFilesAnalyzed', -1)")
    assert_equal "C2: empty scan paths -> 0 findings" "0" "${found}"

    # C3: 200-char filename (well below the 255-char kernel limit but
    # still exercises long-name handling in find / sha256sum / etc).
    case_id="${PREFIX_MALWARE}-2026-01-01-C03"
    mount=$(setup_empty_mount_for "${case_id}")
    mkdir -p "${mount}/Windows/Temp"
    local longname
    longname=$(python3 -c "print('a' * 200 + '.exe')")
    printf 'MZ\x90\x00long-named binary' \
        > "${mount}/Windows/Temp/${longname}"
    out="${TEST_DIR}/c3.json"
    code=$(run_tool "${case_id}" "${FAKE_IMAGE}" "${out}")
    assert_exit_code "C3: 200-char filename handled -> exit 0" \
        "${EXIT_SUCCESS}" "${code}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    make_all_mocks
    ensure_fake_image
    local case_id="${PREFIX_MALWARE}-2026-01-01-D01"
    local mount
    mount=$(setup_empty_mount_for "${case_id}")
    populate_canonical_fixtures "${mount}"
    local out="${TEST_DIR}/d.json"
    run_tool "${case_id}" "${FAKE_IMAGE}" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" "${case_id}"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: each suspiciousFiles entry carries a 64-char sha256 hex
    # string (computed by the real sha256sum binary).
    local with_hash
    with_hash=$(json_value "${out}" "
sum(1 for f in d['results']['properties'].get('suspiciousFiles', [])
    if len(f.get('sha256', '')) == 64)")
    if [ "${with_hash:-0}" -ge 3 ] 2>/dev/null; then
        pass "D3: ${with_hash} suspicious files with SHA-256"
    else
        fail "D3: suspicious files hashed" "got: ${with_hash}"
    fi

    # D4: dynamicNeeded boolean populated. The tool always writes it
    # after the recommend_dynamic step; only dry-run leaves it
    # missing.
    local dyn_needed
    dyn_needed=$(json_value "${out}" \
        "type(d['results']['properties'].get('dynamicNeeded')).__name__")
    assert_equal "D4: dynamicNeeded is a bool" "bool" "${dyn_needed}"

    # D5: dynamicReason populated and the strings file path recorded.
    local reason strings_file
    reason=$(json_value "${out}" \
        "d['results']['properties'].get('dynamicReason', '')")
    strings_file=$(json_value "${out}" \
        "d['results']['properties'].get('stringsFile', '')")
    if [ -n "${reason}" ] && [ -n "${strings_file}" ] && \
       [ "${strings_file}" != "None" ]; then
        pass "D5: dynamicReason + stringsFile populated"
    else
        fail "D5: dynamicReason + stringsFile populated" \
             "reason='${reason}' stringsFile='${strings_file}'"
    fi
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    make_all_mocks
    ensure_fake_image

    # E1: findings -> exit 0. The tool's main() returns 0 on any
    # successful run regardless of finding count; there is no
    # EXIT_FINDING (2) path.
    local case_id="${PREFIX_MALWARE}-2026-01-01-E01"
    local mount
    mount=$(setup_empty_mount_for "${case_id}")
    populate_canonical_fixtures "${mount}"
    local code
    code=$(run_tool "${case_id}" "${FAKE_IMAGE}" "${TEST_DIR}/e1.json")
    assert_exit_code "E1: findings -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: no findings -> still 0. Empty mount, tool runs cleanly.
    case_id="${PREFIX_MALWARE}-2026-01-01-E02"
    setup_empty_mount_for "${case_id}" >/dev/null
    code=$(run_tool "${case_id}" "${FAKE_IMAGE}" "${TEST_DIR}/e2.json")
    assert_exit_code "E2: no findings -> 0" "${EXIT_SUCCESS}" "${code}"

    # E3: missing image file -> prerequisites check fails -> exit 99.
    # This is the only deterministic non-zero path on a stock system.
    case_id="${PREFIX_MALWARE}-2026-01-01-E03"
    setup_empty_mount_for "${case_id}" >/dev/null
    code=$(run_tool "${case_id}" "${TEST_DIR}/does_not_exist.dd" \
        "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E3: missing image -> ${code}" ;;
        *) fail "E3: missing image" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptstaticanalysis\n\n'
    test_a_happy_path
    test_b_recommend_dynamic
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptstaticanalysis"
}

main "$@"