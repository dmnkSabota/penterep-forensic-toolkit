#!/usr/bin/env bash
#
# run_all_tests_threatintel.sh
#
# Unit test suite for ptthreatintel.py
# Validates VirusTotal API v3 and AlienVault OTX queries via a urllib
# monkey-patch wrapper, offline-mode behaviour, batch caps
# (VT_MAX_HASHES = 10, VT_MAX_IPS = 5), and IoC report parsing.
#
# Coverage: 5 categories per chapter 5.4.3 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_threatintel"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptthreatintel.py"
MOCK_WRAPPER="${TEST_DIR}/url_mock_wrapper.py"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Build the urllib monkey-patch wrapper.
# -----------------------------------------------------------------------------
make_mock_wrapper() {
    cat > "${MOCK_WRAPPER}" <<'PYEOF'
#!/usr/bin/env python3
"""urllib monkey-patch wrapper for ptthreatintel unit tests."""
import json
import os
import sys
import time
import urllib.request

CALL_LOG = os.environ.get("MOCK_CALL_LOG", "")


class _MockResponse:
    def __init__(self, body):
        self._body = body.encode() if isinstance(body, str) else body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


def _log_call(url):
    if CALL_LOG:
        try:
            with open(CALL_LOG, "a") as fh:
                fh.write(url + "\n")
        except Exception:
            pass


def _mock_urlopen(req, *args, **kwargs):
    url = req.get_full_url() if hasattr(req, "get_full_url") else str(req)
    _log_call(url)
    if "/api/v3/files/" in url:
        body = {"data": {"attributes": {
            "last_analysis_stats": {
                "malicious": 12, "suspicious": 3,
                "undetected": 50, "harmless": 5,
            },
            "names": ["malware.exe"],
            "popular_threat_classification": {
                "suggested_threat_label": "trojan/generic",
            },
            "tags": ["peexe", "trojan"],
        }}}
        return _MockResponse(json.dumps(body))
    if "/api/v3/ip_addresses/" in url:
        ip = url.rsplit("/", 1)[-1]
        mal = 8 if "203.0.113.45" in ip else 0
        body = {"data": {"attributes": {
            "last_analysis_stats": {
                "malicious": mal, "suspicious": 0,
                "undetected": 60, "harmless": 20,
            },
            "country": "US",
            "as_owner": "TestNet AS",
        }}}
        return _MockResponse(json.dumps(body))
    if "/indicators/" in url:
        body = {
            "pulse_info": {"count": 2},
            "reputation": -5,
            "country_name": "US",
        }
        return _MockResponse(json.dumps(body))
    return _MockResponse(json.dumps({"error": "not found"}))


urllib.request.urlopen = _mock_urlopen
time.sleep = lambda *a, **kw: None

# Critical: prepend the tool's directory to sys.path so the tool's
# module-level `from _version import __version__` fallback resolves.
# Without this, the import crashes before main() is ever called and
# Python exits 1 with no other signal.
tool_path = sys.argv[1]
tool_dir = os.path.dirname(os.path.abspath(tool_path))
sys.path.insert(0, tool_dir)

sys.argv = [tool_path] + sys.argv[2:]
with open(tool_path) as fh:
    code = fh.read()
try:
    exec(compile(code, tool_path, "exec"),
         {"__name__": "__main__", "__file__": tool_path})
except SystemExit:
    raise
except BaseException as exc:
    import traceback
    sys.stderr.write(f"[mock-wrapper] tool crashed before main(): {exc}\n")
    traceback.print_exc()
    sys.exit(99)
PYEOF
    chmod +x "${MOCK_WRAPPER}"
}


# -----------------------------------------------------------------------------
# Build an IoC report in the exact shape load_ioc() expects.
# -----------------------------------------------------------------------------
write_ioc_report() {
    local out="$1"
    local case_id="$2"
    local hashes_python="${3:-[]}"
    local ips_python="${4:-[]}"
    python3 - <<PYEOF
import json
doc = {
    "results": {
        "properties": {
            "caseId": "${case_id}",
            "iocReport": {
                "ioc": {
                    "fileHashes": ${hashes_python},
                    "networkIndicators": {
                        "ipAddresses": ${ips_python},
                    },
                },
            },
        },
        "nodes": [],
    },
}
open("${out}", "w").write(json.dumps(doc, indent=2))
PYEOF
}


# -----------------------------------------------------------------------------
# run_tool_offline: empty VT/OTX keys -> offline branches.
# -----------------------------------------------------------------------------
run_tool_offline() {
    local case_id="$1"
    local ioc_file="$2"
    local out="$3"
    local code=0
    VT_API_KEY="" OTX_API_KEY="" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${ioc_file}" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# -----------------------------------------------------------------------------
# run_tool_mocked: routes through the urllib monkey-patch wrapper.
# Coverage instrumentation (COVERAGE=1) is intentionally bypassed
# because the wrapper changes the entry point.
# -----------------------------------------------------------------------------
run_tool_mocked() {
    local case_id="$1"
    local ioc_file="$2"
    local out="$3"
    local code=0
    MOCK_CALL_LOG="${TEST_DIR}/calls.log" \
        python3 "${MOCK_WRAPPER}" "${TOOL_PATH}" "${case_id}" "${ioc_file}" \
            --vt-key "test-vt-key" --otx-key "test-otx-key" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path -- urllib-mocked VT + OTX lookups
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    : > "${TEST_DIR}/calls.log"
    write_ioc_report "${TEST_DIR}/a_iocs.json" \
        "${PREFIX_MALWARE}-2026-01-01-A01" \
        '[{"sha256": "'"${NIST_SHA256_ABC}"'", "filename": "malware.exe"},
          {"sha256": "'"${NIST_SHA256_EMPTY}"'", "filename": "dropper.exe"}]' \
        '["203.0.113.45", "198.51.100.10"]'

    local out="${TEST_DIR}/a.json"
    local code
    code=$(run_tool_mocked "${PREFIX_MALWARE}-2026-01-01-A01" \
        "${TEST_DIR}/a_iocs.json" "${out}")
    assert_exit_code "A1: mocked lookups -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: vtResults with malicious > 0. Mock marks every file
    # malicious=12, so 2 hashes -> 2 malicious records.
    local mal_count
    mal_count=$(json_value "${out}" "
sum(1 for r in d['results']['properties'].get('vtResults', [])
    if r.get('malicious', 0) > 0)")
    if [ "${mal_count:-0}" -ge 1 ] 2>/dev/null; then
        pass "A2: ${mal_count} malicious VT result(s) recorded"
    else
        fail "A2: malicious VT result" "got: ${mal_count}"
    fi

    # A3: otxResults with pulseCount > 0.
    local pulse_count
    pulse_count=$(json_value "${out}" "
sum(1 for r in d['results']['properties'].get('otxResults', [])
    if r.get('pulseCount', 0) > 0)")
    if [ "${pulse_count:-0}" -ge 1 ] 2>/dev/null; then
        pass "A3: ${pulse_count} OTX result(s) with pulse data"
    else
        fail "A3: OTX pulse data" "got: ${pulse_count}"
    fi

    # A4: keyFindings populated when malicious results detected.
    local findings_count
    findings_count=$(json_value "${out}" \
        "len(d['results']['properties'].get('keyFindings', []))")
    if [ "${findings_count:-0}" -ge 1 ] 2>/dev/null; then
        pass "A4: keyFindings populated (${findings_count} entries)"
    else
        fail "A4: keyFindings populated" "got: ${findings_count}"
    fi
}


# =============================================================================
# B: Offline mode (no API keys)
# =============================================================================
test_b_offline_mode() {
    test_header "Category B: Offline mode"

    write_ioc_report "${TEST_DIR}/b_iocs.json" \
        "${PREFIX_MALWARE}-2026-01-01-B01" \
        '[{"sha256": "'"${NIST_SHA256_ABC}"'", "filename": "x.exe"}]' \
        '["203.0.113.45"]'

    local out="${TEST_DIR}/b.json"
    local code
    code=$(run_tool_offline "${PREFIX_MALWARE}-2026-01-01-B01" \
        "${TEST_DIR}/b_iocs.json" "${out}")
    assert_exit_code "B1: offline run -> exit 0" "${EXIT_SUCCESS}" "${code}"

    local vt_avail otx_avail
    vt_avail=$(json_value "${out}" \
        "d['results']['properties'].get('vtAvailable')")
    otx_avail=$(json_value "${out}" \
        "d['results']['properties'].get('otxAvailable')")
    if [ "${vt_avail}" = "False" ] && [ "${otx_avail}" = "False" ]; then
        pass "B2: vtAvailable=False, otxAvailable=False"
    else
        fail "B2: offline-mode signal" \
             "vtAvailable=${vt_avail}, otxAvailable=${otx_avail}"
    fi

    local vt_skipped otx_skipped
    vt_skipped=$(node_property "${out}" "virusTotalLookup" "skipped")
    otx_skipped=$(node_property "${out}" "otxLookup" "skipped")
    if [ "${vt_skipped}" = "True" ] && [ "${otx_skipped}" = "True" ]; then
        pass "B3: both lookup nodes skipped=True"
    else
        fail "B3: lookup nodes skipped" \
             "vt=${vt_skipped}, otx=${otx_skipped}"
    fi
}


# =============================================================================
# C: Batch caps + edge cases
# =============================================================================
test_c_limits() {
    test_header "Category C: Batch caps + edge cases"

    # C1: VT_MAX_HASHES = 10 enforced. Fixture supplies 15 distinct
    # hashes; we count /api/v3/files/ entries in MOCK_CALL_LOG.
    local hashes_python
    hashes_python=$(python3 -c "
import json
print(json.dumps([
    {'sha256': format(i, '064x'), 'filename': f'f{i:02d}.exe'}
    for i in range(15)
]))")
    write_ioc_report "${TEST_DIR}/c1_iocs.json" \
        "${PREFIX_MALWARE}-2026-01-01-C01" \
        "${hashes_python}" "[]"

    : > "${TEST_DIR}/calls.log"
    run_tool_mocked "${PREFIX_MALWARE}-2026-01-01-C01" \
        "${TEST_DIR}/c1_iocs.json" "${TEST_DIR}/c1.json" >/dev/null

    local file_calls
    file_calls=$(grep -c '/api/v3/files/' "${TEST_DIR}/calls.log" 2>/dev/null)
    file_calls=${file_calls:-0}
    if [ "${file_calls}" -le 10 ] && [ "${file_calls}" -ge 1 ]; then
        pass "C1: VT_MAX_HASHES enforced (file calls=${file_calls} <= 10)"
    else
        fail "C1: VT_MAX_HASHES" \
             "expected 1..10 file calls, got ${file_calls}"
    fi

    # C2: VT_MAX_IPS = 5 enforced. Fixture supplies 7 IPs.
    local ips_python
    ips_python=$(python3 -c "
import json
print(json.dumps([f'192.0.2.{i+1}' for i in range(7)]))")
    write_ioc_report "${TEST_DIR}/c2_iocs.json" \
        "${PREFIX_MALWARE}-2026-01-01-C02" \
        "[]" "${ips_python}"

    : > "${TEST_DIR}/calls.log"
    run_tool_mocked "${PREFIX_MALWARE}-2026-01-01-C02" \
        "${TEST_DIR}/c2_iocs.json" "${TEST_DIR}/c2.json" >/dev/null

    local ip_calls
    ip_calls=$(grep -c '/api/v3/ip_addresses/' "${TEST_DIR}/calls.log" 2>/dev/null)
    ip_calls=${ip_calls:-0}
    if [ "${ip_calls}" -le 5 ] && [ "${ip_calls}" -ge 1 ]; then
        pass "C2: VT_MAX_IPS enforced (IP calls=${ip_calls} <= 5)"
    else
        fail "C2: VT_MAX_IPS" \
             "expected 1..5 IP calls, got ${ip_calls}"
    fi

    # C3: empty IoC fixture -> no lookups, totalLookups=0, exit 0.
    write_ioc_report "${TEST_DIR}/c3_iocs.json" \
        "${PREFIX_MALWARE}-2026-01-01-C03" "[]" "[]"
    local code
    code=$(run_tool_offline "${PREFIX_MALWARE}-2026-01-01-C03" \
        "${TEST_DIR}/c3_iocs.json" "${TEST_DIR}/c3.json")
    assert_exit_code "C3: empty IoCs -> exit 0" "${EXIT_SUCCESS}" "${code}"

    local total
    total=$(json_value "${TEST_DIR}/c3.json" \
        "d['results']['properties'].get('totalLookups', -1)")
    assert_equal "C3: empty IoCs -> totalLookups=0" "0" "${total}"
}


# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    write_ioc_report "${TEST_DIR}/d_iocs.json" \
        "${PREFIX_MALWARE}-2026-01-01-D01" \
        '[{"sha256": "'"${NIST_SHA256_ABC}"'", "filename": "x.exe"}]' \
        '["203.0.113.45"]'

    local out="${TEST_DIR}/d.json"
    run_tool_offline "${PREFIX_MALWARE}-2026-01-01-D01" \
        "${TEST_DIR}/d_iocs.json" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_MALWARE}-2026-01-01-D01"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    local vt_av otx_av
    vt_av=$(json_value "${out}" \
        "d['results']['properties'].get('vtAvailable')")
    otx_av=$(json_value "${out}" \
        "d['results']['properties'].get('otxAvailable')")
    if [ "${vt_av}" = "False" ] && [ "${otx_av}" = "False" ]; then
        pass "D3: vtAvailable + otxAvailable both bool(False)"
    else
        fail "D3: vtAvailable / otxAvailable" \
             "vt=${vt_av}, otx=${otx_av}"
    fi

    local hashes_loaded ips_loaded
    hashes_loaded=$(node_property "${out}" "iocLoad" "hashesLoaded")
    ips_loaded=$(node_property "${out}" "iocLoad" "ipsLoaded")
    if [ "${hashes_loaded}" = "1" ] && [ "${ips_loaded}" = "1" ]; then
        pass "D4: iocLoad recorded hashesLoaded=1, ipsLoaded=1"
    else
        fail "D4: iocLoad counts" \
             "hashesLoaded=${hashes_loaded}, ipsLoaded=${ips_loaded}"
    fi
}


# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    write_ioc_report "${TEST_DIR}/e_iocs.json" \
        "${PREFIX_MALWARE}-2026-01-01-E01" \
        '[{"sha256": "'"${NIST_SHA256_ABC}"'", "filename": "x.exe"}]' \
        '[]'

    local code
    code=$(run_tool_offline "${PREFIX_MALWARE}-2026-01-01-E01" \
        "${TEST_DIR}/e_iocs.json" "${TEST_DIR}/e1.json")
    assert_exit_code "E1: offline -> 0" "${EXIT_SUCCESS}" "${code}"

    code=$(run_tool_offline "${PREFIX_MALWARE}-2026-01-01-E02" \
        "${TEST_DIR}/does_not_exist.json" "${TEST_DIR}/e2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing IoC file -> ${code}" ;;
        *) fail "E2: missing IoC file" "exit ${code}" ;;
    esac
}


main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    make_mock_wrapper
    printf 'Test suite: ptthreatintel\n\n'
    test_a_happy_path
    test_b_offline_mode
    test_c_limits
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptthreatintel"
}

main "$@"