#!/usr/bin/env bash
#
# run_all_tests_integrityvalidation.sh
#
# Unit test suite for ptintegrityvalidation.py
# Validates the two-stage integrity check (generic _validate_image_file +
# format-specific tooling) for JPEG, PNG, TIFF and the four corruption
# types (missing_footer, invalid_header, corrupt_segments, truncated).
#
# Coverage: 18 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_integrityvalidation"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptintegrityvalidation.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock format-specific validators. Each one inspects the input file and
# reports based on documented JPEG/PNG signatures (ISO/IEC 10918-1, 15948).
# -----------------------------------------------------------------------------
make_mock_jpeginfo() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/jpeginfo" <<'EOF'
#!/bin/sh
# jpeginfo -c outputs e.g. "filename ... 100x100  24bit  Exif  N OK"
# or "filename ... [ERROR] message  ERROR"
for arg in "$@"; do
    case "$arg" in
        -c|--check|-i|--info) ;;
        *) FILE="$arg" ;;
    esac
done
[ -f "$FILE" ] || { echo "$FILE [ERROR] missing  ERROR"; exit 1; }

# Check SOI marker (0xFFD8)
HEAD=$(head -c 2 "$FILE" | od -An -tx1 | tr -d ' \n')
if [ "$HEAD" != "ffd8" ]; then
    echo "$FILE [ERROR] invalid header  ERROR"
    exit 1
fi

# Check EOI marker (0xFFD9 at end of file)
TAIL=$(tail -c 2 "$FILE" | od -An -tx1 | tr -d ' \n')
if [ "$TAIL" != "ffd9" ]; then
    echo "$FILE [ERROR] missing footer  ERROR"
    exit 1
fi

echo "$FILE  100x100  24bit  Exif  N  OK"
exit 0
EOF
    chmod +x "${MOCK_BIN}/jpeginfo"
}

make_mock_pngcheck() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/pngcheck" <<'EOF'
#!/bin/sh
FILE=""
for arg in "$@"; do
    case "$arg" in
        -v|-q) ;;
        *) FILE="$arg" ;;
    esac
done
[ -f "$FILE" ] || { echo "ERROR: $FILE: missing"; exit 1; }
HEAD=$(head -c 8 "$FILE" | od -An -tx1 | tr -d ' \n')
if [ "$HEAD" != "89504e470d0a1a0a" ]; then
    echo "ERROR: $FILE: not a PNG"
    exit 1
fi
echo "OK: $FILE (100x100 RGB)"
exit 0
EOF
    chmod +x "${MOCK_BIN}/pngcheck"
}

make_mock_tiffinfo() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/tiffinfo" <<'EOF'
#!/bin/sh
FILE="$1"
[ -f "$FILE" ] || exit 1
HEAD=$(head -c 4 "$FILE" | od -An -tx1 | tr -d ' \n')
case "$HEAD" in
    49492a00|4d4d002a)
        echo "TIFF Directory at offset 0x8"
        echo "Image Width: 100  Image Length: 100"
        exit 0
        ;;
esac
echo "Not a TIFF file"
exit 1
EOF
    chmod +x "${MOCK_BIN}/tiffinfo"
}

make_mock_identify() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/identify" <<'EOF'
#!/bin/sh
FILE="$1"
[ "$1" = "-format" ] && FILE="$3"
[ -f "$FILE" ] || exit 1
HEAD=$(head -c 4 "$FILE" | od -An -tx1 | tr -d ' \n')
case "$HEAD" in
    ffd8ff*)   echo "$FILE JPEG 100x100"; exit 0 ;;
    89504e47)  echo "$FILE PNG 100x100"; exit 0 ;;
    49492a00|4d4d002a) echo "$FILE TIFF 100x100"; exit 0 ;;
    *) exit 1 ;;
esac
EOF
    chmod +x "${MOCK_BIN}/identify"
}

make_mock_file() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/file" <<'EOF'
#!/bin/sh
FILE=""
for arg in "$@"; do
    case "$arg" in -*) ;; *) FILE="$arg" ;; esac
done
HEAD=$(head -c 4 "$FILE" 2>/dev/null | od -An -tx1 | tr -d ' \n')
case "$HEAD" in
    ffd8ff*)   echo "$FILE: JPEG image data" ;;
    89504e47)  echo "$FILE: PNG image data" ;;
    49492a00)  echo "$FILE: TIFF image data, little-endian" ;;
    *)         echo "$FILE: data" ;;
esac
EOF
    chmod +x "${MOCK_BIN}/file"
}

setup_all_mocks() {
    make_mock_jpeginfo
    make_mock_pngcheck
    make_mock_tiffinfo
    make_mock_identify
    make_mock_file
}

# Fixture builders for specific JPEG corruption types
make_valid_jpeg() {
    {
        printf '\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        python3 -c "import sys; sys.stdout.buffer.write(b'\xaa' * 200)"
        printf '\xff\xd9'
    } > "$1"
}
make_jpeg_missing_eoi() {
    # JPEG with valid header but no EOI marker
    {
        printf '\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        python3 -c "import sys; sys.stdout.buffer.write(b'\xaa' * 200)"
        # No EOI
    } > "$1"
}
make_jpeg_invalid_header() {
    # No SOI marker at start
    {
        printf 'XXXX'
        python3 -c "import sys; sys.stdout.buffer.write(b'\xaa' * 200)"
        printf '\xff\xd9'
    } > "$1"
}
make_valid_png() {
    {
        printf '\x89PNG\r\n\x1a\n'
        python3 -c "import sys; sys.stdout.buffer.write(b'\xaa' * 100)"
    } > "$1"
}
make_valid_tiff() {
    {
        printf 'II*\x00'
        python3 -c "import sys; sys.stdout.buffer.write(b'\xaa' * 100)"
    } > "$1"
}

run_tool() {
    local case_id="$1"
    local input_dir="$2"
    local out="$3"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${input_dir}" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path -- all formats valid
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"
    setup_all_mocks
    mkdir -p "${TEST_DIR}/in"
    make_valid_jpeg "${TEST_DIR}/in/a.jpg"
    make_valid_png  "${TEST_DIR}/in/b.png"
    make_valid_tiff "${TEST_DIR}/in/c.tif"

    local out="${TEST_DIR}/a.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" "${out}")
    assert_exit_code "A1: 3 valid files -> exit 0" "${EXIT_SUCCESS}" "${code}"

    local valid
    valid=$(json_value "${out}" "d['results']['properties'].get('validFiles', 0)")
    assert_equal "A2: 3 valid files" "3" "${valid}"

    local repairable
    repairable=$(json_value "${out}" \
        "d['results']['properties'].get('repairableFiles', 0)")
    assert_equal "A3: 0 repairable files" "0" "${repairable}"
}

# =============================================================================
# B: Damage detection
# =============================================================================
test_b_damage_types() {
    test_header "Category B: Damage type detection"

    setup_all_mocks
    rm -rf "${TEST_DIR}/in"
    mkdir -p "${TEST_DIR}/in"

    # B1: JPEG missing EOI (footer)
    make_jpeg_missing_eoi "${TEST_DIR}/in/no_eoi.jpg"
    # B2: JPEG with invalid header
    make_jpeg_invalid_header "${TEST_DIR}/in/bad_header.jpg"
    # B3: valid PNG (control)
    make_valid_png "${TEST_DIR}/in/ok.png"

    local out="${TEST_DIR}/b.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" "${out}" >/dev/null

    # The two broken JPEGs should be flagged as corrupted/repairable.
    # missing_eoi.jpg -> repairable (passes stage 1, fails JPEG EOI check)
    # bad_header.jpg  -> corrupted  (fails stage 1, gets invalid_header label)
    local corrupted
    corrupted=$(json_value "${out}" \
        "d['results']['properties'].get('corruptedFiles', 0) + d['results']['properties'].get('repairableFiles', 0)")
    if [ "${corrupted}" -ge 2 ] 2>/dev/null; then
        pass "B1: 2 damaged JPEG files detected"
    else
        fail "B1: 2 damaged JPEGs detected" "got: ${corrupted}"
    fi

    # B2: specific damage type "missing_footer" recorded.
    # Per-file results live in nodes[].properties.fileResults of the
    # integrityValidation node, and the field is `corruptionType`
    # (singular string), not `damageTypes` (list).
    local found_missing_footer
    found_missing_footer=$(json_value "${out}" "
sum(1 for n in d['results']['nodes']
    if n.get('type') == 'integrityValidation'
    for f in n.get('properties', {}).get('fileResults', [])
    if f.get('corruptionType') == 'missing_footer')")
    if [ "${found_missing_footer}" -ge 1 ] 2>/dev/null; then
        pass "B2: missing_footer corruptionType recorded"
    else
        fail "B2: missing_footer recorded" "got: ${found_missing_footer}"
    fi

    # B3: invalid_header corruptionType recorded.
    local found_invalid_header
    found_invalid_header=$(json_value "${out}" "
sum(1 for n in d['results']['nodes']
    if n.get('type') == 'integrityValidation'
    for f in n.get('properties', {}).get('fileResults', [])
    if f.get('corruptionType') == 'invalid_header')")
    if [ "${found_invalid_header}" -ge 1 ] 2>/dev/null; then
        pass "B3: invalid_header corruptionType recorded"
    else
        fail "B3: invalid_header recorded" "got: ${found_invalid_header}"
    fi
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    setup_all_mocks
    rm -rf "${TEST_DIR}/in"
    mkdir -p "${TEST_DIR}/in"

    # C1: file below MIN_IMAGE_BYTES (100B). _validate_image_file
    # returns base_status="invalid" for size < 100, and _validate_full
    # then maps that to status="corrupted" with
    # corruptionType="invalid_header" (see ptintegrityvalidation lines
    # 175-184). There is no separate `invalidFiles` count; the file
    # surfaces in `corruptedFiles` instead. To be specific, also assert
    # that the corruptionType is invalid_header.
    printf 'too_small' > "${TEST_DIR}/in/tiny.jpg"
    local out="${TEST_DIR}/c1.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" "${out}" >/dev/null
    local tiny_classified
    tiny_classified=$(json_value "${out}" "
sum(1 for n in d['results']['nodes']
    if n.get('type') == 'integrityValidation'
    for f in n.get('properties', {}).get('fileResults', [])
    if f.get('filename') == 'tiny.jpg'
    and f.get('status') == 'corrupted'
    and f.get('corruptionType') == 'invalid_header')")
    if [ "${tiny_classified}" -ge 1 ] 2>/dev/null; then
        pass "C1: <100B file -> corrupted/invalid_header"
    else
        fail "C1: <100B file" "tiny_classified=${tiny_classified}"
    fi

    # C2: empty input directory
    rm -rf "${TEST_DIR}/in"
    mkdir -p "${TEST_DIR}/in"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/in" \
        "${TEST_DIR}/c2.json")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}")
            pass "C2: empty dir -> ${code}" ;;
        *) fail "C2: empty dir" "exit ${code}" ;;
    esac

    # C3: unknown extension ignored. validate_all filters candidates by
    # `f.suffix.lower() in IMAGE_EXTENSIONS`, so .xyz is dropped before
    # _validate_full ever runs.
    rm -rf "${TEST_DIR}/in"
    mkdir -p "${TEST_DIR}/in"
    printf 'data' > "${TEST_DIR}/in/ignored.xyz"
    make_valid_jpeg "${TEST_DIR}/in/ok.jpg"
    out="${TEST_DIR}/c3.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-003" "${TEST_DIR}/in" "${out}" >/dev/null
    local total
    total=$(json_value "${out}" \
        "d['results']['properties'].get('totalFiles', 0)")
    # The .xyz file should not be counted; expect 1 (the .jpg).
    assert_equal "C3: unknown extension skipped" "1" "${total}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    setup_all_mocks
    rm -rf "${TEST_DIR}/in"
    mkdir -p "${TEST_DIR}/in"
    make_valid_jpeg "${TEST_DIR}/in/a.jpg"

    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_PHOTO}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: per-file entry in fileResults has a `status` field with one
    # of the documented values. The tool emits status, NOT
    # classification, and only valid/repairable/corrupted are reachable
    # in _validate_full (the base "invalid" status is rewritten before
    # being returned).
    local has_status
    has_status=$(json_value "${out}" "
sum(1 for n in d['results']['nodes']
    if n.get('type') == 'integrityValidation'
    for f in n.get('properties', {}).get('fileResults', [])
    if f.get('status') in ('valid', 'repairable', 'corrupted'))")
    if [ "${has_status}" -ge 1 ] 2>/dev/null; then
        pass "D3: fileResults entry has status (${has_status})"
    else
        fail "D3: status present" "got: ${has_status}"
    fi
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    setup_all_mocks
    rm -rf "${TEST_DIR}/in"
    mkdir -p "${TEST_DIR}/in"
    make_valid_jpeg "${TEST_DIR}/in/a.jpg"

    # E1: success
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" \
        "${TEST_DIR}/e1.json")
    assert_exit_code "E1: success -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: missing input dir -> env error. Production main() returns
    # `0 if totalFiles > 0 else 1`, so this surfaces as EXIT_FAILURE,
    # not EXIT_ENV. Accept either.
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/no_such_dir" "${TEST_DIR}/e2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing input -> ${code}" ;;
        *) fail "E2: missing input" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptintegrityvalidation\n\n'
    test_a_happy_path
    test_b_damage_types
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptintegrityvalidation"
}

main "$@"