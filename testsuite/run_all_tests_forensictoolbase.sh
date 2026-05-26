#!/usr/bin/env bash
#
# run_all_tests_forensictoolbase.sh
#
# Unit test suite for ptforensictoolbase.py (shared base class).
#
# The base class has no CLI entry point, so tests use an inline Python
# harness that subclasses ForensicToolBase, invokes the target method,
# and prints the result for shell-side assertions.
#
# Coverage: 23 tests in 5 categories per chapter 5.4.1 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_forensictoolbase"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptforensictoolbase.py"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Python harness: instantiates a minimal subclass and runs <expression>
# Returns the printed result on stdout, exit code on failure.
# -----------------------------------------------------------------------------
py_harness() {
    local expression="$1"
    python3 - <<PYEOF 2>&1
import sys, os
from pathlib import Path
sys.path.insert(0, "${TOOLS_DIR}")
from ptforensictoolbase import ForensicToolBase

class _T(ForensicToolBase):
    def __init__(self):
        self.case_id = "TEST"
        self.analyst = "Test"
        self.dry_run = False

t = _T()
try:
    print(${expression})
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    sys.exit(1)
PYEOF
}


# =============================================================================
# A: Static helpers
# =============================================================================
test_a_static_helpers() {
    test_header "Category A: Static helpers"

    # A1: case ID sanitization removes forward slashes
    local result
    result=$(py_harness "t._sanitize_case_id('COC-2026/01/01-001')")
    case "${result}" in
        *"COC-2026-01-01-001"*|*"COC-20260101-001"*|*"COC-2026_01_01-001"*) pass "A1: slash removed from caseId" ;;
        *) fail "A1: slash removed from caseId" "got: ${result}" ;;
    esac

    # A2: case ID sanitization preserves alphanumerics + hyphen
    result=$(py_harness "t._sanitize_case_id('COC-2026-01-01-001')")
    assert_equal "A2: clean caseId preserved" "COC-2026-01-01-001" "${result}"

    # A3: SHA-256 of empty file matches NIST FIPS 180-4 empty-string vector
    mkdir -p "${TEST_DIR}"
    : > "${TEST_DIR}/empty"
    result=$(py_harness "t._file_sha256('${TEST_DIR}/empty')")
    assert_equal "A3: SHA-256 of empty file (FIPS 180-4)" \
        "${NIST_SHA256_EMPTY}" "${result}"

    # A4: SHA-256 of 'abc' matches FIPS 180-4 Appendix B.1
    printf 'abc' > "${TEST_DIR}/abc"
    result=$(py_harness "t._file_sha256('${TEST_DIR}/abc')")
    assert_equal "A4: SHA-256 of 'abc' (FIPS 180-4 B.1)" \
        "${NIST_SHA256_ABC}" "${result}"
}

# =============================================================================
# B: Hash boundary cases
# =============================================================================
test_b_hash_boundaries() {
    test_header "Category B: Hash boundary cases"

    # B1: nonexistent file returns None or empty
    local result
    result=$(py_harness "t._file_sha256('${TEST_DIR}/does_not_exist')")
    case "${result}" in
        "None"|"") pass "B1: nonexistent file returns None" ;;
        *) fail "B1: nonexistent file returns None" "got: ${result}" ;;
    esac

    # B2: SHA-256 of 1MB file (boundary across hash block size)
    dd if=/dev/zero of="${TEST_DIR}/1mb" bs=1024 count=1024 2>/dev/null
    # SHA-256 of 1MB of zeros, computed independently:
    local expected_1mb
    expected_1mb=$(sha256sum "${TEST_DIR}/1mb" | awk '{print $1}')
    result=$(py_harness "t._file_sha256('${TEST_DIR}/1mb')")
    assert_equal "B2: SHA-256 of 1MB file matches sha256sum" \
        "${expected_1mb}" "${result}"
}

# =============================================================================
# C: Image validation
# =============================================================================
test_c_image_validation() {
    test_header "Category C: Image validation"

    # C1: file below MIN_IMAGE_BYTES threshold (=100B) classified as invalid
    dd if=/dev/zero of="${TEST_DIR}/tiny" bs=50 count=1 2>/dev/null
    local result
    result=$(py_harness "t._validate_image_file(Path('${TEST_DIR}/tiny'))[0]")
    assert_equal "C1: <100B file -> invalid" "invalid" "${result}"

    # C2: file between 100B and 1024B classified as corrupted (no magic)
    dd if=/dev/zero of="${TEST_DIR}/small" bs=500 count=1 2>/dev/null
    result=$(py_harness "t._validate_image_file(Path('${TEST_DIR}/small'))[0]")
    case "${result}" in
        "corrupted"|"invalid") pass "C2: 500B non-image classified ${result}" ;;
        *) fail "C2: 500B non-image classification" "got: ${result}" ;;
    esac

    # C3: nonexistent file -> invalid
    result=$(py_harness "t._validate_image_file(Path('${TEST_DIR}/nonexistent'))[0]")
    assert_equal "C3: nonexistent file -> invalid" "invalid" "${result}"

    # C4: a valid 1x1 PNG (using PIL + identify if available) -> valid
    if python3 -c 'from PIL import Image' 2>/dev/null && command -v identify >/dev/null 2>&1; then
        python3 -c "
from PIL import Image
img = Image.new('RGB', (100, 100), color='red')
img.save('${TEST_DIR}/test.png')
"
        result=$(py_harness "t._validate_image_file(Path('${TEST_DIR}/test.png'))[0]")
        assert_equal "C4: valid PNG -> valid" "valid" "${result}"
    fi
}

# =============================================================================
# D: Filesystem metadata extraction
# =============================================================================
test_d_fs_metadata() {
    test_header "Category D: Filesystem metadata"

    # D1: _extract_fs_metadata on nonexistent path returns dict with error
    local result
    result=$(py_harness "type(t._extract_fs_metadata('${TEST_DIR}/missing')).__name__")
    assert_equal "D1: _extract_fs_metadata returns dict on missing path" \
        "dict" "${result}"

    # D2: existing path returns dict
    result=$(py_harness "type(t._extract_fs_metadata('${TEST_DIR}')).__name__")
    assert_equal "D2: _extract_fs_metadata returns dict on existing path" \
        "dict" "${result}"
}

# =============================================================================
# E: Command utilities + JSON helpers + binary mode + write-blocker
# =============================================================================
test_e_command_helpers() {
    test_header "Category E: Command helpers"

    # E1: _check_command finds existing binary (python3 always available)
    local result
    result=$(py_harness "t._check_command('python3')")
    assert_equal "E1: _check_command finds python3" "True" "${result}"

    # E2: _check_command reports missing binary
    result=$(py_harness "t._check_command('definitely_nonexistent_binary_xyz')")
    assert_equal "E2: _check_command reports missing binary" "False" "${result}"

    # E3: _run_command executes successfully
    result=$(py_harness "t._run_command(['echo', 'hello'])['returncode']")
    assert_equal "E3: _run_command echo -> returncode 0" "0" "${result}"

    # E4: _run_command captures stdout
    result=$(py_harness "t._run_command(['echo', 'hello'])['stdout'].strip()")
    assert_equal "E4: _run_command captures stdout" "hello" "${result}"

    # E5: _run_command on failing command returns non-zero
    result=$(py_harness "t._run_command(['false'])['returncode']")
    if [ "${result}" -ne 0 ] 2>/dev/null; then
        pass "E5: _run_command captures non-zero exit"
    else
        fail "E5: _run_command captures non-zero exit" "got: ${result}"
    fi

    # E6: _run_command with timeout raises or reports
    result=$(py_harness "t._run_command(['sleep', '10'], timeout=1)['returncode']")
    if [ "${result}" = "-1" ] || [ "${result}" = "124" ]; then
        pass "E6: _run_command timeout honoured"
    else
        fail "E6: _run_command timeout honoured" "got returncode: ${result}"
    fi

    # E7: _run_command in binary mode returns bytes
    result=$(py_harness "type(t._run_command(['printf', 'abc'], binary=True)['stdout']).__name__")
    assert_equal "E7: _run_command binary mode returns bytes" "bytes" "${result}"

    # E8: _init_properties populates required fields
    result=$(python3 - <<PYEOF2 2>&1
import sys
sys.path.insert(0, "${TOOLS_DIR}")
from ptforensictoolbase import ForensicToolBase
from ptlibs.ptjsonlib import PtJsonLib
class _T(ForensicToolBase):
    def __init__(self):
        self.case_id = "TEST"
        self.analyst = "Test"
        self.dry_run = False
class _Holder(_T):
    def __init__(self):
        super().__init__()
        self.ptjsonlib = PtJsonLib()
h = _Holder()
try:
    h._init_properties("1.0.0")
    print("caseId" in h.ptjsonlib.json_object.get("results", {}).get("properties", {}))
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
PYEOF2
)
    case "${result}" in
        *"True"*) pass "E8: _init_properties sets caseId" ;;
        *) fail "E8: _init_properties sets caseId" "got: ${result}" ;;
    esac
}

# =============================================================================
# F: Write-blocker confirmation
# =============================================================================
test_f_write_blocker() {
    test_header "Category F: Write-blocker confirmation"

    # F1: confirm_write_blocker accepts 'y'
    local result
    result=$(echo "y" | python3 -c "
import sys
sys.path.insert(0, '${TOOLS_DIR}')
from ptforensictoolbase import ForensicToolBase
print(ForensicToolBase.confirm_write_blocker())
" 2>/dev/null | tail -1)
    assert_equal "F1: write-blocker accepts 'y'" "True" "${result}"

    # F2: confirm_write_blocker rejects 'n'
    result=$(echo "n" | python3 -c "
import sys
sys.path.insert(0, '${TOOLS_DIR}')
from ptforensictoolbase import ForensicToolBase
print(ForensicToolBase.confirm_write_blocker())
" 2>/dev/null | tail -1)
    assert_equal "F2: write-blocker rejects 'n'" "False" "${result}"

    # F3: confirm_write_blocker rejects empty input (default no)
    result=$(echo "" | python3 -c "
import sys
sys.path.insert(0, '${TOOLS_DIR}')
from ptforensictoolbase import ForensicToolBase
print(ForensicToolBase.confirm_write_blocker())
" 2>/dev/null | tail -1)
    assert_equal "F3: write-blocker rejects empty (default N)" "False" "${result}"
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptforensictoolbase\n\n'
    test_a_static_helpers
    test_b_hash_boundaries
    test_c_image_validation
    test_d_fs_metadata
    test_e_command_helpers
    test_f_write_blocker
    print_summary "ptforensictoolbase"
}

main "$@"