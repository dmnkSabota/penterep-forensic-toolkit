#!/usr/bin/env bash
#
# run_all_tests_imageverification.sh
#
# Unit test suite for ptimageverification.py
# Validates SHA-256 verification of forensic images, MISMATCH detection,
# hash format validation, and .E01 path delegation to ewfverify.
#
# Coverage: 19 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_imageverification"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptimageverification.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock ewfverify: prints output that includes the file's actual SHA-256
# (computed independently via sha256sum) so the toolkit can parse it.
#
# IMPORTANT: the toolkit's regex for the .E01 path is
#     re.search(r'sha256.*?:\s*([a-f0-9]{64})', line, re.IGNORECASE)
# which requires the substring "sha256" without a hyphen. Real
# libewf-tools ewfverify prints "MD5 hash ...", "SHA1 hash ...",
# "SHA256 hash ..." (also no hyphens), so this mock matches reality.
# -----------------------------------------------------------------------------
make_mock_ewfverify() {
    local target_hash="$1"
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/ewfverify" <<EOF
#!/usr/bin/env bash
echo "ewfverify 20140807"
echo "Hash values:"
echo "SHA256 hash calculated over data:    ${target_hash}"
echo "SHA256 hash stored in segment files: ${target_hash}"
exit 0
EOF
    chmod +x "${MOCK_BIN}/ewfverify"
}

make_image() {
    local content="$1"
    local path="$2"
    printf '%s' "${content}" > "${path}"
}

run_tool() {
    local case_id="$1"
    local image="$2"
    local expected_hash="$3"
    local out="$4"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${image}" "${expected_hash}" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    # A1: VERIFIED on .dd image whose hash matches expected.
    # Both values are independently traceable: the image content is 'abc',
    # the expected hash is the FIPS 180-4 vector.
    make_image "abc" "${TEST_DIR}/a1.dd"
    local out="${TEST_DIR}/a1.json"
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/a1.dd" \
        "${NIST_SHA256_ABC}" "${out}")
    assert_exit_code "A1: matching hash -> exit 0" "${EXIT_SUCCESS}" "${code}"

    assert_json_field "A2: verificationStatus=VERIFIED" "${out}" \
        "d['results']['properties'].get('verificationStatus')" "VERIFIED"

    assert_json_field "A3: hashMatch=True" "${out}" \
        "d['results']['properties'].get('hashMatch')" "True"

    # A4: empty file matches FIPS 180-4 empty-string vector
    : > "${TEST_DIR}/a4.dd"
    out="${TEST_DIR}/a4.json"
    code=$(run_tool "${PREFIX_COC}-2026-01-01-002" "${TEST_DIR}/a4.dd" \
        "${NIST_SHA256_EMPTY}" "${out}")
    assert_exit_code "A4: empty file matches empty-string vector" \
        "${EXIT_SUCCESS}" "${code}"
}

# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    # B1: hash mismatch -> MISMATCH + exit 1
    make_image "abc" "${TEST_DIR}/b1.dd"
    local out="${TEST_DIR}/b1.json"
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/b1.dd" \
        "${REF_SHA256_MISMATCH}" "${out}")
    assert_exit_code "B1: mismatch -> exit 1" "${EXIT_FAILURE}" "${code}"

    assert_json_field "B2: verificationStatus=MISMATCH" "${out}" \
        "d['results']['properties'].get('verificationStatus')" "MISMATCH"

    # B3: nonexistent image
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" \
        "${TEST_DIR}/nonexistent.dd" "${NIST_SHA256_ABC}" \
        "${TEST_DIR}/b3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B3: missing image -> ${code}" ;;
        *) fail "B3: missing image" "exit ${code}" ;;
    esac

    # B4: malformed hash (too short)
    make_image "abc" "${TEST_DIR}/b4.dd"
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/b4.dd" \
        "deadbeef" "${TEST_DIR}/b4.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B4: short hash -> ${code}" ;;
        *) fail "B4: short hash" "exit ${code}" ;;
    esac

    # B5: malformed hash (non-hex)
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/b4.dd" \
        "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ" \
        "${TEST_DIR}/b5.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B5: non-hex hash -> ${code}" ;;
        *) fail "B5: non-hex hash" "exit ${code}" ;;
    esac
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    # C1: hash provided in upper case
    make_image "abc" "${TEST_DIR}/c1.dd"
    local out="${TEST_DIR}/c1.json"
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/c1.dd" \
        "${NIST_SHA256_ABC^^}" "${out}")
    assert_exit_code "C1: uppercase hash accepted" "${EXIT_SUCCESS}" "${code}"

    # C2: large image (1 MiB), independent verification
    dd if=/dev/zero of="${TEST_DIR}/c2_1mb.dd" bs=1M count=1 2>/dev/null
    local ref_hash
    ref_hash=$(sha256sum "${TEST_DIR}/c2_1mb.dd" | awk '{print $1}')
    out="${TEST_DIR}/c2.json"
    code=$(run_tool "${PREFIX_COC}-2026-01-01-002" "${TEST_DIR}/c2_1mb.dd" \
        "${ref_hash}" "${out}")
    assert_exit_code "C2: 1MiB image verified" "${EXIT_SUCCESS}" "${code}"

    # C3: .E01 path -> delegates to ewfverify
    make_image "dummy ewf content" "${TEST_DIR}/c3.E01"
    local ewf_hash
    ewf_hash=$(sha256sum "${TEST_DIR}/c3.E01" | awk '{print $1}')
    make_mock_ewfverify "${ewf_hash}"
    out="${TEST_DIR}/c3.json"
    code=$(run_tool "${PREFIX_COC}-2026-01-01-003" "${TEST_DIR}/c3.E01" \
        "${ewf_hash}" "${out}")
    assert_exit_code "C3: .E01 verification via ewfverify" \
        "${EXIT_SUCCESS}" "${code}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    make_image "abc" "${TEST_DIR}/d.dd"
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/d.dd" \
        "${NIST_SHA256_ABC}" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_COC}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: both sourceHash and imageHash recorded
    local sh ih
    sh=$(json_value "${out}" "d['results']['properties'].get('sourceHash')")
    ih=$(json_value "${out}" "d['results']['properties'].get('imageHash')")
    assert_equal "D3: sourceHash recorded" "${NIST_SHA256_ABC}" "${sh}"
    assert_equal "D4: imageHash recorded" "${NIST_SHA256_ABC}" "${ih}"

    # D5: hashMatch is a JSON boolean
    local hm
    hm=$(json_value "${out}" "d['results']['properties'].get('hashMatch')")
    case "${hm}" in
        "True"|"False") pass "D5: hashMatch is boolean (${hm})" ;;
        *) fail "D5: hashMatch is boolean" "got: '${hm}'" ;;
    esac
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    make_image "abc" "${TEST_DIR}/e.dd"

    # E1: match -> 0
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/e.dd" \
        "${NIST_SHA256_ABC}" "${TEST_DIR}/e1.json")
    assert_exit_code "E1: match -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: mismatch -> 1
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/e.dd" \
        "${REF_SHA256_MISMATCH}" "${TEST_DIR}/e2.json")
    assert_exit_code "E2: mismatch -> 1" "${EXIT_FAILURE}" "${code}"

    # E3: missing image -> 99
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/missing.dd" \
        "${NIST_SHA256_ABC}" "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E3: missing image -> ${code}" ;;
        *) fail "E3: missing image" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptimageverification\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptimageverification"
}

main "$@"