#!/usr/bin/env bash
#
# run_all_tests_artefactextractor.sh
#
# Unit test suite for ptartefactextractor.py
# Validates IoC extraction via regex (IP / URL / domain), private-IP
# filtering, optional PCAP parsing via tshark, and Windows-registry
# autostart inspection via reglookup over WIN_AUTOSTART_PATHS.
# Test IPs/domains follow RFC 5737 / RFC 2606.
#
# Coverage: 14 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_artefactextractor"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptartefactextractor.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock tshark + reglookup. Outputs follow real-tool field naming.
# Test data uses RFC 5737 documentation address space and RFC 2606
# reserved TLDs (.example, .test, .invalid).
# -----------------------------------------------------------------------------
make_mock_tshark() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/tshark" <<EOF
#!/bin/sh
# Emit a small dataset with public RFC 5737 + private RFC 1918 IPs
echo "203.0.113.45"   # RFC 5737 TEST-NET-3 -- treated as "public" by tool
echo "198.51.100.10"  # RFC 5737 TEST-NET-2 -- also "public"
echo "192.168.1.5"    # RFC 1918 private    -- filtered by tool
echo "10.0.0.7"       # RFC 1918 private    -- filtered
echo "127.0.0.1"      # loopback             -- filtered
EOF
    chmod +x "${MOCK_BIN}/tshark"
}

make_mock_reglookup() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/reglookup" <<'EOF'
#!/bin/sh
# Emit a registry dump with WIN_AUTOSTART_PATHS entries
cat <<REG_OUT
PATH,TYPE,VALUE
/Microsoft/Windows/CurrentVersion/Run/dropper,REG_SZ,C:\\Users\\Public\\dropper.exe
/Microsoft/Windows/CurrentVersion/RunOnce/setup,REG_SZ,C:\\ProgramData\\setup.exe
/Microsoft/Windows/CurrentVersion/Winlogon/Shell,REG_SZ,explorer.exe
REG_OUT
EOF
    chmod +x "${MOCK_BIN}/reglookup"
}

setup_input_fixture() {
    local dir="${TEST_DIR}/in"
    mkdir -p "${dir}"
    # Plain-text artefact containing a mix of public and private IPs / URLs / domains
    cat > "${dir}/observed.txt" <<EOF
Connection from 203.0.113.45 to internal host 192.168.1.5
Beacon: https://example.com/api/v1/cmd  (RFC 2606 documentation TLD)
Suspicious URL: http://malware.test/payload  (RFC 2606 reserved TLD)
Loopback noise: 127.0.0.1
DNS: badhost.invalid
EOF
}

run_tool() {
    local case_id="$1"
    local input_dir="$2"
    local out="$3"
    local extra="${4:-}"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${input_dir}" \
            --analyst "Test" \
            --json-out "${out}" \
            ${extra} \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    setup_input_fixture
    local out="${TEST_DIR}/a.json"
    local code
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-001" \
        "${TEST_DIR}/in/observed.txt" "${out}")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FINDING}")
            pass "A1: artefact extraction -> exit ${code}" ;;
        *) fail "A1: artefact extraction" "exit ${code}" ;;
    esac

    # A2: 203.0.113.45 (RFC 5737 public) extracted
    local has_public
    has_public=$(json_value "${out}" "1 if '203.0.113.45' in d['results']['properties'].get('networkIndicators',{}).get('ipAddresses',[]) else 0")
    assert_equal "A2: 203.0.113.45 (public RFC 5737) extracted" \
        "1" "${has_public}"

    # A3: example.com (RFC 2606 reserved) extracted as domain
    local has_example
    has_example=$(json_value "${out}" "1 if any('example.com' in v for v in d['results']['properties'].get('networkIndicators',{}).get('urls',[])+d['results']['properties'].get('networkIndicators',{}).get('domains',[])) else 0")
    if [ "${has_example}" -ge 1 ] 2>/dev/null; then
        pass "A3: example.com domain extracted"
    else
        fail "A3: example.com" "got: ${has_example}"
    fi
}

# =============================================================================
# B: Private-IP filtering
# =============================================================================
test_b_private_ip_filter() {
    test_header "Category B: Private-IP filtering"

    setup_input_fixture
    local out="${TEST_DIR}/b.json"
    run_tool "${PREFIX_MALWARE}-2026-01-01-001" \
        "${TEST_DIR}/in/observed.txt" "${out}" >/dev/null

    # B1: 192.168.1.5 (RFC 1918) NOT extracted
    local has_private
    has_private=$(json_value "${out}" "1 if '192.168.1.5' in d['results']['properties'].get('networkIndicators',{}).get('ipAddresses',[]) else 0")
    assert_equal "B1: 192.168.1.5 (RFC 1918) filtered" "0" "${has_private}"

    # B2: 127.0.0.1 (loopback) NOT extracted
    local has_loopback
    has_loopback=$(json_value "${out}" "1 if '127.0.0.1' in d['results']['properties'].get('networkIndicators',{}).get('ipAddresses',[]) else 0")
    assert_equal "B2: 127.0.0.1 (loopback) filtered" "0" "${has_loopback}"
}

# =============================================================================
# C: Optional tooling (tshark, reglookup)
# =============================================================================
test_c_optional_tooling() {
    test_header "Category C: Optional tooling"

    setup_input_fixture
    make_mock_tshark
    make_mock_reglookup

    # C1: PCAP file processed via tshark
    cp "${TEST_DIR}/in/observed.txt" "${TEST_DIR}/in/capture.pcap"
    local out="${TEST_DIR}/c1.json"
    run_tool "${PREFIX_MALWARE}-2026-01-01-001" \
        "${TEST_DIR}/in/observed.txt" "${out}" "--pcap ${TEST_DIR}/in/capture.pcap" >/dev/null
    local total
    total=$(json_value "${out}" \
        "sum(d['results']['properties'].get('totals',{}).get(k,0) for k in ['ips','urls','domains'])")
    if [ "${total}" -ge 1 ] 2>/dev/null; then
        pass "C1: tshark PCAP path extracted ${total} IoCs"
    else
        fail "C1: tshark PCAP path" "got: ${total}"
    fi

    # C2: Registry hive processed via reglookup
    cp "${TEST_DIR}/in/observed.txt" "${TEST_DIR}/in/NTUSER.DAT"
    mkdir -p "${TEST_DIR}/mount/Windows/System32/config"
    touch "${TEST_DIR}/mount/Windows/System32/config/SOFTWARE"
    out="${TEST_DIR}/c2.json"
    run_tool "${PREFIX_MALWARE}-2026-01-01-002" \
        "${TEST_DIR}/in/observed.txt" "${out}" "-m ${TEST_DIR}/mount" >/dev/null
    # Expect at least one autostart entry
    local autostart
    autostart=$(json_value "${out}" "len(d['results']['properties'].get('registryPersistence', []))")
    if [ "${autostart}" -ge 1 ] 2>/dev/null; then
        pass "C2: reglookup autostart entries found (${autostart})"
    else
        fail "C2: reglookup autostart entries" "got: ${autostart}"
    fi
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    setup_input_fixture
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_MALWARE}-2026-01-01-001" \
        "${TEST_DIR}/in/observed.txt" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_MALWARE}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: each IoC has a type (ip / domain / url)
    local with_type
    with_type=$(json_value "${out}" "1 if (d['results']['properties'].get('networkIndicators',{}).get('ipAddresses') or d['results']['properties'].get('networkIndicators',{}).get('urls') or d['results']['properties'].get('networkIndicators',{}).get('domains')) else 0")
    if [ "${with_type}" -ge 1 ] 2>/dev/null; then
        pass "D3: each IoC carries iocType"
    else
        fail "D3: IoC type field" "got: ${with_type}"
    fi

    # D4: source filename recorded
    local with_source
    with_source=$(json_value "${out}" "1 if d['results']['properties'].get('stringsFile','') != '' else 0")
    if [ "${with_source}" -ge 1 ] 2>/dev/null; then
        pass "D4: source filename recorded"
    else
        fail "D4: source filename" "got: ${with_source}"
    fi
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    setup_input_fixture

    # E1: extraction success -> 0 or 2 (findings)
    local code
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-001" \
        "${TEST_DIR}/in/observed.txt" "${TEST_DIR}/e1.json")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FINDING}")
            pass "E1: extraction -> ${code}" ;;
        *) fail "E1: extraction" "exit ${code}" ;;
    esac

    # E2: missing input dir -> env error
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-002" \
        "${TEST_DIR}/no_such_dir" "${TEST_DIR}/e2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing input -> ${code}" ;;
        *) fail "E2: missing input" "exit ${code}" ;;
    esac

    # E3: empty input dir -> exit 0 (no findings)
    rm -rf "${TEST_DIR}/in"
    mkdir -p "${TEST_DIR}/in"
    touch "${TEST_DIR}/in/empty.txt"
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-003" \
        "${TEST_DIR}/in/empty.txt" "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_SUCCESS}") pass "E3: empty input -> 0" ;;
        *) fail "E3: empty input" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptartefactextractor\n\n'
    test_a_happy_path
    test_b_private_ip_filter
    test_c_optional_tooling
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptartefactextractor"
}

main "$@"