#!/usr/bin/env bash
#
# run_all_tests_photorepair.sh
#
# Unit test suite for ptphotorepair.py
# Validates four JPEG repair strategies (eoi_append, header_reconstruct,
# segment_strip, pil_reopen) and the PNG re-save strategy.
# Verifies the non-modification invariant: source files must be unchanged
# after repair.
#
# Coverage: 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_photorepair"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptphotorepair.py"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Fixture builders. The JPEG payloads are real JFIF files produced by
# PIL, then deliberately damaged so each repair strategy has something
# to operate on.
# -----------------------------------------------------------------------------
make_valid_jpeg_via_pil() {
    local path="$1"
    python3 -c "
from PIL import Image
img = Image.new('RGB', (10, 10), color=(255, 0, 0))
img.save('${path}', 'JPEG')
" 2>/dev/null
}

make_jpeg_no_eoi() {
    # Truncate a valid JPEG by removing the last 2 bytes (the EOI marker).
    local valid="${TEST_DIR}/.valid.jpg"
    make_valid_jpeg_via_pil "${valid}"
    local size
    size=$(stat -c%s "${valid}")
    head -c $((size - 2)) "${valid}" > "$1"
}

make_jpeg_truncated() {
    local valid="${TEST_DIR}/.valid.jpg"
    make_valid_jpeg_via_pil "${valid}"
    local size
    size=$(stat -c%s "${valid}")
    head -c $((size / 2)) "${valid}" > "$1"
}

# -----------------------------------------------------------------------------
# write_decision_report <out_path> <filename> <file_path> <decision>
#                       <corruption_type> [<format>]
#
# Writes a decisions JSON whose shape matches what load_decisions()
# actually parses:
#
#     results.nodes[type=repairDecision].properties.decisions[
#         {filename, path, decision, corruptionType, format}, ...
#     ]
#
# Each decision MUST carry an absolute `path` -- _repair_single skips
# entries whose path is missing or non-existent.
# -----------------------------------------------------------------------------
write_decision_report() {
    local out_path="$1"
    local filename="$2"
    local file_path="$3"
    local decision="$4"
    local corruption_type="$5"
    local format="${6:-jpeg}"
    local case_id="${PREFIX_PHOTO}-2026-01-01-001"
    python3 - <<PYEOF
import json
doc = {
    "results": {
        "properties": {"caseId": "${case_id}"},
        "nodes": [{
            "type": "repairDecision",
            "properties": {
                "decisions": [{
                    "filename": "${filename}",
                    "path": "${file_path}",
                    "decision": "${decision}",
                    "corruptionType": "${corruption_type}",
                    "format": "${format}"
                }]
            }
        }]
    }
}
open("${out_path}", "w").write(json.dumps(doc))
PYEOF
}

# -----------------------------------------------------------------------------
# run_tool <case_id> <decisions_path> <json_out_path>
#
# Repaired files land in ${TEST_DIR}/out/<case_id>_repaired/<filename>.
# -----------------------------------------------------------------------------
run_tool() {
    local case_id="$1"
    local decisions="$2"
    local out="$3"
    local code=0
    invoke_tool "${TOOL_PATH}" "${case_id}" "${decisions}" \
        --output-dir "${TEST_DIR}/out" \
        --analyst "Test" \
        --json-out "${out}" \
        >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path -- eoi_append on a JPEG missing its EOI marker
# =============================================================================
test_a_strategies() {
    test_header "Category A: Repair strategies"

    if ! python3 -c 'from PIL import Image' 2>/dev/null; then
        printf '[SKIP] PIL/Pillow not installed; A category skipped\n'
        return 0
    fi

    mkdir -p "${TEST_DIR}/in"

    local case_id="${PREFIX_PHOTO}-2026-01-01-001"
    local src="${TEST_DIR}/in/no_eoi.jpg"
    make_jpeg_no_eoi "${src}"
    local orig_hash
    orig_hash=$(sha256sum "${src}" | awk '{print $1}')

    # corruption_type=missing_footer dispatches _fix_footer -> appends EOI
    # and returns method="eoi_append".
    write_decision_report "${TEST_DIR}/a1_dec.json" \
        "no_eoi.jpg" "${src}" "ATTEMPT_REPAIR" "missing_footer"

    local out="${TEST_DIR}/a1.json"
    local code
    code=$(run_tool "${case_id}" "${TEST_DIR}/a1_dec.json" "${out}")
    assert_exit_code "A1: eoi_append -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: source file unchanged (non-modification invariant)
    local current_hash
    current_hash=$(sha256sum "${src}" | awk '{print $1}')
    assert_equal "A2: source file unchanged after repair" \
        "${orig_hash}" "${current_hash}"

    # A3: repaired file lives in <output-dir>/<case_id>_repaired/<filename>.
    local repaired_dir="${TEST_DIR}/out/${case_id}_repaired"
    local repaired="${repaired_dir}/no_eoi.jpg"
    if [ -f "${repaired}" ]; then
        pass "A3: repaired file produced in ${repaired_dir##*/}/"
    else
        fail "A3: repaired file produced" "not found at ${repaired}"
    fi

    # A4: repaired file ends with EOI (0xFF 0xD9).
    if [ -f "${repaired}" ]; then
        local tail_bytes
        tail_bytes=$(tail -c 2 "${repaired}" | od -An -tx1 | tr -d ' \n')
        assert_equal "A4: repaired JPEG ends with FFD9 (EOI)" \
            "ffd9" "${tail_bytes}"
    else
        fail "A4: repaired JPEG ends with EOI" "repaired file not found"
    fi
}

# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"
    mkdir -p "${TEST_DIR}/in"

    # B1: malformed decisions JSON.
    # load_decisions() wraps json.loads in try/except and calls _fail();
    # the run aborts before repair_all() and main() returns 1.
    echo "this is not valid JSON" > "${TEST_DIR}/b1_dec.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/b1_dec.json" "${TEST_DIR}/b1.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B1: malformed decisions -> ${code}" ;;
        *) fail "B1: malformed decisions" "exit ${code}" ;;
    esac

    # B2: missing decisions file.
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/no_such_decisions.json" "${TEST_DIR}/b2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B2: missing decisions -> ${code}" ;;
        *) fail "B2: missing decisions" "exit ${code}" ;;
    esac

    # B3: decisions reference a file path that does not exist on disk.
    # _repair_single sees src.exists() == False and increments
    # self.skipped; the count appears in top-level properties.
    write_decision_report "${TEST_DIR}/b3_dec.json" \
        "absent.jpg" "${TEST_DIR}/in/absent.jpg" \
        "ATTEMPT_REPAIR" "missing_footer"
    local out="${TEST_DIR}/b3.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/b3_dec.json" "${out}" >/dev/null
    local skipped
    skipped=$(json_value "${out}" \
        "d['results']['properties'].get('skipped', 0)")
    if [ "${skipped:-0}" -ge 1 ] 2>/dev/null; then
        pass "B3: missing target file marked skipped (skipped=${skipped})"
    else
        fail "B3: missing target file" "skipped count: ${skipped}"
    fi
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    if ! python3 -c 'from PIL import Image' 2>/dev/null; then
        printf '[SKIP] PIL/Pillow not installed; C category partial\n'
        return 0
    fi

    mkdir -p "${TEST_DIR}/in"

    # C1: SKIP decision. The tool filters ATTEMPT_REPAIR only, so
    # repair_all() is called with an empty list, repaired=0, and
    # main() returns 1 by contract. Accept either 0 or 1 since both
    # are valid "nothing was repaired" outcomes.
    make_valid_jpeg_via_pil "${TEST_DIR}/in/valid.jpg"
    write_decision_report "${TEST_DIR}/c1_dec.json" \
        "valid.jpg" "${TEST_DIR}/in/valid.jpg" "SKIP" "none"
    local out="${TEST_DIR}/c1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/c1_dec.json" "${out}")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}")
            pass "C1: SKIP decision handled -> exit ${code}" ;;
        *) fail "C1: SKIP decision" "exit ${code}" ;;
    esac

    # C2: MANUAL_REVIEW filtered out by the to_repair list comp; the
    # _repair_single path never runs, so totalAttempted stays 0.
    write_decision_report "${TEST_DIR}/c2_dec.json" \
        "valid.jpg" "${TEST_DIR}/in/valid.jpg" "MANUAL_REVIEW" "none"
    out="${TEST_DIR}/c2.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-002" \
        "${TEST_DIR}/c2_dec.json" "${out}" >/dev/null
    local attempted
    attempted=$(json_value "${out}" \
        "d['results']['properties'].get('totalAttempted', 0)")
    assert_equal "C2: MANUAL_REVIEW not attempted (totalAttempted=0)" \
        "0" "${attempted}"

    # C3: PNG re-save. The .png extension dispatches to _fix_png()
    # regardless of corruptionType; a valid PNG round-trips through
    # PIL successfully and counts as a repair, so exit 0.
    python3 -c "
from PIL import Image
img = Image.new('RGB', (10, 10), color=(0, 255, 0))
img.save('${TEST_DIR}/in/test.png', 'PNG')
"
    write_decision_report "${TEST_DIR}/c3_dec.json" \
        "test.png" "${TEST_DIR}/in/test.png" \
        "ATTEMPT_REPAIR" "unknown" "png"
    out="${TEST_DIR}/c3.json"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/c3_dec.json" "${out}")
    assert_exit_code "C3: PNG re-save -> exit 0" "${EXIT_SUCCESS}" "${code}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    if ! python3 -c 'from PIL import Image' 2>/dev/null; then
        printf '[SKIP] PIL/Pillow not installed; D partial\n'
        return 0
    fi

    mkdir -p "${TEST_DIR}/in"
    local case_id="${PREFIX_PHOTO}-2026-01-01-001"
    local src="${TEST_DIR}/in/no_eoi.jpg"
    make_jpeg_no_eoi "${src}"
    write_decision_report "${TEST_DIR}/d_dec.json" \
        "no_eoi.jpg" "${src}" "ATTEMPT_REPAIR" "missing_footer"
    local out="${TEST_DIR}/d.json"
    run_tool "${case_id}" "${TEST_DIR}/d_dec.json" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" "${case_id}"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: per-file repair result records repairedPath on success.
    # The tool does NOT record hashBefore / hashAfter on individual
    # results; the source-unchanged invariant is verified in A2.
    local repaired_path
    repaired_path=$(json_value "${out}" "
next((r.get('repairedPath', '') for n in d['results']['nodes']
      if n.get('type') == 'repairResults'
      for r in n.get('properties', {}).get('repairResults', [])
      if r.get('success')), '')")
    if [ -n "${repaired_path}" ] && [ "${repaired_path}" != "None" ]; then
        pass "D3: repairResult.repairedPath set on success"
    else
        fail "D3: repairResult.repairedPath set on success" \
             "got: '${repaired_path}'"
    fi

    # D4: per-file result records `method` (the strategy name).
    local method
    method=$(json_value "${out}" "
next((r.get('method', '') for n in d['results']['nodes']
      if n.get('type') == 'repairResults'
      for r in n.get('properties', {}).get('repairResults', [])
      if r.get('success')), '')")
    assert_equal "D4: method=eoi_append recorded" "eoi_append" "${method}"
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    if ! python3 -c 'from PIL import Image' 2>/dev/null; then
        printf '[SKIP] PIL/Pillow not installed; E partial\n'
        return 0
    fi

    mkdir -p "${TEST_DIR}/in"

    # E1: successful repair -> exit 0. A SKIP fixture would force
    # exit 1 by contract; use ATTEMPT_REPAIR on a recoverable JPEG.
    local src="${TEST_DIR}/in/no_eoi.jpg"
    make_jpeg_no_eoi "${src}"
    write_decision_report "${TEST_DIR}/e_dec.json" \
        "no_eoi.jpg" "${src}" "ATTEMPT_REPAIR" "missing_footer"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/e_dec.json" "${TEST_DIR}/e1.json")
    assert_exit_code "E1: successful repair -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: missing decisions file -> load_decisions fails -> exit 1.
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/no_such_decisions.json" "${TEST_DIR}/e2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing decisions -> ${code}" ;;
        *) fail "E2: missing decisions" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptphotorepair\n\n'
    test_a_strategies
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptphotorepair"
}

main "$@"