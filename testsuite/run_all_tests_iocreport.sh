#!/usr/bin/env bash
#
# run_all_tests_iocreport.sh
#
# Unit test suite for ptiocreport.py
# Validates the consolidation of IoCs from upstream stages into a
# unified report with three categories: fileHashes, networkIndicators,
# hostIndicators. The module performs only data transformation -- no
# external tools.
#
# Coverage: 15 tests in 5 categories per chapter 5.4.3 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_iocreport"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptiocreport.py"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Fixture builders
# -----------------------------------------------------------------------------

# Artefacts JSON in the shape that ptartefactextractor produces and
# ptiocreport.load_network_artefacts() consumes.
write_artefacts_file() {
    python3 - <<PYEOF
import json
doc = {
    "results": {
        "properties": {
            "caseId": "${PREFIX_MALWARE}-2026-01-01-001",
            "networkIndicators": {
                "ipAddresses": ["203.0.113.45", "198.51.100.10"],
                "urls": ["https://${RFC2606_EXAMPLE_TLD}/api/cmd"],
                "domains": ["${RFC2606_EXAMPLE_TLD}"],
                "emails": []
            },
            "registryPersistence": [
                {"registryPath": "Software/Run/dropper",
                 "command": "/Users/Public/dropper.exe"}
            ]
        },
        "nodes": []
    }
}
open("${TEST_DIR}/artefacts.json", "w").write(json.dumps(doc))
PYEOF
}

# Artefacts JSON with all IoC sections empty
write_empty_artefacts_file() {
    python3 - <<PYEOF
import json
doc = {
    "results": {
        "properties": {
            "networkIndicators": {
                "ipAddresses": [], "urls": [], "domains": [], "emails": []
            },
            "registryPersistence": []
        },
        "nodes": []
    }
}
open("${TEST_DIR}/artefacts_empty.json", "w").write(json.dumps(doc))
PYEOF
}

# Hashes file in sha256sum format: "<64 hex>  <path>" per line.
# The tool's filter accepts lines with exactly 64-char first field --
# hex validity is NOT checked, only length, but using real FIPS vectors
# here keeps the fixture honest.
write_hashes_file() {
    {
        printf '%s  /Windows/Temp/malware.exe\n' "${NIST_SHA256_ABC}"
        printf '%s  /ProgramData/dropper.ps1\n' "${NIST_SHA256_EMPTY}"
    } > "${TEST_DIR}/hashes.txt"
}

# Hashes file with one valid line and two malformed lines (filter should
# drop the malformed ones).
write_mixed_hashes_file() {
    {
        printf '%s  /valid.exe\n' "${NIST_SHA256_ABC}"
        # Short hash (8 chars instead of 64) -- dropped by length filter
        printf 'deadbeef  /short.exe\n'
        # Single field, no path -- dropped (only 1 part after split)
        printf '%s\n' "${NIST_SHA256_EMPTY}"
    } > "${TEST_DIR}/hashes_mixed.txt"
}

# Invoke ptiocreport with a writable --output-dir (production default
# is /var/forensics/analysis and requires sudo).
run_tool() {
    local case_id="$1" out="$2"
    local artefacts="${3:-${TEST_DIR}/artefacts.json}"
    local hashes_file="${4:-}"
    local code=0
    if [ -n "${hashes_file}" ]; then
        invoke_tool "${TOOL_PATH}" "${case_id}" "${artefacts}" \
            --hashes-file "${hashes_file}" \
            --output-dir "${TEST_DIR}/out" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    else
        invoke_tool "${TOOL_PATH}" "${case_id}" "${artefacts}" \
            --output-dir "${TEST_DIR}/out" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    fi
    echo "${code}"
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    write_artefacts_file
    write_hashes_file

    local out="${TEST_DIR}/a.json"
    local code
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-001" "${out}" \
        "${TEST_DIR}/artefacts.json" "${TEST_DIR}/hashes.txt")
    assert_exit_code "A1: consolidation -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: fileHashes from the --hashes-file (sha256sum format text)
    local file_count
    file_count=$(json_value "${out}" \
        "len(d['results']['properties']['iocReport']['ioc']['fileHashes'])")
    assert_equal "A2: 2 file hashes loaded from hashes.txt" \
        "2" "${file_count}"

    # A3: networkIndicators populated (2 IPs, 1 URL, 1 domain)
    local ip_count
    ip_count=$(json_value "${out}" \
        "len(d['results']['properties']['iocReport']['ioc']['networkIndicators']['ipAddresses'])")
    assert_equal "A3: 2 IP addresses" "2" "${ip_count}"

    # A4: hostIndicators populated (1 registry persistence entry)
    local reg_count
    reg_count=$(json_value "${out}" \
        "len(d['results']['properties']['iocReport']['ioc']['hostIndicators']['registryPersistence'])")
    assert_equal "A4: 1 registry persistence entry" "1" "${reg_count}"
}

# =============================================================================
# B: Error / missing-input handling
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    # B1: nonexistent artefacts file -> load_network_artefacts() fails
    # -> run() returns False -> main() returns 99.
    local code
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-001" "${TEST_DIR}/b1.json" \
        "${TEST_DIR}/no_such_artefacts.json")
    assert_exit_code "B1: missing artefacts file -> 99" "${EXIT_ENV}" "${code}"

    # B2: malformed artefacts JSON. _load_json() catches the parse
    # exception and returns {}, so the consolidation proceeds with all
    # zero counts. This is documented tolerant behavior, not a bug;
    # the assertion records the resulting totalIoc.
    echo "{ not valid json" > "${TEST_DIR}/malformed.json"
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-002" "${TEST_DIR}/b2.json" \
        "${TEST_DIR}/malformed.json")
    assert_exit_code "B2: malformed JSON tolerated -> exit 0" \
        "${EXIT_SUCCESS}" "${code}"
    local total
    total=$(json_value "${TEST_DIR}/b2.json" \
        "d['results']['properties'].get('totalIoc', -1)")
    assert_equal "B2: malformed JSON yields totalIoc=0" "0" "${total}"

    # B3: artefacts only, no --hashes-file -> exit 0, fileHashes empty.
    write_artefacts_file
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-003" "${TEST_DIR}/b3.json")
    assert_exit_code "B3: artefacts-only -> exit 0" "${EXIT_SUCCESS}" "${code}"
    local fh
    fh=$(json_value "${TEST_DIR}/b3.json" \
        "len(d['results']['properties']['iocReport']['ioc']['fileHashes'])")
    assert_equal "B3: no hashes file -> fileHashes empty" "0" "${fh}"
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    # C1: empty IoC sections in artefacts file -> all counts 0, exit 0.
    write_empty_artefacts_file
    local out="${TEST_DIR}/c1.json"
    local code
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-001" "${out}" \
        "${TEST_DIR}/artefacts_empty.json")
    assert_exit_code "C1: empty IoC sections -> exit 0" \
        "${EXIT_SUCCESS}" "${code}"
    local total
    total=$(json_value "${out}" \
        "d['results']['properties'].get('totalIoc', -1)")
    assert_equal "C1: totalIoc=0 with empty inputs" "0" "${total}"

    # C2: malformed lines in hashes file. The tool's filter accepts only
    # lines whose first whitespace-separated token is exactly 64 chars,
    # so the short-hash line and the single-field line are dropped, and
    # only the valid line survives.
    write_artefacts_file
    write_mixed_hashes_file
    out="${TEST_DIR}/c2.json"
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-002" "${out}" \
        "${TEST_DIR}/artefacts.json" "${TEST_DIR}/hashes_mixed.txt")
    assert_exit_code "C2: mixed hashes file -> exit 0" \
        "${EXIT_SUCCESS}" "${code}"
    local kept
    kept=$(json_value "${out}" \
        "len(d['results']['properties']['iocReport']['ioc']['fileHashes'])")
    assert_equal "C2: only 1 valid hash line kept" "1" "${kept}"

    # C3: duplicate lines in hashes file are NOT deduplicated at this
    # stage (the loader appends without checking). 3 identical lines
    # produce 3 fileHashes entries -- documenting the tool's behavior
    # so a future change can be detected.
    {
        printf '%s  /a.exe\n' "${NIST_SHA256_ABC}"
        printf '%s  /a.exe\n' "${NIST_SHA256_ABC}"
        printf '%s  /a.exe\n' "${NIST_SHA256_ABC}"
    } > "${TEST_DIR}/hashes_dup.txt"
    out="${TEST_DIR}/c3.json"
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-003" "${out}" \
        "${TEST_DIR}/artefacts.json" "${TEST_DIR}/hashes_dup.txt")
    local dup_count
    dup_count=$(json_value "${out}" \
        "len(d['results']['properties']['iocReport']['ioc']['fileHashes'])")
    assert_equal "C3: 3 duplicate lines all loaded (no dedup at this stage)" \
        "3" "${dup_count}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    write_artefacts_file
    write_hashes_file
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_MALWARE}-2026-01-01-001" "${out}" \
        "${TEST_DIR}/artefacts.json" "${TEST_DIR}/hashes.txt" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_MALWARE}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: iocReport.ioc has all three IoC categories.
    local has_all
    has_all=$(json_value "${out}" "
int(all(k in d['results']['properties']['iocReport']['ioc']
        for k in ('fileHashes', 'networkIndicators', 'hostIndicators')))")
    assert_equal "D3: 3 IoC categories present under iocReport.ioc" \
        "1" "${has_all}"

    # D4: totalIoc matches the sum of category lengths.
    # Sum = 2 hashes + 2 IPs + 1 URL + 1 domain + 1 registry = 7.
    # (emails are counted by the tool's `total` but are zero here, so
    # totalIoc should equal 7.)
    local total
    total=$(json_value "${out}" \
        "d['results']['properties'].get('totalIoc', -1)")
    assert_equal "D4: totalIoc matches expected count" "7" "${total}"
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    write_artefacts_file
    write_hashes_file

    # E1: success
    local code
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-001" "${TEST_DIR}/e1.json" \
        "${TEST_DIR}/artefacts.json" "${TEST_DIR}/hashes.txt")
    assert_exit_code "E1: success -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: missing artefacts file -> 99
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-002" "${TEST_DIR}/e2.json" \
        "${TEST_DIR}/no_such_file.json")
    assert_exit_code "E2: missing artefacts -> 99" "${EXIT_ENV}" "${code}"

    # E3: malformed JSON -> 0 (tolerant; see B2).
    echo "{{{" > "${TEST_DIR}/junk.json"
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-003" "${TEST_DIR}/e3.json" \
        "${TEST_DIR}/junk.json")
    assert_exit_code "E3: malformed JSON tolerated -> 0" \
        "${EXIT_SUCCESS}" "${code}"
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptiocreport\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptiocreport"
}

main "$@"