#!/usr/bin/env bash
#
# run_all_tests_repairdecision.sh
#
# Unit test suite for ptrepairdecision.py
# Validates rules R1-R5 that map damage type to one of
# ATTEMPT_REPAIR / MANUAL_REVIEW / SKIP (chapter 4.5.7).
# This module does not modify files; it consumes a JSON integrity
# report and produces a JSON decision report.
#
# Coverage: 5 categories per chapter 5.4.2 of the thesis.
#
# Rule mapping (driven by REPAIR_SUCCESS_RATES, thesis Annex B):
#     R1  rate >= 85       -> ATTEMPT_REPAIR
#     R2  50 <= rate < 85  -> ATTEMPT_REPAIR
#     R3  30 <= rate < 50  -> MANUAL_REVIEW
#     R4  15 <= rate < 30  -> SKIP
#     R5  rate < 15        -> SKIP
# Concrete rate table:
#     missing_footer     90  -> R1
#     invalid_header     85  -> R1
#     truncated          85  -> R1
#     corrupt_segments   60  -> R2
#     corrupted_metadata 60  -> R2
#     corrupt_data       40  -> R3
#     partial_data       40  -> R3
#     unknown            29  -> R4
#     invalid_structure  20  -> R4
#     fragmented         15  -> R4
# Unknown corruption types fall back to the "unknown" rate (29) -> R4.
# R5 (<15) is unreachable through the public surface; the suite covers
# R1, R2, R3, R4.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_repairdecision"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptrepairdecision.py"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# write_integrity_report <out_path> <python_list_literal>
#
# Writes an integrity-validation report in the exact shape the tool
# reads: a single `integrityValidation` node whose properties contain
# a `fileResults` list. The list argument is interpolated verbatim as
# a Python literal so individual fields can be quoted naturally.
# -----------------------------------------------------------------------------
write_integrity_report() {
    local out_path="$1"
    local records_python="$2"
    local case_id="${3:-${PREFIX_PHOTO}-2026-01-01-001}"
    python3 - <<PYEOF
import json
records = ${records_python}
doc = {
    "results": {
        "properties": {
            "caseId": "${case_id}",
            "totalFiles": len(records),
        },
        "nodes": [{
            "type": "integrityValidation",
            "properties": {"fileResults": records},
        }],
    },
}
open("${out_path}", "w").write(json.dumps(doc, indent=2))
PYEOF
}


# -----------------------------------------------------------------------------
# get_decision_field <json_file> <field>
#
# Returns the value of <field> on the FIRST entry inside
# repairDecision.properties.decisions, or '' if no decisions exist.
# -----------------------------------------------------------------------------
get_decision_field() {
    local file="$1"
    local field="$2"
    json_value "${file}" "
next((dec.get('${field}', '') for n in d['results']['nodes']
      if n.get('type') == 'repairDecision'
      for dec in n.get('properties', {}).get('decisions', [])), '')"
}


# -----------------------------------------------------------------------------
# count_decisions_with <json_file> <field> <value>
#
# Returns the number of decision entries where <field> == <value>.
# -----------------------------------------------------------------------------
count_decisions_with() {
    local file="$1"
    local field="$2"
    local value="$3"
    json_value "${file}" "
sum(1 for n in d['results']['nodes']
    if n.get('type') == 'repairDecision'
    for dec in n.get('properties', {}).get('decisions', [])
    if dec.get('${field}') == '${value}')"
}


run_tool() {
    local case_id="$1"
    local integrity="$2"
    local out="$3"
    local code=0
    invoke_tool "${TOOL_PATH}" "${case_id}" "${integrity}" \
        --output-dir "${TEST_DIR}/out" \
        --analyst "Test" \
        --json-out "${out}" \
        >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path -- rule application
# =============================================================================
test_a_rule_application() {
    test_header "Category A: Rule application"

    # A1: corruption rate 90 (missing_footer) -> R1 ATTEMPT_REPAIR
    write_integrity_report "${TEST_DIR}/a1_in.json" '[
        {"filename": "a.jpg", "status": "repairable",
         "corruptionType": "missing_footer", "path": "/tmp/a.jpg"}
    ]'
    local out="${TEST_DIR}/a1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/a1_in.json" "${out}")
    assert_exit_code "A1: missing_footer -> exit 0" "${EXIT_SUCCESS}" "${code}"

    local decision
    decision=$(get_decision_field "${out}" "decision")
    assert_equal "A2: missing_footer (90%) -> ATTEMPT_REPAIR (R1)" \
        "ATTEMPT_REPAIR" "${decision}"

    # A3: corruption rate 85 (invalid_header) -> still R1 ATTEMPT_REPAIR
    write_integrity_report "${TEST_DIR}/a3_in.json" '[
        {"filename": "b.jpg", "status": "repairable",
         "corruptionType": "invalid_header", "path": "/tmp/b.jpg"}
    ]'
    out="${TEST_DIR}/a3.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-002" \
        "${TEST_DIR}/a3_in.json" "${out}" >/dev/null
    decision=$(get_decision_field "${out}" "decision")
    assert_equal "A3: invalid_header (85%) -> ATTEMPT_REPAIR (R1)" \
        "ATTEMPT_REPAIR" "${decision}"

    # A4: corruption rate 40 (corrupt_data) -> R3 MANUAL_REVIEW.
    write_integrity_report "${TEST_DIR}/a4_in.json" '[
        {"filename": "c.jpg", "status": "repairable",
         "corruptionType": "corrupt_data", "path": "/tmp/c.jpg"}
    ]'
    out="${TEST_DIR}/a4.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/a4_in.json" "${out}" >/dev/null
    decision=$(get_decision_field "${out}" "decision")
    assert_equal "A4: corrupt_data (40%) -> MANUAL_REVIEW (R3)" \
        "MANUAL_REVIEW" "${decision}"

    # A5: valid files are filtered out before the decision engine runs,
    # so no decision is emitted for them.
    write_integrity_report "${TEST_DIR}/a5_in.json" '[
        {"filename": "d.jpg", "status": "valid",
         "corruptionType": "", "path": "/tmp/d.jpg"}
    ]'
    out="${TEST_DIR}/a5.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-004" \
        "${TEST_DIR}/a5_in.json" "${out}" >/dev/null
    local total
    total=$(json_value "${out}" \
        "d['results']['properties'].get('totalRepairable', -1)")
    assert_equal "A5: valid file -> no decision emitted (totalRepairable=0)" \
        "0" "${total}"
}


# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    # B1: missing integrity report -> _load returns None -> _fail ->
    # no totalRepairable -> main returns 1.
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/missing.json" "${TEST_DIR}/b1.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B1: missing report -> ${code}" ;;
        *) fail "B1: missing report" "exit ${code}" ;;
    esac

    # B2: malformed JSON -> json.loads raises -> _load returns None ->
    # same path as B1.
    echo "{ not valid json" > "${TEST_DIR}/b2_in.json"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/b2_in.json" "${TEST_DIR}/b2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B2: malformed JSON -> ${code}" ;;
        *) fail "B2: malformed JSON" "exit ${code}" ;;
    esac

    # B3: well-formed report with no file entries. process_validation_report
    # still sets totalRepairable=0, so main returns 0.
    write_integrity_report "${TEST_DIR}/b3_in.json" '[]'
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/b3_in.json" "${TEST_DIR}/b3.json")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}")
            pass "B3: empty file list -> ${code}" ;;
        *) fail "B3: empty file list" "exit ${code}" ;;
    esac
}


# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    # C1: batch covering R1..R4 in one run. Verifies the counters
    # increment per-rule, not just per-record.
    #   missing_footer    90 -> R1 ATTEMPT_REPAIR
    #   corrupt_segments  60 -> R2 ATTEMPT_REPAIR
    #   corrupt_data      40 -> R3 MANUAL_REVIEW
    #   fragmented        15 -> R4 SKIP
    write_integrity_report "${TEST_DIR}/c1_in.json" '[
        {"filename": "r1.jpg", "status": "repairable",
         "corruptionType": "missing_footer",   "path": "/tmp/r1.jpg"},
        {"filename": "r2.jpg", "status": "repairable",
         "corruptionType": "corrupt_segments", "path": "/tmp/r2.jpg"},
        {"filename": "r3.jpg", "status": "repairable",
         "corruptionType": "corrupt_data",     "path": "/tmp/r3.jpg"},
        {"filename": "r4.jpg", "status": "repairable",
         "corruptionType": "fragmented",       "path": "/tmp/r4.jpg"}
    ]'
    local out="${TEST_DIR}/c1.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/c1_in.json" "${out}" >/dev/null

    local attempt manual skip
    attempt=$(json_value "${out}" \
        "d['results']['properties'].get('attemptRepair', -1)")
    manual=$(json_value "${out}" \
        "d['results']['properties'].get('manualReview', -1)")
    skip=$(json_value "${out}" \
        "d['results']['properties'].get('skip', -1)")
    if [ "${attempt}" = "2" ] && [ "${manual}" = "1" ] && [ "${skip}" = "1" ]; then
        pass "C1: mixed batch -> attempt=2 manual=1 skip=1"
    else
        fail "C1: mixed batch counters" \
             "got attemptRepair=${attempt}, manualReview=${manual}, skip=${skip}"
    fi

    # C2: unknown corruption type. decide_single falls back to the
    # "unknown" rate (29) -> R4 SKIP. This tests the dict-default
    # branch in decide_single().
    write_integrity_report "${TEST_DIR}/c2_in.json" '[
        {"filename": "unk.jpg", "status": "repairable",
         "corruptionType": "some_unrecognised_type", "path": "/tmp/unk.jpg"}
    ]'
    out="${TEST_DIR}/c2.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-002" \
        "${TEST_DIR}/c2_in.json" "${out}" >/dev/null
    local decision
    decision=$(get_decision_field "${out}" "decision")
    assert_equal "C2: unknown corruption -> fallback rate 29 -> SKIP (R4)" \
        "SKIP" "${decision}"

    # C3: large batch. With status cycled across 4 values, only the
    # "repairable" quarter (25 records) reaches the decision engine.
    python3 - <<PYEOF
import json
statuses = ["valid", "repairable", "corrupted", "invalid"]
ctypes   = ["", "missing_footer", "corrupt_data", "fragmented"]
records = []
for i in range(100):
    records.append({
        "filename": f"f{i:03d}.jpg",
        "status": statuses[i % 4],
        "corruptionType": ctypes[i % 4],
        "path": f"/tmp/f{i:03d}.jpg",
    })
doc = {
    "results": {
        "properties": {"caseId": "${PREFIX_PHOTO}-2026-01-01-003", "totalFiles": 100},
        "nodes": [{"type": "integrityValidation",
                   "properties": {"fileResults": records}}],
    },
}
open("${TEST_DIR}/c3_in.json", "w").write(json.dumps(doc))
PYEOF
    out="${TEST_DIR}/c3.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/c3_in.json" "${out}")
    assert_exit_code "C3: 100-file batch -> exit 0" "${EXIT_SUCCESS}" "${code}"

    local total
    total=$(json_value "${out}" \
        "d['results']['properties'].get('totalRepairable', -1)")
    assert_equal "C3: 25 of 100 records have status=repairable" \
        "25" "${total}"
}


# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    write_integrity_report "${TEST_DIR}/d_in.json" '[
        {"filename": "a.jpg", "status": "repairable",
         "corruptionType": "missing_footer", "path": "/tmp/a.jpg"}
    ]'
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/d_in.json" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_PHOTO}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: each decision entry records the rule that produced it under
    # `ruleApplied` (not `rule`). Values look like "R1 - High recovery
    # probability".
    local rule
    rule=$(get_decision_field "${out}" "ruleApplied")
    case "${rule}" in
        R1*|R2*|R3*|R4*|R5*) pass "D3: decision references rule (${rule%% *})" ;;
        *) fail "D3: decision references rule (R1..R5)" "got: '${rule}'" ;;
    esac
}


# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    # E1: a well-formed report (even with only valid files) yields
    # totalRepairable=0 in properties -> main returns 0.
    write_integrity_report "${TEST_DIR}/e_in.json" '[
        {"filename": "a.jpg", "status": "valid",
         "corruptionType": "", "path": "/tmp/a.jpg"}
    ]'
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/e_in.json" "${TEST_DIR}/e1.json")
    assert_exit_code "E1: well-formed report -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: missing report -> 1.
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/missing.json" "${TEST_DIR}/e2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing report -> ${code}" ;;
        *) fail "E2: missing report" "exit ${code}" ;;
    esac
}


main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptrepairdecision\n\n'
    test_a_rule_application
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptrepairdecision"
}

main "$@"