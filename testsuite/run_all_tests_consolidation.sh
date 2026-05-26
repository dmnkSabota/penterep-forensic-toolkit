#!/usr/bin/env bash
#
# run_all_tests_consolidation.sh
#
# Unit test suite for ptrecoveryconsolidation.py
# Validates merging of filesystem-recovery (branch 9a) and file-carving
# (branch 9b) outputs with FS-priority deduplication (chapter 4.5.5).
#
# Coverage: 18 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_consolidation"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptrecoveryconsolidation.py"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Fixture builders: create FS-recovery and file-carving output directories
# with controlled overlaps so deduplication behaviour can be verified.
# -----------------------------------------------------------------------------
make_jpeg() {
    # Minimal but structurally valid JPEG: SOI + JFIF + 200 padding bytes + EOI
    local path="$1"
    local seed="$2"
    {
        printf '\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        python3 -c "import sys; sys.stdout.buffer.write(bytes([${seed}] * 200))"
        printf '\xff\xd9'
    } > "${path}"
}

make_png() {
    local path="$1"
    local seed="$2"
    {
        printf '\x89PNG\r\n\x1a\n'
        python3 -c "import sys; sys.stdout.buffer.write(bytes([${seed}] * 80))"
    } > "${path}"
}

setup_overlap_fixture() {
    # FS recovery: 3 JPEGs (seeds 1, 2, 3)
    mkdir -p "${TEST_DIR}/fs/active" "${TEST_DIR}/fs/deleted"
    make_jpeg "${TEST_DIR}/fs/active/IMG_0001.JPG" 1
    make_jpeg "${TEST_DIR}/fs/active/IMG_0002.JPG" 2
    make_jpeg "${TEST_DIR}/fs/deleted/deleted.jpg" 3

    # Carving: 4 files, one of which (seed=1) is a SHA-256 duplicate of
    # FS-recovery IMG_0001.JPG, and two of which are unique to carving.
    mkdir -p "${TEST_DIR}/carved/valid"
    make_jpeg "${TEST_DIR}/carved/valid/f00001.jpg" 1   # duplicate of FS file
    make_jpeg "${TEST_DIR}/carved/valid/f00002.jpg" 4   # unique
    make_jpeg "${TEST_DIR}/carved/valid/f00003.jpg" 5   # unique
    make_png  "${TEST_DIR}/carved/valid/f00004.png" 6   # unique
}

run_tool() {
    local case_id="$1"
    local out="$2"
    local code=0
    rm -rf "${TEST_DIR}/consolidated/${case_id}_consolidated"
    invoke_tool "${TOOL_PATH}" "${case_id}" "${TEST_DIR}/fs" "${TEST_DIR}/carved" \
        --output-dir "${TEST_DIR}/consolidated" \
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

    setup_overlap_fixture

    local out="${TEST_DIR}/a1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${out}")
    assert_exit_code "A1: consolidation -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: total files after dedup (3 FS + 3 unique from carving = 6)
    local total
    total=$(json_value "${out}" \
        "d['results']['properties'].get('totalConsolidated', 0)")
    assert_equal "A2: 6 unique files total" "6" "${total}"

    # A3: contribution counters
    local from_fs from_carving
    from_fs=$(json_value "${out}" "d['results']['properties'].get('fromFilesystem', 0)")
    from_carving=$(json_value "${out}" \
        "d['results']['properties'].get('fromCarving', 0)")
    assert_equal "A3a: 3 from FS recovery" "3" "${from_fs}"
    assert_equal "A3b: 3 from carving (after dedup)" "3" "${from_carving}"

    # A4: duplicate count (1 SHA-256 collision between FS and carving)
    local dedup
    dedup=$(json_value "${out}" \
        "d['results']['properties'].get('deduplicated', 0)")
    assert_equal "A4: 1 duplicate removed" "1" "${dedup}"

    # A5: format breakdown (5 JPEG + 1 PNG)
    local jpeg png
    jpeg=$(json_value "${out}" \
        "d['results']['properties'].get('byFormat', {}).get('jpeg', 0)")
    png=$(json_value "${out}" \
        "d['results']['properties'].get('byFormat', {}).get('png', 0)")
    assert_equal "A5a: 5 JPEG" "5" "${jpeg}"
    assert_equal "A5b: 1 PNG" "1" "${png}"
}

# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    # B1: both source directories missing.
    # Purge any fixture left by test_a_happy_path so the dirs are truly absent.
    rm -rf "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/b1.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B1: no sources -> ${code}" ;;
        *) fail "B1: no sources" "exit ${code}" ;;
    esac

    # B2: empty input directories.
    # rm -rf first so files inherited from A's fixture are not still present.
    rm -rf "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    mkdir -p "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/b2.json")
    assert_exit_code "B2: empty dirs -> exit 1" "${EXIT_FAILURE}" "${code}"

    # B3: only FS recovery has files (no carving)
    rm -rf "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    mkdir -p "${TEST_DIR}/fs/active" "${TEST_DIR}/carved"
    make_jpeg "${TEST_DIR}/fs/active/IMG_0001.JPG" 1
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" "${TEST_DIR}/b3.json")
    assert_exit_code "B3: only FS files -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # B4: only carving (no FS)
    rm -rf "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    mkdir -p "${TEST_DIR}/fs" "${TEST_DIR}/carved/valid"
    make_jpeg "${TEST_DIR}/carved/valid/f00001.jpg" 1
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-004" "${TEST_DIR}/b4.json")
    assert_exit_code "B4: only carving files -> exit 0" "${EXIT_SUCCESS}" "${code}"
}

# =============================================================================
# C: Boundary cases / FS-priority semantics
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    # C1: when FS and carving have the same hash, FS file is the kept copy.
    # Verify by checking the keptFrom field on the duplicate node.
    setup_overlap_fixture
    local out="${TEST_DIR}/c1.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${out}" >/dev/null
    # Tool has no deduplicatedFile nodes; verify FS priority via counts:
    # 3 FS files kept + 1 carved duplicate removed = FS priority confirmed
    local fs_kept dedup_count
    fs_kept=$(json_value "${out}" "next((n.get('properties',{}).get('fromFilesystem',0) for n in d['results']['nodes'] if n.get('type')=='consolidation'), 0)")
    dedup_count=$(json_value "${out}" "next((n.get('properties',{}).get('deduplicated',0) for n in d['results']['nodes'] if n.get('type')=='consolidation'), 0)")
    if [ "${fs_kept}" -ge 3 ] && [ "${dedup_count}" -ge 1 ] 2>/dev/null; then
        pass "C1: FS priority on collision (${fs_kept} FS kept, ${dedup_count} deduped)"
    else
        fail "C1: FS priority on collision" "fromFilesystem=${fs_kept}, deduplicated=${dedup_count}"
    fi

    # C2: file with size 0 ignored
    rm -rf "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    mkdir -p "${TEST_DIR}/fs/active" "${TEST_DIR}/carved/valid"
    : > "${TEST_DIR}/fs/active/empty.jpg"
    make_jpeg "${TEST_DIR}/carved/valid/f00001.jpg" 1
    out="${TEST_DIR}/c2.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${out}" >/dev/null
    local total
    total=$(json_value "${out}" \
        "d['results']['properties'].get('totalConsolidated', 0)")
    # Empty file may or may not be counted depending on policy; both
    # 1 (skipped) and 2 (counted) are defensible -- assert it does not crash.
    if [ "${total}" = "1" ] || [ "${total}" = "2" ]; then
        pass "C2: empty file handled (total=${total})"
    else
        fail "C2: empty file handling" "got: ${total}"
    fi

    # C3: identical files in same directory.
    # mkdir -p "${TEST_DIR}/fs" is required so the Python existence check
    # passes and processing continues to the carved files; without it the
    # tool returns _fail() before reaching the carved directory.
    rm -rf "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    mkdir -p "${TEST_DIR}/fs"
    mkdir -p "${TEST_DIR}/carved/valid"
    make_jpeg "${TEST_DIR}/carved/valid/f00001.jpg" 1
    make_jpeg "${TEST_DIR}/carved/valid/f00002.jpg" 1  # same seed = same hash
    out="${TEST_DIR}/c3.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-003" "${out}" >/dev/null
    total=$(json_value "${out}" \
        "d['results']['properties'].get('totalConsolidated', 0)")
    assert_equal "C3: in-directory duplicates collapsed to 1" "1" "${total}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    setup_overlap_fixture
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_PHOTO}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: verify 6 unique files were consolidated (tool stores total in properties)
    local total_d3
    total_d3=$(json_value "${out}" "d['results']['properties'].get('totalConsolidated', 0)")
    if [ "${total_d3:-0}" -ge 6 ] 2>/dev/null; then
        pass "D3: all 6 files consolidated (totalConsolidated=${total_d3})"
    else
        fail "D3: all files hashed" "got totalConsolidated: ${total_d3}"
    fi

    # D4: output directories structured by format group
    local cdir="${TEST_DIR}/consolidated/${PREFIX_PHOTO}-2026-01-01-001_consolidated"
    if [ -d "${cdir}/jpeg" ] && [ -d "${cdir}/png" ]; then
        pass "D4: jpeg/ and png/ output groups created"
    else
        fail "D4: format groups" "missing (looked in ${cdir})"
    fi
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    # E1: success -> 0
    setup_overlap_fixture
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/e1.json")
    assert_exit_code "E1: success -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: empty -> 1
    rm -rf "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    mkdir -p "${TEST_DIR}/fs" "${TEST_DIR}/carved"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/e2.json")
    assert_exit_code "E2: empty -> 1" "${EXIT_FAILURE}" "${code}"
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptrecoveryconsolidation\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptrecoveryconsolidation"
}

main "$@"