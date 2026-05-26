# test_framework.sh
#
# Shared helpers for ptforensicanalysis unit test scripts. Each per-tool
# test script sources this file once near the top, then uses the helpers
# below to keep the assertion vocabulary uniform across all suites.
#
# The framework provides:
#   - Assertion primitives:     pass, fail, assert_equal, assert_exit_code,
#                               assert_json_field, assert_node_present
#   - Prerequisite validation:  check_prerequisites
#   - JSON inspection helpers:  json_value, node_property
#   - Coverage instrumentation: invoke_tool (transparently runs the tool
#                               under coverage.py when COVERAGE=1)
#   - Color handling:           honors NO_COLOR and non-TTY stdout
#
# This file is sourced after reference_values.sh and before any test
# functions are defined.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

[ -n "${_TESTFW_SOURCED:-}" ] && return 0
_TESTFW_SOURCED=1

set -u
set -o pipefail


# -----------------------------------------------------------------------------
# Counters and failure log. These are mutable; not declared readonly.
# -----------------------------------------------------------------------------
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
FAILED_CASES=()


# -----------------------------------------------------------------------------
# Color handling.
# Honors:
#   NO_COLOR=1     -> ANSI escapes disabled (https://no-color.org/)
#   non-TTY stdout -> ANSI escapes disabled (suitable for CI logs)
# -----------------------------------------------------------------------------
if [ -n "${NO_COLOR:-}" ] || [ ! -t 1 ]; then
    C_PASS=""
    C_FAIL=""
    C_WARN=""
    C_INFO=""
    C_RESET=""
else
    C_PASS=$'\033[0;32m'
    C_FAIL=$'\033[0;31m'
    C_WARN=$'\033[1;33m'
    C_INFO=$'\033[0;34m'
    C_RESET=$'\033[0m'
fi


# -----------------------------------------------------------------------------
# pass <test_name>
# Record a passing test case and increment counters.
# -----------------------------------------------------------------------------
pass() {
    local name="$1"
    printf '%s[PASS]%s %s\n' "${C_PASS}" "${C_RESET}" "${name}"
    PASSED_TESTS=$((PASSED_TESTS + 1))
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
}


# -----------------------------------------------------------------------------
# fail <test_name> [<diagnostic>]
# Record a failing test case. The optional diagnostic argument is printed
# verbatim and truncated to 20 lines to keep the summary readable.
# -----------------------------------------------------------------------------
fail() {
    local name="$1"
    local diag="${2:-}"
    printf '%s[FAIL]%s %s\n' "${C_FAIL}" "${C_RESET}" "${name}"
    if [ -n "${diag}" ]; then
        printf '%s---%s\n' "${C_WARN}" "${C_RESET}"
        printf '%s\n' "${diag}" | head -20
        printf '%s---%s\n' "${C_WARN}" "${C_RESET}"
    fi
    FAILED_TESTS=$((FAILED_TESTS + 1))
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    FAILED_CASES+=("${name}")
}


# -----------------------------------------------------------------------------
# test_header <category_label>
# Print a section banner. ASCII-only so the output is safe for redirection
# into log files and CI consoles that do not render Unicode.
# -----------------------------------------------------------------------------
test_header() {
    printf '\n%s=== %s ===%s\n' "${C_INFO}" "$1" "${C_RESET}"
}


# -----------------------------------------------------------------------------
# json_value <file> <python_expression>
# Read the JSON in <file> as Python dict 'd' and print the result of
# <python_expression>. Returns the empty string on any parse or lookup
# failure, so callers can also use this helper to detect malformed output.
# -----------------------------------------------------------------------------
json_value() {
    local file="$1"
    local expr="$2"
    python3 -c "
import json, sys
try:
    d = json.load(open('${file}'))
    print(${expr})
except Exception:
    print('')
" 2>/dev/null
}


# -----------------------------------------------------------------------------
# node_property <file> <node_type> <property_name>
# Locate the first node in results.nodes whose 'type' equals <node_type>
# and print the value of properties.<property_name>. Empty string on miss.
# -----------------------------------------------------------------------------
node_property() {
    local file="$1"
    local node_type="$2"
    local prop_name="$3"
    python3 -c "
import json
try:
    nodes = json.load(open('${file}'))['results']['nodes']
    node = next((n for n in nodes if n.get('type') == '${node_type}'), {})
    print(node.get('properties', {}).get('${prop_name}', ''))
except Exception:
    print('')
" 2>/dev/null
}


# -----------------------------------------------------------------------------
# assert_equal <test_name> <expected> <actual>
# Pass iff "${expected}" == "${actual}". The values are compared as strings.
# -----------------------------------------------------------------------------
assert_equal() {
    local name="$1"
    local expected="$2"
    local actual="$3"
    if [ "${expected}" = "${actual}" ]; then
        pass "${name}"
    else
        fail "${name}" "expected: '${expected}'
actual:   '${actual}'"
    fi
}


# -----------------------------------------------------------------------------
# assert_exit_code <test_name> <expected> <actual>
# Specialised wrapper around assert_equal that prints the named exit-code
# constant in diagnostics when the value matches a known one.
# -----------------------------------------------------------------------------
assert_exit_code() {
    local name="$1"
    local expected="$2"
    local actual="$3"
    if [ "${expected}" = "${actual}" ]; then
        pass "${name}"
    else
        fail "${name}" "expected exit code: ${expected}
actual exit code:   ${actual}"
    fi
}


# -----------------------------------------------------------------------------
# assert_json_field <test_name> <json_file> <python_expr> <expected>
# Convenience wrapper combining json_value with assert_equal.
# -----------------------------------------------------------------------------
assert_json_field() {
    local name="$1"
    local file="$2"
    local expr="$3"
    local expected="$4"
    local actual
    actual=$(json_value "${file}" "${expr}")
    assert_equal "${name}" "${expected}" "${actual}"
}


# -----------------------------------------------------------------------------
# assert_node_present <test_name> <json_file> <node_type>
# Pass iff results.nodes contains at least one node whose 'type' equals
# <node_type>. Used to verify chainOfCustodyEntry presence (category D).
# -----------------------------------------------------------------------------
assert_node_present() {
    local name="$1"
    local file="$2"
    local node_type="$3"
    local count
    count=$(python3 -c "
import json
try:
    nodes = json.load(open('${file}'))['results']['nodes']
    print(sum(1 for n in nodes if n.get('type') == '${node_type}'))
except Exception:
    print(0)
" 2>/dev/null)
    if [ "${count}" -ge 1 ] 2>/dev/null; then
        pass "${name}"
    else
        fail "${name}" "expected at least one node of type '${node_type}', found ${count}"
    fi
}


# -----------------------------------------------------------------------------
# check_prerequisites <python_min_version> <tool_path> [extra_binaries...]
# Verify that the runtime environment satisfies the suite's hard requirements
# before any test is launched. Exits with EXIT_ENV (=99) on missing items so
# CI systems can distinguish environment failures from genuine test failures.
# -----------------------------------------------------------------------------
check_prerequisites() {
    local python_min="$1"
    local tool_path="$2"
    shift 2

    local missing=()
    local found_version=""

    if command -v python3 >/dev/null 2>&1; then
        found_version=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
        if ! python3 -c "import sys; major, minor = '${python_min}'.split('.'); sys.exit(0 if sys.version_info >= (int(major), int(minor)) else 1)"; then
            missing+=("python3 >= ${python_min} (found ${found_version})")
        fi
    else
        missing+=("python3")
    fi

    if [ ! -f "${tool_path}" ]; then
        missing+=("tool under test: ${tool_path}")
    fi

    local binary
    for binary in "$@"; do
        if ! command -v "${binary}" >/dev/null 2>&1; then
            missing+=("${binary}")
        fi
    done

    if [ "${#missing[@]}" -gt 0 ]; then
        printf '[ERROR] Cannot run test suite, missing prerequisites:\n' >&2
        printf '  - %s\n' "${missing[@]}" >&2
        printf '\nInstall hints (Debian/Ubuntu):\n' >&2
        printf '  sudo apt install python3 coreutils libewf-tools sleuthkit \\\n' >&2
        printf '       testdisk exiftool libtiff-tools imagemagick smartmontools\n' >&2
        exit 99
    fi
}


# -----------------------------------------------------------------------------
# invoke_tool <python_script> <args...>
# Run the tool under test. When COVERAGE=1 is set in the environment the
# invocation is wrapped in `coverage run --append --branch`, allowing the
# master runner to aggregate line and branch coverage across all suites
# without modifying each script individually.
# -----------------------------------------------------------------------------
invoke_tool() {
    local script="$1"
    shift
    if [ "${COVERAGE:-0}" = "1" ] && command -v coverage >/dev/null 2>&1; then
        coverage run --append --branch --source="$(dirname "${script}")" \
            "${script}" "$@"
    else
        python3 "${script}" "$@"
    fi
}


# -----------------------------------------------------------------------------
# print_summary <suite_label>
# Emit final summary line. Returns 0 if no failures, 1 otherwise, so the
# caller can use this as the script's exit code.
# -----------------------------------------------------------------------------
print_summary() {
    local label="$1"
    printf '\n=== Summary: %s ===\n' "${label}"
    printf '  total:  %d\n' "${TOTAL_TESTS}"
    printf '  passed: %s%d%s\n' "${C_PASS}" "${PASSED_TESTS}" "${C_RESET}"
    if [ "${FAILED_TESTS}" -gt 0 ]; then
        printf '  failed: %s%d%s\n' "${C_FAIL}" "${FAILED_TESTS}" "${C_RESET}"
        printf '\nFailed cases:\n'
        printf '  - %s\n' "${FAILED_CASES[@]}"
        return 1
    fi
    return 0
}