#!/usr/bin/env bash
#
# run_all_tests.sh
#
# Master runner for the ptforensicanalysis unit test suite.
#
# Discovers every per-tool test script (run_all_tests_*.sh) in the project
# root, executes them sequentially, aggregates the results and prints a
# combined summary.
#
# Options:
#
#   --coverage        run each suite under coverage.py, then emit a combined
#                     line/branch coverage report and an HTML version in
#                     ./htmlcov/. Requires coverage.py >= 7.0.
#
#   --no-color        disable ANSI escapes. Equivalent to NO_COLOR=1 in
#                     the environment.
#
#   --fail-fast       stop at the first failing suite (default: run all).
#
#   --filter <name>   only run suites whose script name matches the given
#                     fragment (e.g. --filter coc -> run_all_tests_cocmanager.sh
#                     and run_all_tests_consolidation.sh).
#
#   --list            list discovered suites and exit without running them.
#
# Exit codes:
#   0   all suites passed
#   1   at least one suite reported failures
#   2   no suites discovered (configuration error)
#   99  prerequisites missing
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=testlib/test_framework.sh
source "${SCRIPT_DIR}/testlib/test_framework.sh"

# Reset framework counters; the master runner aggregates its own totals.
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
FAILED_CASES=()


# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------
OPT_COVERAGE=0
OPT_FAIL_FAST=0
OPT_LIST_ONLY=0
OPT_FILTER=""

while [ $# -gt 0 ]; do
    case "$1" in
        --coverage)   OPT_COVERAGE=1 ;;
        --no-color)   export NO_COLOR=1 ;;
        --fail-fast)  OPT_FAIL_FAST=1 ;;
        --list)       OPT_LIST_ONLY=1 ;;
        --filter)     shift; OPT_FILTER="$1" ;;
        -h|--help)
            sed -n '2,40p' "$0"
            exit 0
            ;;
        *)
            printf '[ERROR] Unknown option: %s\n' "$1" >&2
            printf 'Run with --help to see usage.\n' >&2
            exit 2
            ;;
    esac
    shift
done


# -----------------------------------------------------------------------------
# Coverage setup
# -----------------------------------------------------------------------------
if [ "${OPT_COVERAGE}" = "1" ]; then
    if ! command -v coverage >/dev/null 2>&1; then
        printf '[ERROR] --coverage requires coverage.py:\n' >&2
        printf '  pip install --user coverage\n' >&2
        exit 99
    fi
    coverage erase
    export COVERAGE=1
fi


# -----------------------------------------------------------------------------
# Discover suites.
#
# The discovery glob explicitly excludes this master runner itself, so the
# script never invokes recursively even if it lives in the same directory.
# -----------------------------------------------------------------------------
declare -a SUITES=()
for f in "${SCRIPT_DIR}"/run_all_tests_*.sh; do
    [ -f "${f}" ] || continue
    [ "${f}" = "${SCRIPT_DIR}/run_all_tests.sh" ] && continue
    if [ -n "${OPT_FILTER}" ]; then
        case "${f}" in
            *"${OPT_FILTER}"*) SUITES+=("${f}") ;;
            *) continue ;;
        esac
    else
        SUITES+=("${f}")
    fi
done

if [ "${#SUITES[@]}" -eq 0 ]; then
    printf '[ERROR] No test suites discovered.\n' >&2
    [ -n "${OPT_FILTER}" ] && printf '  Filter: %s\n' "${OPT_FILTER}" >&2
    exit 2
fi

if [ "${OPT_LIST_ONLY}" = "1" ]; then
    printf 'Discovered %d test suite(s):\n' "${#SUITES[@]}"
    for s in "${SUITES[@]}"; do
        printf '  %s\n' "$(basename "${s}")"
    done
    exit 0
fi


# -----------------------------------------------------------------------------
# Run suites and aggregate results
# -----------------------------------------------------------------------------
printf 'Running %d test suite(s)\n' "${#SUITES[@]}"
[ "${OPT_COVERAGE}" = "1" ] && printf 'Coverage instrumentation: enabled\n'
printf '\n'

declare -a FAILED_SUITES=()
declare -a PASSED_SUITES=()
START_EPOCH=$(date +%s)

for suite in "${SUITES[@]}"; do
    suite_name=$(basename "${suite}" .sh)
    printf '>>> %s\n' "${suite_name}"

    suite_log=$(mktemp)
    rc=0
    bash "${suite}" 2>&1 | tee "${suite_log}"
    rc=${PIPESTATUS[0]}

    # Parse "total" / "passed" / "failed" lines from the suite's own summary.
    local_total=$(grep -E '^[[:space:]]*total:' "${suite_log}" | awk '{print $NF}' | tail -1)
    local_passed=$(grep -E '^[[:space:]]*passed:' "${suite_log}" | awk '{print $NF}' | tail -1)
    local_failed=$(grep -E '^[[:space:]]*failed:' "${suite_log}" | awk '{print $NF}' | tail -1)
    rm -f "${suite_log}"

    # Strip color codes that may have leaked into the captured numbers.
    local_total=$(printf '%s' "${local_total}" | sed 's/\x1b\[[0-9;]*m//g')
    local_passed=$(printf '%s' "${local_passed}" | sed 's/\x1b\[[0-9;]*m//g')
    local_failed=$(printf '%s' "${local_failed}" | sed 's/\x1b\[[0-9;]*m//g')

    TOTAL_TESTS=$((TOTAL_TESTS + ${local_total:-0}))
    PASSED_TESTS=$((PASSED_TESTS + ${local_passed:-0}))
    FAILED_TESTS=$((FAILED_TESTS + ${local_failed:-0}))

    if [ "${rc}" -eq 0 ]; then
        PASSED_SUITES+=("${suite_name}")
    else
        FAILED_SUITES+=("${suite_name} (rc=${rc})")
        if [ "${OPT_FAIL_FAST}" = "1" ]; then
            printf '\n[FAIL-FAST] Aborting after %s\n' "${suite_name}"
            break
        fi
    fi
    printf '\n'
done

END_EPOCH=$(date +%s)
ELAPSED=$((END_EPOCH - START_EPOCH))


# -----------------------------------------------------------------------------
# Coverage report
# -----------------------------------------------------------------------------
if [ "${OPT_COVERAGE}" = "1" ]; then
    printf '=== Code coverage ===\n'
    coverage report --show-missing | tail -50
    coverage html -d "${SCRIPT_DIR}/htmlcov" >/dev/null
    printf '\nHTML report: %s/htmlcov/index.html\n' "${SCRIPT_DIR}"
fi


# -----------------------------------------------------------------------------
# Aggregate summary
# -----------------------------------------------------------------------------
printf '\n=== Aggregate summary ===\n'
printf '  suites discovered:    %d\n' "${#SUITES[@]}"
printf '  suites passed:        %d\n' "${#PASSED_SUITES[@]}"
printf '  suites failed:        %d\n' "${#FAILED_SUITES[@]}"
printf '  test cases total:     %d\n' "${TOTAL_TESTS}"
printf '  test cases passed:    %d\n' "${PASSED_TESTS}"
printf '  test cases failed:    %d\n' "${FAILED_TESTS}"
printf '  elapsed:              %ds\n' "${ELAPSED}"

if [ "${#FAILED_SUITES[@]}" -gt 0 ]; then
    printf '\nFailed suites:\n'
    printf '  - %s\n' "${FAILED_SUITES[@]}"
    exit 1
fi

printf '\nAll suites passed.\n'
exit 0