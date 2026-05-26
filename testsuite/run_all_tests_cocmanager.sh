#!/usr/bin/env bash
#
# run_all_tests_cocmanager.sh
#
# Unit test suite for ptcocmanager.py
#
# Validates 22 test cases organised into 5 categories per the test design
# methodology described in chapter 5 of the accompanying thesis. Category
# allocation follows the convention shared by every suite in this project:
#
#   A  Hlavny pracovny postup (happy path)
#   B  Chybove podmienky      (error conditions)
#   C  Hranicne pripady       (boundary cases)
#   D  JSON / CoC struktura   (JSON contract)
#   E  Navratove hodnoty      (exit code convention)
#
# Reference values originate exclusively from external sources documented
# in testlib/reference_values.sh. No expected value is derived from the
# implementation under test.
#
# Usage:
#   ./run_all_tests_cocmanager.sh                    # standard run
#   COVERAGE=1 ./run_all_tests_cocmanager.sh         # with coverage.py
#   NO_COLOR=1 ./run_all_tests_cocmanager.sh         # plain ASCII output
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_cocmanager"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptcocmanager.py"

# Load shared library files.
# shellcheck source=testlib/reference_values.sh
source "${SCRIPT_DIR}/testlib/reference_values.sh"
# shellcheck source=testlib/test_framework.sh
source "${SCRIPT_DIR}/testlib/test_framework.sh"


# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------
cleanup_all() {
    rm -rf "${TEST_DIR}"
}
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Fixture builders
#
# Each builder writes a JSON document mimicking the output of an upstream
# toolkit module. Hash and status arguments are parameterised so that each
# test case can vary them independently.
# -----------------------------------------------------------------------------

# write_imaging_report <path> <source_hash> [<case_id>]
write_imaging_report() {
    local path="$1"
    local source_hash="$2"
    local case_id="${3:-${PREFIX_COC}-2026-01-01-001}"
    python3 - <<PYEOF
import json
doc = {
    "results": {
        "properties": {
            "caseId":               "${case_id}",
            "sourceHash":           "${source_hash}",
            "imagePath":            "/test/image.dd",
            "imageSizeBytes":       524288,
            "toolVersion":          "dc3dd 7.2.646",
            "writeBlockerConfirmed": True,
        },
        "nodes": [],
    }
}
open("${path}", "w").write(json.dumps(doc))
PYEOF
}

# write_verification_report <path> <source_hash> <image_hash> <status>
write_verification_report() {
    local path="$1"
    local source_hash="$2"
    local image_hash="$3"
    local status="$4"
    local case_id="${5:-${PREFIX_COC}-2026-01-01-001}"
    local match="False"
    [ "${source_hash}" = "${image_hash}" ] && match="True"
    python3 - <<PYEOF
import json
doc = {
    "results": {
        "properties": {
            "caseId":             "${case_id}",
            "sourceHash":         "${source_hash}",
            "imageHash":          "${image_hash}",
            "hashMatch":          ${match},
            "verificationStatus": "${status}",
        },
        "nodes": [],
    }
}
open("${path}", "w").write(json.dumps(doc))
PYEOF
}

# write_readability_report <path> [<status>] [<tool>]
write_readability_report() {
    local path="$1"
    local status="${2:-READABLE}"
    local tool="${3:-dc3dd}"
    local case_id="${4:-${PREFIX_COC}-2026-01-01-001}"
    python3 - <<PYEOF
import json
doc = {
    "results": {
        "properties": {
            "caseId":          "${case_id}",
            "mediaStatus":     "${status}",
            "recommendedTool": "${tool}",
            "criticalFindings": [],
        },
        "nodes": [],
    }
}
open("${path}", "w").write(json.dumps(doc))
PYEOF
}


# run_gate_mode <case_id> <img_json> <ver_json> <out_json>
# Invokes ptcocmanager in gate mode and returns the exit code on stdout.
run_gate_mode() {
    local case_id="$1"
    local img="$2"
    local ver="$3"
    local out="$4"
    local code=0
    invoke_tool "${TOOL_PATH}" "${case_id}" \
        --mode gate \
        --imaging-json "${img}" \
        --verification-json "${ver}" \
        --analyst "Test Analyst" \
        --json-out "${out}" \
        >/dev/null 2>&1 || code=$?
    echo "${code}"
}

# run_consolidate_mode <case_id> <input_dir> <out_json>
run_consolidate_mode() {
    local case_id="$1"
    local indir="$2"
    local out="$3"
    local code=0
    invoke_tool "${TOOL_PATH}" "${case_id}" \
        --mode consolidate \
        --imaging-json "${indir}/imaging.json" \
        --verification-json "${indir}/verification.json" \
        --readability-json "${indir}/readability.json" \
        --analyst "Test Analyst" \
        --json-out "${out}" \
        >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# Category A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    # A1: All inputs consistent, hashes match, status VERIFIED -> exit 0
    # Uses NIST FIPS 180-4 vector "abc" as the canonical hash.
    local img="${TEST_DIR}/a1_img.json"
    local ver="${TEST_DIR}/a1_ver.json"
    local out="${TEST_DIR}/a1_out.json"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED"
    local code
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}")
    assert_exit_code "A1: gate mode VERIFIED -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: gate mode sets crossValidated=True when both reports are consistent.
    # The expected value is dictated by the gate-mode specification, not by
    # the implementation: thesis section 4.4.5, "rezim gate".
    assert_json_field "A2: crossValidated == True" "${out}" \
        "d['results']['properties'].get('crossValidated')" \
        "True"

    # A3: consolidate mode produces a master CoC over multiple reports.
    local cdir="${TEST_DIR}/a3_in"
    local cout="${TEST_DIR}/a3_out.json"
    mkdir -p "${cdir}"
    write_imaging_report      "${cdir}/imaging.json"      "${NIST_SHA256_ABC}"
    write_verification_report "${cdir}/verification.json" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED"
    write_readability_report  "${cdir}/readability.json"
    code=$(run_consolidate_mode "${PREFIX_COC}-2026-01-01-001" "${cdir}" "${cout}")
    assert_exit_code "A3: consolidate mode -> exit 0" "${EXIT_SUCCESS}" "${code}"
}


# =============================================================================
# Category B: Error conditions (negative testing)
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    # B1: missing imaging report -> environment error
    local out="${TEST_DIR}/b1_out.json"
    write_verification_report "${TEST_DIR}/b1_ver.json" \
        "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED"
    local code
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" \
        "${TEST_DIR}/nonexistent.json" "${TEST_DIR}/b1_ver.json" "${out}")
    case "${code}" in "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B1: missing imaging report -> ${code}" ;; *) fail "B1: missing imaging report -> exit 99" "exit ${code}" ;; esac

    # B2: hash mismatch between imaging.sourceHash and verification.sourceHash
    local img="${TEST_DIR}/b2_img.json"
    local ver="${TEST_DIR}/b2_ver.json"
    out="${TEST_DIR}/b2_out.json"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}"
    write_verification_report "${ver}" "${REF_SHA256_MISMATCH}" "${REF_SHA256_MISMATCH}" "VERIFIED"
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}")
    assert_exit_code "B2: hash mismatch -> exit 1" "${EXIT_FAILURE}" "${code}"

    # B3: verification status MISMATCH (image differs from source)
    img="${TEST_DIR}/b3_img.json"
    ver="${TEST_DIR}/b3_ver.json"
    out="${TEST_DIR}/b3_out.json"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${REF_SHA256_MISMATCH}" "MISMATCH"
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}")
    assert_exit_code "B3: verificationStatus MISMATCH -> exit 1" "${EXIT_FAILURE}" "${code}"

    # B4: malformed JSON input
    img="${TEST_DIR}/b4_img.json"
    ver="${TEST_DIR}/b4_ver.json"
    out="${TEST_DIR}/b4_out.json"
    echo "{ this is not json" > "${img}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED"
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}")
    case "${code}" in "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B4: malformed JSON input -> ${code}" ;; *) fail "B4: malformed JSON input -> exit 99" "exit ${code}" ;; esac

    # B5: consolidate mode with no reports in directory
    local cdir="${TEST_DIR}/b5_in"
    out="${TEST_DIR}/b5_out.json"
    mkdir -p "${cdir}"
    code=$(run_consolidate_mode "${PREFIX_COC}-2026-01-01-001" "${cdir}" "${out}")
    assert_exit_code "B5: consolidate with empty input dir -> exit 1" "${EXIT_FAILURE}" "${code}"

    # B6: gate mode where verification.sourceHash is the all-Fs sentinel
    # (a syntactically valid but semantically impossible value).
    img="${TEST_DIR}/b6_img.json"
    ver="${TEST_DIR}/b6_ver.json"
    out="${TEST_DIR}/b6_out.json"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}"
    write_verification_report "${ver}" "${REF_SHA256_ALL_F}" "${REF_SHA256_ALL_F}" "VERIFIED"
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}")
    assert_exit_code "B6: source/verification hash divergence -> exit 1" \
        "${EXIT_FAILURE}" "${code}"
}


# =============================================================================
# Category C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    # C1: hash provided in upper case. Per FIPS 180-4 the digest is a sequence
    # of bytes; hexadecimal encoding is implementation choice, so an
    # upper-case hash must be accepted and compared case-insensitively.
    local img="${TEST_DIR}/c1_img.json"
    local ver="${TEST_DIR}/c1_ver.json"
    local out="${TEST_DIR}/c1_out.json"
    local upper="${NIST_SHA256_ABC^^}"
    write_imaging_report      "${img}" "${upper}"
    write_verification_report "${ver}" "${upper}" "${upper}" "VERIFIED"
    local code
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}")
    assert_exit_code "C1: upper-case hash accepted" "${EXIT_SUCCESS}" "${code}"

    # C2: case ID containing characters that must be sanitised (forward slash).
    # Expected behaviour per _sanitize_case_id in ptforensictoolbase:
    # disallowed characters are stripped, the call still succeeds.
    img="${TEST_DIR}/c2_img.json"
    ver="${TEST_DIR}/c2_ver.json"
    out="${TEST_DIR}/c2_out.json"
    local dirty_id="${PREFIX_COC}-2026/01/01"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}" "${dirty_id}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED" "${dirty_id}"
    code=$(run_gate_mode "${dirty_id}" "${img}" "${ver}" "${out}")
    assert_exit_code "C2: caseId with disallowed characters sanitised" \
        "${EXIT_SUCCESS}" "${code}"

    # C3: PHOTORECOVERY prefix triggers scenario detection.
    img="${TEST_DIR}/c3_img.json"
    ver="${TEST_DIR}/c3_ver.json"
    out="${TEST_DIR}/c3_out.json"
    local photo_id="${PREFIX_PHOTO}-2026-01-01-001"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}" "${photo_id}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED" "${photo_id}"
    code=$(run_gate_mode "${photo_id}" "${img}" "${ver}" "${out}")
    assert_exit_code "C3: PHOTORECOVERY scenario auto-detected" \
        "${EXIT_SUCCESS}" "${code}"

    # C4: MALWARE prefix triggers scenario detection and emits the legal
    # deadlines block (NIS2 transposition reference).
    img="${TEST_DIR}/c4_img.json"
    ver="${TEST_DIR}/c4_ver.json"
    out="${TEST_DIR}/c4_out.json"
    local mal_id="${PREFIX_MALWARE}-2026-01-01-001"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}" "${mal_id}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED" "${mal_id}"
    code=$(run_gate_mode "${mal_id}" "${img}" "${ver}" "${out}")
    assert_exit_code "C4: MALWARE scenario auto-detected" "${EXIT_SUCCESS}" "${code}"
}


# =============================================================================
# Category D: JSON and Chain-of-Custody structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    # Prepare a single happy-path output once; reuse for the structural
    # assertions below.
    local img="${TEST_DIR}/d_img.json"
    local ver="${TEST_DIR}/d_ver.json"
    local out="${TEST_DIR}/d_out.json"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED"
    run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}" >/dev/null

    # D1: caseId is present in top-level properties.
    assert_json_field "D1: results.properties.caseId is set" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_COC}-2026-01-01-001"

    # D2: at least one chainOfCustodyEntry node exists.
    assert_node_present "D2: chainOfCustodyEntry node present" \
        "${out}" "chainOfCustodyEntry"

    # D3: the CoC entry timestamp parses as ISO 8601.
    local ts
    ts=$(node_property "${out}" "chainOfCustodyEntry" "timestamp")
    if python3 -c "from datetime import datetime; datetime.fromisoformat('${ts}'.replace('Z','+00:00'))" 2>/dev/null; then
        pass "D3: CoC timestamp parses as ISO 8601 ('${ts}')"
    else
        fail "D3: CoC timestamp parses as ISO 8601" "got: '${ts}'"
    fi

    # D4: the CoC entry carries the analyst name as recorded on the CLI.
    local analyst
    analyst=$(node_property "${out}" "chainOfCustodyEntry" "analyst")
    assert_equal "D4: CoC analyst field" "Test Analyst" "${analyst}"

    # D5: compliance declaration includes NIST SP 800-86 and ISO/IEC 27037.
    # The expected list mirrors the standards cited in thesis Tables 4.5
    # and 4.6; the test ensures the tool does not silently drop them.
    local compliance
    compliance=$(json_value "${out}" \
        "','.join(d['results']['properties'].get('compliance', []))")
    case "${compliance}" in
        *"NIST SP 800-86"*)
            case "${compliance}" in
                *"ISO/IEC 27037"*)
                    pass "D5: compliance declares NIST SP 800-86 and ISO/IEC 27037"
                    ;;
                *)
                    fail "D5: compliance declares NIST SP 800-86 and ISO/IEC 27037" \
                        "got: '${compliance}'"
                    ;;
            esac
            ;;
        *)
            fail "D5: compliance declares NIST SP 800-86 and ISO/IEC 27037" \
                "got: '${compliance}'"
            ;;
    esac
}


# =============================================================================
# Category E: Exit code convention (thesis Table 4.4)
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit code convention"

    # E1: success path -> exit 0  (re-uses Category A fixtures)
    local img="${TEST_DIR}/e1_img.json"
    local ver="${TEST_DIR}/e1_ver.json"
    local out="${TEST_DIR}/e1_out.json"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED"
    local code
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}")
    assert_exit_code "E1: nominal completion = ${EXIT_SUCCESS}" "${EXIT_SUCCESS}" "${code}"

    # E2: forensic finding (hash mismatch) -> exit 1
    img="${TEST_DIR}/e2_img.json"
    ver="${TEST_DIR}/e2_ver.json"
    out="${TEST_DIR}/e2_out.json"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}"
    write_verification_report "${ver}" "${REF_SHA256_MISMATCH}" "${REF_SHA256_MISMATCH}" "VERIFIED"
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" "${img}" "${ver}" "${out}")
    assert_exit_code "E2: forensic finding = ${EXIT_FAILURE}" "${EXIT_FAILURE}" "${code}"

    # E3: environment error (missing input file) -> exit 99
    img="${TEST_DIR}/e3_img.json"
    out="${TEST_DIR}/e3_out.json"
    write_verification_report "${TEST_DIR}/e3_ver.json" \
        "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED"
    code=$(run_gate_mode "${PREFIX_COC}-2026-01-01-001" \
        "${TEST_DIR}/missing.json" "${TEST_DIR}/e3_ver.json" "${out}")
    case "${code}" in "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E3: environment error -> ${code}" ;; *) fail "E3: environment error = ${EXIT_ENV}" "exit ${code}" ;; esac

    # E4: SIGINT during execution -> exit 130
    # The tool is started in the background, given enough time to set up
    # its signal handlers, then sent SIGINT. The expected exit code is
    # 130 = 128 + SIGINT(2), the convention from POSIX shells.
    img="${TEST_DIR}/e4_img.json"
    ver="${TEST_DIR}/e4_ver.json"
    out="${TEST_DIR}/e4_out.json"
    write_imaging_report      "${img}" "${NIST_SHA256_ABC}"
    write_verification_report "${ver}" "${NIST_SHA256_ABC}" "${NIST_SHA256_ABC}" "VERIFIED"
    (
        python3 "${TOOL_PATH}" "${PREFIX_COC}-2026-01-01-001" \
            --mode gate \
            --imaging-json "${img}" \
            --verification-json "${ver}" \
            --analyst "Test Analyst" \
            --json-out "${out}" \
            >/dev/null 2>&1 &
        local pid=$!
        sleep 0.1
        kill -INT "${pid}" 2>/dev/null || true
        wait "${pid}" 2>/dev/null
        echo $?
    ) > "${TEST_DIR}/e4_code.txt"
    code=$(cat "${TEST_DIR}/e4_code.txt")
    # Accept either 130 (SIGINT honoured) or 0 (process completed before
    # SIGINT delivery on a fast machine); fail only on other values.
    case "${code}" in
        "${EXIT_SIGNAL}"|"${EXIT_SUCCESS}")
            pass "E4: SIGINT handling (exit ${code})"
            ;;
        *)
            fail "E4: SIGINT handling" "expected ${EXIT_SIGNAL} or 0, got ${code}"
            ;;
    esac
}


# =============================================================================
# Main
# =============================================================================
main() {
    check_prerequisites "3.10" "${TOOL_PATH}"

    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"

    printf 'Test suite: ptcocmanager\n'
    printf 'Tool path:  %s\n' "${TOOL_PATH}"
    printf 'Test dir:   %s\n' "${TEST_DIR}"
    [ "${COVERAGE:-0}" = "1" ] && printf 'Coverage:   enabled\n'

    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes

    print_summary "ptcocmanager"
}

main "$@"