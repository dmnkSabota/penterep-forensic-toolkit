#!/usr/bin/env bash
#
# run_all_tests_forensicimaging.sh
#
# Unit test suite for ptforensicimaging.py
# Validates the dc3dd / ddrescue dispatch, sidecar .sha256 generation,
# write-blocker confirmation gating, and prerequisite checks.
#
# Coverage: 22 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_forensicimaging"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptforensicimaging.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

# Absolute path to python3, resolved against the parent shell's PATH.
# B3 and E2 invoke the tool with a deliberately-empty PATH to make dc3dd
# unresolvable; if python3 itself were looked up under that empty PATH,
# bash would fail with exit 127 before the tool ever ran. Using the
# absolute path bypasses PATH lookup for the python3 binary while still
# letting the child process inherit the restricted PATH.
PYTHON3_BIN="$(command -v python3)"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock dc3dd
#
# The production tool calls real dc3dd as:
#   dc3dd if=<src> of=<dst> hash=sha256 log=<log>
# and then parses the SHA-256 hex token out of <log> via the regex in
# PtForensicImaging._parse_dc3dd_hash() (any line containing "sha256"
# whose tokens include a 64-char [0-9a-f] string).
#
# Hash is recomputed from the destination via an INDEPENDENT sha256sum
# rather than looked up in a hard-coded table -- this is why C2 / C3
# can compare against published FIPS 180-4 vectors and detect a
# regression where the tool reads the wrong log field.
# -----------------------------------------------------------------------------
make_mock_dc3dd() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/dc3dd" <<'EOF'
#!/usr/bin/env bash
# Mock dc3dd. Handles --version, parses if= / of= / log= / hash= just
# like the real tool, and writes the SHA-256 line into the log file.
if [ "${1:-}" = "--version" ]; then
    echo "dc3dd 7.2.646"
    exit 0
fi
SRC=""; DST=""; LOG=""
for a in "$@"; do
    case "$a" in
        if=*)   SRC="${a#if=}" ;;
        of=*)   DST="${a#of=}" ;;
        log=*)  LOG="${a#log=}" ;;
        hash=*) : ;;
        *)      : ;;
    esac
done
[ -z "${SRC}" ] || [ -z "${DST}" ] && exit 64
[ ! -e "${SRC}" ] && exit 1
cp "${SRC}" "${DST}" || exit 1
HASH=$(sha256sum "${DST}" | awk '{print $1}')
# Real dc3dd writes its SHA-256 result into the log file given by log=.
# _parse_dc3dd_hash() looks for a 64-char hex token on any line that
# contains the substring "sha256", so emit a structure similar to the
# real tool's log output.
if [ -n "${LOG}" ]; then
    {
        echo "dc3dd 7.2.646 started at $(date -u +%FT%TZ)"
        echo "compiled options:"
        echo "command line: dc3dd if=${SRC} of=${DST} hash=sha256 log=${LOG}"
        echo "sector size: 512 bytes (assumed)"
        echo ""
        echo "input results for device \`${SRC}':"
        echo "    sha256 total (${SRC}): ${HASH}"
        echo ""
        echo "output results for file \`${DST}':"
        echo "    bytes out: $(stat -c%s "${DST}") sectors out"
        echo ""
        echo "dc3dd completed at $(date -u +%FT%TZ)"
    } > "${LOG}"
fi
# Real dc3dd also writes a progress line to stderr; keep this for
# parity but it is not what the parser reads.
echo "    sha256 (${SRC}): ${HASH}" >&2
exit 0
EOF
    chmod +x "${MOCK_BIN}/dc3dd"
}


# -----------------------------------------------------------------------------
# Mock ddrescue
#
# Invoked by the production tool as:
#   ddrescue -f -v <device> <image> <mapfile>
# The tool computes the SHA-256 itself by running sha256sum afterwards
# (via _compute_hash), so the mock just has to produce a copy and an
# empty mapfile.
# -----------------------------------------------------------------------------
make_mock_ddrescue() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/ddrescue" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then
    echo "GNU ddrescue 1.27"
    exit 0
fi
# Strip known options, collect positionals.
POS=()
while [ $# -gt 0 ]; do
    case "$1" in
        -f|-v|-q|--force|--verbose|--quiet) shift ;;
        --) shift; while [ $# -gt 0 ]; do POS+=("$1"); shift; done ;;
        -*) shift ;;
        *)  POS+=("$1"); shift ;;
    esac
done
SRC="${POS[0]:-}"
DST="${POS[1]:-}"
MAP="${POS[2]:-}"
[ -z "${SRC}" ] || [ -z "${DST}" ] && exit 1
[ ! -e "${SRC}" ] && exit 1
cp "${SRC}" "${DST}" 2>/dev/null || exit 1
[ -n "${MAP}" ] && printf '# Mock ddrescue mapfile\n' > "${MAP}"
exit 0
EOF
    chmod +x "${MOCK_BIN}/ddrescue"
}


# -----------------------------------------------------------------------------
# Create a 1 MiB source file with structured content. Prints the
# independent SHA-256 reference on stdout.
# -----------------------------------------------------------------------------
make_test_source() {
    python3 -c "
with open('${TEST_DIR}/source.img', 'wb') as f:
    for i in range(1024):
        f.write(bytes([i & 0xff] * 1024))
"
    sha256sum "${TEST_DIR}/source.img" | awk '{print $1}'
}


# -----------------------------------------------------------------------------
# run_tool <case_id> <src> <tool> <json_out> [extra_args]
#
# Invokes the tool with the mocks on PATH and auto-confirms the
# write-blocker prompt via a here-string ("y"). Stdout / stderr are
# discarded; the function echoes the captured exit code.
#
# NOTE: --dry-run is deliberately NOT passed, because it would short-
# circuit imaging and prevent the JSON / sidecar assertions from
# succeeding (see header).
# -----------------------------------------------------------------------------
run_tool() {
    local case_id="$1" src="$2" tool="$3" out="$4"
    local extra="${5:-}"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${src}" "${tool}" \
            --analyst "Test" \
            --output-dir "${TEST_DIR}/images" \
            --json-out "${out}" \
            ${extra} \
            <<< "y" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    make_mock_dc3dd
    make_mock_ddrescue
    local ref_hash
    ref_hash=$(make_test_source)
    mkdir -p "${TEST_DIR}/images"

    # A1: dc3dd path completes with exit 0
    local out="${TEST_DIR}/a1.json"
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/source.img" \
        "dc3dd" "${out}")
    assert_exit_code "A1: dc3dd happy path -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: sourceHash matches independent sha256sum reference
    assert_json_field "A2: sourceHash matches independent sha256sum" "${out}" \
        "d['results']['properties'].get('sourceHash', '')" "${ref_hash}"

    # A3: sidecar .sha256 created next to the image
    local sidecar
    sidecar=$(find "${TEST_DIR}/images" -name "*.sha256" 2>/dev/null | head -1)
    if [ -n "${sidecar}" ] && [ -s "${sidecar}" ]; then
        pass "A3: sidecar .sha256 written"
        # A4: sidecar contents match sha256sum format ("<hash>  <filename>").
        # Guarded inside the success branch so an empty ${sidecar} cannot
        # cause `awk` to fall through to reading stdin and hang.
        local sidecar_hash
        sidecar_hash=$(awk '{print $1}' "${sidecar}")
        assert_equal "A4: sidecar hash matches reference" \
            "${ref_hash}" "${sidecar_hash}"
    else
        fail "A3: sidecar .sha256 written" "no .sha256 file found"
        fail "A4: sidecar hash matches reference" "skipped: A3 produced no sidecar"
    fi

    # A5: ddrescue path also completes
    out="${TEST_DIR}/a5.json"
    code=$(run_tool "${PREFIX_COC}-2026-01-01-002" "${TEST_DIR}/source.img" \
        "ddrescue" "${out}")
    assert_exit_code "A5: ddrescue happy path -> exit 0" "${EXIT_SUCCESS}" "${code}"
}

# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    make_mock_dc3dd
    make_mock_ddrescue
    make_test_source >/dev/null
    mkdir -p "${TEST_DIR}/images"

    # B1: invalid tool name. argparse uses choices=["dc3dd", "ddrescue"]
    # and rejects with exit 2 (which is neither EXIT_ENV nor EXIT_FAILURE
    # in the toolkit's convention, but is the standard argparse code).
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/source.img" \
        "invalid_tool" "${TEST_DIR}/b1.json")
    case "${code}" in
        2|"${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B1: invalid tool -> ${code}" ;;
        *) fail "B1: invalid tool" "exit ${code}" ;;
    esac

    # B2: nonexistent source device -> _check_device fails -> exit 1
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "/dev/no_such_device" \
        "dc3dd" "${TEST_DIR}/b2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B2: missing source -> ${code}" ;;
        *) fail "B2: missing source" "exit ${code}" ;;
    esac

    # B3: requested tool binary missing from PATH.
    # Use an empty directory as PATH so neither dc3dd nor `which` itself
    # can be resolved. _check_command() catches the resulting OSError
    # and returns False. /usr/bin:/bin cannot be used here because real
    # dc3dd is typically installed at /usr/bin/dc3dd on a forensic
    # workstation, which would let the tool succeed against a regular
    # file source and exit 0.
    # Production main() does `return 0 if props.get("sourceHash") else 1`,
    # so missing prerequisites surface as EXIT_FAILURE (1) rather than
    # EXIT_ENV (99). Accept either.
    local empty_path="${TEST_DIR}/empty_path"
    mkdir -p "${empty_path}"
    code=0
    PATH="${empty_path}" "${PYTHON3_BIN}" "${TOOL_PATH}" \
        "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/source.img" "dc3dd" \
        --analyst Test --output-dir "${TEST_DIR}/images" \
        --json-out "${TEST_DIR}/b3.json" \
        <<< "y" >/dev/null 2>&1 || code=$?
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B3: missing dc3dd binary -> ${code}" ;;
        *) fail "B3: missing dc3dd binary" "exit ${code}" ;;
    esac

    # B4: write-blocker NOT confirmed -> exit 99
    code=0
    PATH="${MOCK_BIN}:${PATH}" python3 "${TOOL_PATH}" \
        "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/source.img" "dc3dd" \
        --analyst Test --output-dir "${TEST_DIR}/images" \
        --json-out "${TEST_DIR}/b4.json" \
        <<< "n" >/dev/null 2>&1 || code=$?
    assert_exit_code "B4: write-blocker declined -> 99" "${EXIT_ENV}" "${code}"
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    make_mock_dc3dd
    mkdir -p "${TEST_DIR}/images"

    # C1: 1-byte source file
    printf 'a' > "${TEST_DIR}/c1_tiny"
    local ref
    ref=$(sha256sum "${TEST_DIR}/c1_tiny" | awk '{print $1}')
    local out="${TEST_DIR}/c1.json"
    run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/c1_tiny" \
        "dc3dd" "${out}" >/dev/null
    assert_json_field "C1: 1-byte source produces matching hash" "${out}" \
        "d['results']['properties'].get('sourceHash', '')" "${ref}"

    # C2: source whose SHA-256 is the NIST FIPS 180-4 'abc' vector
    printf 'abc' > "${TEST_DIR}/c2_abc"
    out="${TEST_DIR}/c2.json"
    run_tool "${PREFIX_COC}-2026-01-01-002" "${TEST_DIR}/c2_abc" \
        "dc3dd" "${out}" >/dev/null
    assert_json_field "C2: SHA-256 of 'abc' matches FIPS 180-4 B.1" "${out}" \
        "d['results']['properties'].get('sourceHash', '')" "${NIST_SHA256_ABC}"

    # C3: empty source file (FIPS 180-4 empty-string vector)
    : > "${TEST_DIR}/c3_empty"
    out="${TEST_DIR}/c3.json"
    run_tool "${PREFIX_COC}-2026-01-01-003" "${TEST_DIR}/c3_empty" \
        "dc3dd" "${out}" >/dev/null
    assert_json_field "C3: SHA-256 of empty matches FIPS 180-4 empty" "${out}" \
        "d['results']['properties'].get('sourceHash', '')" "${NIST_SHA256_EMPTY}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    make_mock_dc3dd
    make_test_source >/dev/null
    mkdir -p "${TEST_DIR}/images"
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/source.img" \
        "dc3dd" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_COC}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: imagePath populated and under the output directory
    local ipath
    ipath=$(json_value "${out}" "d['results']['properties'].get('imagePath', '')")
    case "${ipath}" in
        */images/*) pass "D3: imagePath under output-dir (${ipath})" ;;
        *) fail "D3: imagePath populated" "got: '${ipath}'" ;;
    esac

    # D4: sourceHash is 64 hex chars
    local h
    h=$(json_value "${out}" "d['results']['properties'].get('sourceHash', '')")
    if [ "${#h}" -eq 64 ]; then
        pass "D4: sourceHash is 64 hex chars"
    else
        fail "D4: sourceHash length" "got ${#h} chars: ${h}"
    fi

    # D5: writeBlockerConfirmed present and True
    # writeBlockerConfirmed = not self.dry_run, so it is True whenever
    # --dry-run is absent (i.e. always in this suite).
    local wb
    wb=$(json_value "${out}" \
        "d['results']['properties'].get('writeBlockerConfirmed')")
    assert_equal "D5: writeBlockerConfirmed=True" "True" "${wb}"
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    make_mock_dc3dd
    make_test_source >/dev/null
    mkdir -p "${TEST_DIR}/images"

    # E1: success -> 0
    local code
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/source.img" \
        "dc3dd" "${TEST_DIR}/e1.json")
    assert_exit_code "E1: success -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: missing tool. As in B3, an empty-directory PATH is required to
    # guarantee dc3dd is unresolvable on a forensic workstation where it
    # is normally installed in /usr/bin. Production main() collapses this
    # to EXIT_FAILURE (1), not EXIT_ENV (99). Accept either.
    local empty_path="${TEST_DIR}/empty_path"
    mkdir -p "${empty_path}"
    code=0
    PATH="${empty_path}" "${PYTHON3_BIN}" "${TOOL_PATH}" \
        "${PREFIX_COC}-2026-01-01-001" "${TEST_DIR}/source.img" "dc3dd" \
        --analyst Test --output-dir "${TEST_DIR}/images" \
        --json-out "${TEST_DIR}/e2.json" \
        <<< "y" >/dev/null 2>&1 || code=$?
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing tool -> ${code}" ;;
        *) fail "E2: missing tool" "exit ${code}" ;;
    esac

    # E3: missing source -> 1
    code=$(run_tool "${PREFIX_COC}-2026-01-01-001" "/dev/totally_missing" \
        "dc3dd" "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E3: missing source -> ${code}" ;;
        *) fail "E3: missing source" "got ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptforensicimaging\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptforensicimaging"
}

main "$@"