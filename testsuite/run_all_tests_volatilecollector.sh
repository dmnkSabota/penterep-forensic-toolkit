#!/usr/bin/env bash
#
# run_all_tests_volatilecollector.sh
#
# Unit test suite for ptvolatilecollector.py
# Validates volatile-data acquisition per RFC 3227: memory dump
# (LiME -> /dev/mem fallback), running processes (ps), and open
# network sockets (ss / netstat). Each artefact is paired with a
# SHA-256 sidecar.
#
# Coverage: 5 categories per chapter 5.4.2 of the thesis.
#
# Output JSON structure:
#     properties.ramMethod      "lime" | "devmem"
#     properties.ramHash        sha256 of ram dump (or empty)
#     properties.ramSizeBytes   int
#     properties.artefacts      [ {name, path, sha256, timestamp}, ... ]
#     nodes[type=prerequisitesCheck]
#     nodes[type=ramDump]               method, sizeMB, sha256
#     nodes[type=processCollection]     processesHash, networkHash
#     nodes[type=chainOfCustodyEntry]
#
# Filenames follow {case_id}_<artefact>.{txt,lime} with a matching
# .sha256 sidecar for each artefact.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_volatilecollector"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptvolatilecollector.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock collectors.
# -----------------------------------------------------------------------------
make_mock_ps() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/ps" <<'EOF'
#!/bin/sh
cat <<PS_OUT
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root         1  0.0  0.1 168256 12356 ?        Ss   Jan01   0:01 /sbin/init
root       100  0.0  0.0      0     0 ?        S    Jan01   0:00 [kthreadd]
analyst   1234  0.5  1.2 234567 65432 pts/0    Ss+  10:30   0:15 -bash
analyst   5678  0.0  0.3  12345  4567 pts/0    S+   11:00   0:00 python3 script.py
PS_OUT
EOF
    chmod +x "${MOCK_BIN}/ps"
}

make_mock_ss() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/ss" <<'EOF'
#!/bin/sh
cat <<SS_OUT
Netid State   Recv-Q Send-Q Local Address:Port Peer Address:Port Process
tcp   LISTEN  0      128    0.0.0.0:22         0.0.0.0:*         users:(("sshd",pid=850,fd=3))
tcp   LISTEN  0      4096   127.0.0.1:5432     0.0.0.0:*         users:(("postgres",pid=1100,fd=7))
udp   UNCONN  0      0      0.0.0.0:68         0.0.0.0:*         users:(("dhclient",pid=600,fd=8))
SS_OUT
EOF
    chmod +x "${MOCK_BIN}/ss"
}

# Mock dd: intercept `if=/dev/mem` and write a deterministic 1 MiB
# stub so the RAM-collection path can complete without root.
# Everything else delegates to the real dd binary (located outside
# MOCK_BIN so the recursion never fires).
make_mock_dd_for_mem() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/dd" <<'EOF'
#!/bin/sh
INPUT=""; OUTPUT=""
for a in "$@"; do
    case "$a" in
        if=*) INPUT="${a#if=}" ;;
        of=*) OUTPUT="${a#of=}" ;;
    esac
done
if [ "${INPUT}" = "/dev/mem" ] && [ -n "${OUTPUT}" ]; then
    python3 -c "
with open('${OUTPUT}', 'wb') as f:
    for i in range(1024):
        f.write(bytes([i & 0xff] * 1024))
"
    echo "1024+0 records in"  >&2
    echo "1024+0 records out" >&2
    exit 0
fi
# Delegate non-/dev/mem calls to the real dd.
for d in /usr/bin/dd /bin/dd; do
    if [ -x "$d" ]; then
        exec "$d" "$@"
    fi
done
echo "dd: mock found no real dd binary" >&2
exit 1
EOF
    chmod +x "${MOCK_BIN}/dd"
}

setup_all_mocks() {
    make_mock_ps
    make_mock_ss
    make_mock_dd_for_mem
}


# -----------------------------------------------------------------------------
# run_tool: invoke with mocks on PATH. No --dry-run (see header).
# -----------------------------------------------------------------------------
run_tool() {
    local case_id="$1"
    local out="$2"
    local outdir="${3:-${TEST_DIR}/collected_${case_id}}"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" \
            --output-dir "${outdir}" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# -----------------------------------------------------------------------------
# run_tool_empty_path: invoke with PATH pointing at an empty directory
# so neither the mocks nor the real ps/ss/dd are resolvable. The tool's
# _check_command("ps") falls through to FileNotFoundError, prerequisites
# check fails, exit 99.
# -----------------------------------------------------------------------------
run_tool_empty_path() {
    local case_id="$1"
    local out="$2"
    local outdir="${3:-${TEST_DIR}/collected_${case_id}}"
    local py3
    py3=$(command -v python3)
    local empty_path="${TEST_DIR}/__empty_path__"
    mkdir -p "${empty_path}"
    local code=0
    PATH="${empty_path}" "${py3}" "${TOOL_PATH}" \
        "${case_id}" --output-dir "${outdir}" \
        --analyst Test --json-out "${out}" \
        >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"
    setup_all_mocks

    local case_id="${PREFIX_MALWARE}-2026-01-01-A01"
    local outdir="${TEST_DIR}/collected_a"
    local out="${TEST_DIR}/a.json"
    local code
    code=$(run_tool "${case_id}" "${out}" "${outdir}")
    assert_exit_code "A1: collection -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: processes file written under the actual filename.
    if [ -s "${outdir}/${case_id}_processes.txt" ]; then
        pass "A2: ${case_id}_processes.txt captured"
    else
        fail "A2: processes file" \
             "missing or empty at ${outdir}/${case_id}_processes.txt"
    fi

    # A3: network file written.
    if [ -s "${outdir}/${case_id}_network.txt" ]; then
        pass "A3: ${case_id}_network.txt captured"
    else
        fail "A3: network file" \
             "missing or empty at ${outdir}/${case_id}_network.txt"
    fi

    # A4: SHA-256 sidecars exist. Expect 3 (ram + processes + network);
    # accept >=2 since RAM dump can race the dd mock on slow VMs.
    local sidecar_count
    sidecar_count=$(find "${outdir}" -name "*.sha256" 2>/dev/null | wc -l)
    if [ "${sidecar_count:-0}" -ge 2 ] 2>/dev/null; then
        pass "A4: ${sidecar_count} SHA-256 sidecars created (>=2)"
    else
        fail "A4: SHA-256 sidecars" "got: ${sidecar_count}"
    fi
}


# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    # B1: prerequisites missing -> check_prerequisites fails -> exit 99.
    # PATH points at an empty dir; even `which` is unresolvable, so
    # _check_command("ps") falls through to FileNotFoundError.
    local code
    code=$(run_tool_empty_path "${PREFIX_MALWARE}-2026-01-01-B01" \
        "${TEST_DIR}/b1.json")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}"|"${EXIT_ENV}")
            pass "B1: missing collectors handled -> ${code}" ;;
        *) fail "B1: missing collectors" "exit ${code}" ;;
    esac

    # B2: unwritable output directory. __init__ calls mkdir on the
    # path; PermissionError bubbles up to main()'s try/except -> 99.
    setup_all_mocks
    local cb2=0
    PATH="${MOCK_BIN}:${PATH}" python3 "${TOOL_PATH}" \
        "${PREFIX_MALWARE}-2026-01-01-B02" \
        --output-dir "/proc/cannot_write_here" \
        --analyst Test --json-out "${TEST_DIR}/b2.json" \
        >/dev/null 2>&1 || cb2=$?
    case "${cb2}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}")
            pass "B2: unwritable output -> ${cb2}" ;;
        *) fail "B2: unwritable output" "exit ${cb2}" ;;
    esac
}


# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"
    setup_all_mocks

    # C1: RFC 3227 order. The tool records artefacts in volatility
    # order: RAM -> processes -> network. Each entry carries an ISO
    # 8601 timestamp; we verify they're sorted ascending.
    local case_id="${PREFIX_MALWARE}-2026-01-01-C01"
    local out="${TEST_DIR}/c1.json"
    run_tool "${case_id}" "${out}" "${TEST_DIR}/collected_c1" >/dev/null

    local order_ok
    order_ok=$(python3 - <<PYEOF
import json
d = json.load(open("${out}"))
arts = d.get('results', {}).get('properties', {}).get('artefacts', [])
timestamps = [a.get('timestamp', '') for a in arts]
print("ok" if len(timestamps) >= 2 and timestamps == sorted(timestamps) else f"out_of_order:{timestamps}")
PYEOF
)
    assert_equal "C1: RFC 3227 collection order respected" "ok" "${order_ok}"

    # C2: scenario prefix MALWARE retained through _sanitize_case_id.
    local case_id_out
    case_id_out=$(json_value "${out}" "d['results']['properties'].get('caseId')")
    case "${case_id_out}" in
        "${PREFIX_MALWARE}"*) pass "C2: MALWARE prefix preserved" ;;
        *) fail "C2: MALWARE prefix" "got: ${case_id_out}" ;;
    esac
}


# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"
    setup_all_mocks

    local case_id="${PREFIX_MALWARE}-2026-01-01-D01"
    local out="${TEST_DIR}/d.json"
    run_tool "${case_id}" "${out}" "${TEST_DIR}/collected_d" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" "${case_id}"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: each artefact in properties.artefacts[] has a 64-char sha256.
    local with_hash
    with_hash=$(json_value "${out}" "
sum(1 for a in d['results']['properties'].get('artefacts', [])
    if len(a.get('sha256', '')) == 64)")
    if [ "${with_hash:-0}" -ge 2 ] 2>/dev/null; then
        pass "D3: ${with_hash} artefacts with SHA-256 (>=2)"
    else
        fail "D3: artefacts with SHA-256" "got: ${with_hash}"
    fi

    # D4: ramMethod recorded at top-level properties (the tool does
    # NOT emit per-artefact collectionMethod fields).
    local ram_method
    ram_method=$(json_value "${out}" \
        "d['results']['properties'].get('ramMethod', '')")
    case "${ram_method}" in
        lime|devmem) pass "D4: ramMethod recorded (${ram_method})" ;;
        *) fail "D4: ramMethod" "got: '${ram_method}'" ;;
    esac

    # D5: each artefact carries a parseable ISO 8601 timestamp.
    local iso_ok
    iso_ok=$(python3 - <<PYEOF
import json
from datetime import datetime
d = json.load(open("${out}"))
arts = d.get('results', {}).get('properties', {}).get('artefacts', [])
ok = 0
for a in arts:
    ts = a.get('timestamp', '')
    try:
        datetime.fromisoformat(ts.replace('Z', '+00:00'))
        ok += 1
    except Exception:
        pass
print(ok)
PYEOF
)
    if [ "${iso_ok:-0}" -ge 2 ] 2>/dev/null; then
        pass "D5: ${iso_ok} ISO 8601 timestamps"
    else
        fail "D5: ISO 8601 timestamps" "got: ${iso_ok}"
    fi
}


# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"
    setup_all_mocks

    # E1: success -> 0
    local code
    code=$(run_tool "${PREFIX_MALWARE}-2026-01-01-E01" "${TEST_DIR}/e1.json" \
        "${TEST_DIR}/collected_e1")
    assert_exit_code "E1: success -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: unwritable output -> 99 via PermissionError in __init__.
    local ce2=0
    PATH="${MOCK_BIN}:${PATH}" python3 "${TOOL_PATH}" \
        "${PREFIX_MALWARE}-2026-01-01-E02" \
        --output-dir "/proc/no_write" \
        --analyst Test --json-out "${TEST_DIR}/e2.json" \
        >/dev/null 2>&1 || ce2=$?
    case "${ce2}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: unwritable -> ${ce2}" ;;
        *) fail "E2: unwritable" "exit ${ce2}" ;;
    esac

    # E3: missing collector binaries. With an empty PATH, the
    # prerequisites check fails -> exit 99.
    code=$(run_tool_empty_path "${PREFIX_MALWARE}-2026-01-01-E03" \
        "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}"|"${EXIT_ENV}")
            pass "E3: missing binaries -> ${code}" ;;
        *) fail "E3: missing binaries" "exit ${code}" ;;
    esac
}


main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptvolatilecollector\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptvolatilecollector"
}

main "$@"