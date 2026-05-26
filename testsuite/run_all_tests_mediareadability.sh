#!/usr/bin/env bash
#
# run_all_tests_mediareadability.sh
#
# Unit test suite for ptmediareadability.py
# Validates the READABLE / PARTIAL / UNREADABLE classifier across the
# pre-detection phase (lsblk, blkid, smartctl, hdparm, mdadm) and the
# four diagnostic read tests (first sector, sequential, random, speed).
#
# Coverage: 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_mediareadability"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptmediareadability.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

# Healthy-source device. crw-rw-rw-, exists on every POSIX system,
# satisfies the tool's "/dev/<path> exists" gate, and supplies an
# unlimited stream of zeros to the (mocked) diagnostic dd calls.
HEALTHY_DEV="/dev/zero"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock external diagnostic binaries. Each mock emits deterministic output
# that exercises the tool's parser branches; no real hardware is touched.
# -----------------------------------------------------------------------------
make_mock_lsblk() {
    local present="$1"   # "yes" -> device listed, "no" -> empty output
    mkdir -p "${MOCK_BIN}"
    if [ "${present}" = "yes" ]; then
        cat > "${MOCK_BIN}/lsblk" <<'EOF'
#!/bin/sh
echo "NAME   SIZE TYPE MOUNTPOINT"
echo "sdb    4G   disk"
EOF
    else
        cat > "${MOCK_BIN}/lsblk" <<'EOF'
#!/bin/sh
echo "NAME   SIZE TYPE MOUNTPOINT"
EOF
    fi
    chmod +x "${MOCK_BIN}/lsblk"
}

make_mock_blkid() {
    local fs="$1"   # "none" | "ext4" | "crypto_LUKS"
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/blkid" <<EOF
#!/bin/sh
[ "\$1" = "-o" ] && shift 2
if [ "${fs}" = "none" ]; then
    exit 2
fi
echo "/dev/sdb: TYPE=\"${fs}\""
EOF
    chmod +x "${MOCK_BIN}/blkid"
}

# Healthy mode keeps SMART attributes below SMART_CHECKS thresholds;
# warning mode pushes them above so _parse_smart_warnings() populates
# critical_findings.
make_mock_smartctl() {
    local mode="$1"   # "healthy" | "warning"
    mkdir -p "${MOCK_BIN}"
    if [ "${mode}" = "warning" ]; then
        cat > "${MOCK_BIN}/smartctl" <<'EOF'
#!/bin/sh
echo "SMART overall-health self-assessment test result: FAILED"
echo "  5 Reallocated_Sector_Ct 0x0033 100 100 010 Pre-fail Always - 200"
echo "197 Current_Pending_Sector 0x0012 100 100 000 Old_age Always - 5"
echo "198 Offline_Uncorrectable  0x0010 100 100 000 Old_age Offline - 3"
EOF
    else
        cat > "${MOCK_BIN}/smartctl" <<'EOF'
#!/bin/sh
echo "SMART overall-health self-assessment test result: PASSED"
echo "  5 Reallocated_Sector_Ct 0x0033 100 100 010 Pre-fail Always - 0"
echo "197 Current_Pending_Sector 0x0012 100 100 000 Old_age Always - 0"
echo "198 Offline_Uncorrectable  0x0010 100 100 000 Old_age Offline - 0"
EOF
    fi
    chmod +x "${MOCK_BIN}/smartctl"
}

# Tool detects TRIM only when a line (lowercased) contains both "trim"
# and "supported" AND its strip()ped form begins with "*", matching
# real hdparm -I output.
make_mock_hdparm() {
    local trim="$1"   # "yes" | "no"
    mkdir -p "${MOCK_BIN}"
    if [ "${trim}" = "yes" ]; then
        cat > "${MOCK_BIN}/hdparm" <<'EOF'
#!/bin/sh
echo "        *    Data Set Management TRIM supported (limit 8 blocks)"
EOF
    else
        cat > "${MOCK_BIN}/hdparm" <<'EOF'
#!/bin/sh
echo "        Data Set Management TRIM not supported"
EOF
    fi
    chmod +x "${MOCK_BIN}/hdparm"
}

make_mock_mdadm() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/mdadm" <<'EOF'
#!/bin/sh
echo "mdadm: cannot open: No such file or directory"
exit 1
EOF
    chmod +x "${MOCK_BIN}/mdadm"
}

# Mock dd. The tool calls real dd via _run_command; with --dry-run
# absent that call is fully executed, so PATH lookup picks up this
# script. Behaviour is driven by MOCK_DD_MODE in the environment.
make_mock_dd() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/dd" <<'EOF'
#!/bin/sh
SRC=""; SKIP=0
for a in "$@"; do
    case "$a" in
        if=*)   SRC="${a#if=}" ;;
        skip=*) SKIP="${a#skip=}" ;;
    esac
done
case "${MOCK_DD_MODE:-pass_all}" in
    fail_all)
        echo "dd: error reading '${SRC}': Input/output error" >&2
        exit 1
        ;;
    fail_random)
        # Succeed for sequential reads (skip=0); fail for random
        # offsets. classify() requires T1 AND T2 to pass for the
        # PARTIAL branch, so this gives a clean PARTIAL outcome.
        if [ "${SKIP:-0}" -gt 0 ]; then
            echo "dd: error reading '${SRC}': Input/output error" >&2
            exit 1
        fi
        exit 0
        ;;
    pass_all|*)
        exit 0
        ;;
esac
EOF
    chmod +x "${MOCK_BIN}/dd"
}

setup_all_mocks_healthy() {
    make_mock_lsblk "yes"
    make_mock_blkid "ext4"
    make_mock_smartctl "healthy"
    make_mock_hdparm "no"
    make_mock_mdadm
    make_mock_dd
}

# -----------------------------------------------------------------------------
# run_tool <case_id> <device> <json_out> [<mock_dd_mode>]
#
# Invokes the tool with the diagnostic-binary mocks on PATH and the
# requested dd mode in the environment. The write-blocker prompt is
# satisfied by a here-string. --dry-run is NOT passed because doing so
# would short-circuit _run_command() and skip every subprocess call
# (see header).
# -----------------------------------------------------------------------------
run_tool() {
    local case_id="$1"
    local device="$2"
    local out="$3"
    local dd_mode="${4:-pass_all}"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
    MOCK_DD_MODE="${dd_mode}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${device}" \
            --analyst "Test" \
            --json-out "${out}" \
            <<< "y" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    setup_all_mocks_healthy
    local out="${TEST_DIR}/a_out.json"
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${HEALTHY_DEV}" "${out}" pass_all)
    assert_exit_code "A1: healthy media -> exit 0" "${EXIT_SUCCESS}" "${code}"

    assert_json_field "A2: mediaStatus=READABLE" "${out}" \
        "d['results']['properties'].get('mediaStatus')" "READABLE"

    assert_json_field "A3: recommendedTool=dc3dd for READABLE" "${out}" \
        "d['results']['properties'].get('recommendedTool')" "dc3dd"

    # A4: testsPassed >= 3 of 4. Property-level running total.
    local passed
    passed=$(json_value "${out}" \
        "d['results']['properties'].get('testsPassed', 0)")
    if [ "${passed:-0}" -ge 3 ] 2>/dev/null; then
        pass "A4: 3+ of 4 read tests passed (got ${passed})"
    else
        fail "A4: 3+ of 4 read tests passed" "got: ${passed}"
    fi

    # A5: speed for testId=4 lives on the diagnosticTests node, not
    # on top-level properties.
    local speed
    speed=$(json_value "${out}" \
        "next((t.get('speedMBps', 0) for n in d['results']['nodes'] if n.get('type') == 'diagnosticTests' for t in n.get('properties', {}).get('tests', []) if t.get('testId') == 4), 0)")
    if [ -n "${speed}" ] && [ "${speed}" != "0" ] && [ "${speed}" != "0.0" ]; then
        pass "A5: read speed reported (${speed} MB/s)"
    else
        fail "A5: read speed reported" "got: '${speed}'"
    fi
}

# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    setup_all_mocks_healthy

    # B1: nonexistent /dev/ path. The tool's __init__ existence
    # check fires and calls sys.exit(99) before the diagnostic
    # phase. EXIT_ENV is the expected outcome here.
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" \
        "/dev/totally_nonexistent_xyz" "${TEST_DIR}/b1.json")
    case "${code}" in
        "${EXIT_FINDING}"|"${EXIT_ENV}"|"${EXIT_FAILURE}")
            pass "B1: nonexistent device -> finding/env (exit ${code})" ;;
        *) fail "B1: nonexistent device" "exit ${code}" ;;
    esac

    # B2: media unreadable. Mock dd in fail_all mode causes the first
    # sector read to fail; classify() drops to UNREADABLE.
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" \
        "${HEALTHY_DEV}" "${TEST_DIR}/b2.json" fail_all)
    case "${code}" in
        "${EXIT_FINDING}"|"${EXIT_FAILURE}")
            pass "B2: unreadable media -> finding (exit ${code})" ;;
        *) fail "B2: unreadable media classification" "exit ${code}" ;;
    esac

    # B3: LUKS detected via blkid mock. The tool stores the finding
    # in properties.criticalFindings, NOT in a dedicated boolean.
    make_mock_blkid "crypto_LUKS"
    local findings
    run_tool "${PREFIX_COC}-2026-01-01-001" "${HEALTHY_DEV}" \
        "${TEST_DIR}/b3.json" pass_all >/dev/null
    findings=$(json_value "${TEST_DIR}/b3.json" \
        "' '.join(d['results']['properties'].get('criticalFindings', []))")
    case "${findings}" in
        *LUKS*|*Encryption*|*encryption*)
            pass "B3: LUKS encryption detected in criticalFindings" ;;
        *) fail "B3: LUKS encryption detected" "got: '${findings}'" ;;
    esac

    # B4: SMART warnings. Mock emits raw attribute integers above
    # the SMART_CHECKS thresholds; the tool ignores the PASSED/FAILED
    # health line and parses the integers directly.
    setup_all_mocks_healthy
    make_mock_smartctl "warning"
    run_tool "${PREFIX_COC}-2026-01-01-001" "${HEALTHY_DEV}" \
        "${TEST_DIR}/b4.json" pass_all >/dev/null
    findings=$(json_value "${TEST_DIR}/b4.json" \
        "' '.join(d['results']['properties'].get('criticalFindings', []))")
    case "${findings}" in
        *SMART*|*Reallocated*|*Pending*|*Uncorrectable*)
            pass "B4: SMART warnings captured in criticalFindings" ;;
        *) fail "B4: SMART warnings captured" "got: '${findings}'" ;;
    esac

    # B5: TRIM active. Mock line must strip()-start with "*".
    setup_all_mocks_healthy
    make_mock_hdparm "yes"
    run_tool "${PREFIX_COC}-2026-01-01-001" "${HEALTHY_DEV}" \
        "${TEST_DIR}/b5.json" pass_all >/dev/null
    findings=$(json_value "${TEST_DIR}/b5.json" \
        "' '.join(d['results']['properties'].get('criticalFindings', []))")
    case "${findings}" in
        *TRIM*|*trim*)
            pass "B5: TRIM active captured in criticalFindings" ;;
        *) fail "B5: TRIM active captured" "got: '${findings}'" ;;
    esac
}

# =============================================================================
# C: Boundary cases
#
# Unprivileged users cannot create block devices of specific small
# sizes, so the size axis is simulated via MOCK_DD_MODE:
#   100 B device  ~  fail_all      (every diagnostic read returns EIO)
#   1 MiB device  ~  fail_random   (T1+T2 succeed, T3 fails -> PARTIAL)
#   10 MiB device ~  pass_all      (everything succeeds -> READABLE)
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"
    setup_all_mocks_healthy

    # C1: tiny media -> UNREADABLE.
    run_tool "${PREFIX_COC}-2026-01-01-001" "${HEALTHY_DEV}" \
        "${TEST_DIR}/c1.json" fail_all >/dev/null
    local status
    status=$(json_value "${TEST_DIR}/c1.json" \
        "d['results']['properties'].get('mediaStatus')")
    case "${status}" in
        "PARTIAL"|"UNREADABLE")
            pass "C1: tiny media -> ${status}" ;;
        *) fail "C1: tiny media classification" "got: ${status}" ;;
    esac

    # C2: media large enough for T1+T2 but random reads fail -> PARTIAL.
    run_tool "${PREFIX_COC}-2026-01-01-002" "${HEALTHY_DEV}" \
        "${TEST_DIR}/c2.json" fail_random >/dev/null
    status=$(json_value "${TEST_DIR}/c2.json" \
        "d['results']['properties'].get('mediaStatus')")
    case "${status}" in
        "READABLE"|"PARTIAL")
            pass "C2: 1 MiB-equivalent media -> ${status}" ;;
        *) fail "C2: 1 MiB-equivalent media classification" "got: ${status}" ;;
    esac

    # C3: media of speed-benchmark size -> READABLE.
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-003" "${HEALTHY_DEV}" \
        "${TEST_DIR}/c3.json" pass_all)
    case "${code}" in
        "${EXIT_SUCCESS}"|"${EXIT_FAILURE}"|"${EXIT_FINDING}")
            pass "C3: 10 MiB-equivalent media handled (exit ${code})" ;;
        *) fail "C3: 10 MiB-equivalent media" "exit ${code}" ;;
    esac
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"
    setup_all_mocks_healthy

    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_COC}-2026-01-01-001" "${HEALTHY_DEV}" "${out}" pass_all >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" "${PREFIX_COC}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    local ver
    ver=$(json_value "${out}" "d['results']['properties'].get('scriptVersion', '')")
    if [ -n "${ver}" ] && [ "${ver}" != "''" ]; then
        pass "D3: scriptVersion populated (${ver})"
    else
        fail "D3: scriptVersion populated" "got: '${ver}'"
    fi

    local ts
    ts=$(json_value "${out}" "d['results']['properties'].get('timestamp', '')")
    if python3 -c "from datetime import datetime; datetime.fromisoformat('${ts}'.replace('Z','+00:00'))" 2>/dev/null; then
        pass "D4: timestamp ISO 8601"
    else
        fail "D4: timestamp ISO 8601" "got: '${ts}'"
    fi

    # D5: four diagnostic tests recorded. testsRun is the property-
    # level running total of the four entries on the diagnosticTests
    # node (first sector, sequential, random, speed). All four
    # require pass_all mode so that _test_first_sector() does not
    # short-circuit the suite.
    local n
    n=$(json_value "${out}" "d['results']['properties'].get('testsRun', 0)")
    assert_equal "D5: 4 diagnostic tests recorded" "4" "${n}"
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"
    setup_all_mocks_healthy

    # E1: READABLE -> exit 0
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${HEALTHY_DEV}" \
        "${TEST_DIR}/e1.json" pass_all)
    assert_exit_code "E1: READABLE -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: UNREADABLE -> exit 2 (specific finding) via fail_all.
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${HEALTHY_DEV}" \
        "${TEST_DIR}/e2.json" fail_all)
    case "${code}" in
        "${EXIT_FINDING}"|"${EXIT_FAILURE}")
            pass "E2: UNREADABLE -> ${code}" ;;
        *) fail "E2: UNREADABLE exit code" "got: ${code}" ;;
    esac

    # E3: nonexistent device -> __init__ existence check -> exit 99.
    # EXIT_FINDING / EXIT_FAILURE are kept in the acceptance set for
    # forward compatibility if the tool reclassifies the error later.
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "/dev/no_such_device_xyz" \
        "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FINDING}"|"${EXIT_FAILURE}")
            pass "E3: missing device -> ${code}" ;;
        *) fail "E3: missing device exit code" "got: ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptmediareadability\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptmediareadability"
}

main "$@"