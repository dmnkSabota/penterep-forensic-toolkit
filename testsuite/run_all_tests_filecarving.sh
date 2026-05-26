#!/usr/bin/env bash
#
# run_all_tests_filecarving.sh
#
# Unit test suite for ptfilecarving.py
# Validates the PhotoRec carving pipeline: input format dispatch
# (.dd / .raw / .img / .001 / .e01 -> ewfexport), pexpect-driven
# interaction with PhotoRec, post-processing (identify validation,
# deduplication by SHA-256, triage into valid/corrupted/duplicates).
#
# Coverage: 20 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_filecarving"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptfilecarving.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock photorec: a Python script that satisfies the pexpect interaction
# expected by run_photorec() and then drops carved files into the
# recup_dir.1/ directory that the real PhotoRec would create.
#
# A Python mock is required (rather than a plain shell script) because
# pexpect drives PhotoRec one keystroke at a time through a PTY: the mock
# must echo prompts back through the PTY and consume single-byte responses
# without waiting for newlines. This requires switching stdin into raw
# mode, which a /bin/sh script cannot do portably.
#
# Files produced:
#   f00001-f00003.jpg  3 unique JPEGs (seeds 1-3, each >= 219 bytes)
#   f00004.png         1 padded 1x1 PNG (>= MIN_IMAGE_BYTES=100)
#   f00005.jpg         exact copy of f00001.jpg -> SHA-256 duplicate
# -----------------------------------------------------------------------------
make_mock_photorec() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/photorec" <<'PYEOF'
#!/usr/bin/env python3
"""
Mock PhotoRec for pexpect-driven unit tests.

PhotoRec is driven by pexpect, which sends individual keystrokes such as
'c' and '\r' (no newline appended). A PTY slave is in COOKED mode by
default, so the OS only delivers buffered input to the process after
receiving a newline; sys.stdin.read(1) would block indefinitely after
pexpect sent 'c'.

The mock therefore switches stdin to RAW mode before any read, so that
every character is delivered to os.read(0, 1) immediately, regardless of
whether a newline follows.
"""
import os, sys, shutil

# ── Parse /d <outdir> from argv ──────────────────────────────────────────────
args = sys.argv[1:]
outdir = None
for i, a in enumerate(args):
    if a == '/d' and i + 1 < len(args):
        outdir = args[i + 1] + '/recup_dir.1'
        break
if not outdir:
    outdir = 'recup_dir.1'

# ── Switch PTY stdin to raw mode ─────────────────────────────────────────────
# Without this, the OS line discipline holds input until a newline arrives.
# pexpect sends 'c' and '\r' as individual chars with no newline, so
# os.read(0, 1) would block forever in cooked mode.
_saved = None
try:
    import tty, termios
    _fd = sys.stdin.fileno()
    _saved = termios.tcgetattr(_fd)
    tty.setraw(_fd)
except Exception:
    _fd = None

# ── I/O helpers ───────────────────────────────────────────────────────────────
def pr(s):
    sys.stdout.write(s)
    sys.stdout.flush()

def rd():
    """Read exactly one byte from stdin (raw PTY)."""
    try:
        return os.read(0, 1)
    except Exception:
        return b''

# ── Emit pexpect prompts and consume matching keystrokes ─────────────────────
pr("Select a media (use Arrow keys, then press Enter):\r\n")
rd()   # consumes child.send("\r")

pr("P NTFS\r\n")
rd()   # consumes child.send("\r")

pr("Other\r\n")
rd()   # consumes child.send("\r")

pr("Free\r\n")
rd()   # consumes child.send("\r")

pr("Search directory\r\n")
rd()   # consumes child.send("c")  - raw mode required (see docstring)

# ── Create synthetic carved files ────────────────────────────────────────────
os.makedirs(outdir, exist_ok=True)

for i, seed in enumerate([1, 2, 3], 1):
    path = os.path.join(outdir, f'f0000{i}.jpg')
    with open(path, 'wb') as f:
        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')
        f.write(bytes([seed]) * 200)
        f.write(b'\xff\xd9')

path = os.path.join(outdir, 'f00004.png')
# Build a proper minimal 1×1 8-bit grayscale PNG so that `file -b`
# returns "PNG image data, 1 x 1, 8-bit grayscale, non-interlaced".
# IMPORTANT: a bare minimal PNG is only 67 bytes, but _constants.py
# defines MIN_IMAGE_BYTES = 100 and ForensicToolBase._validate_image_file()
# classifies anything smaller than that as 'invalid' - which deletes the
# file and excludes it from validImages / byFormat.png / validFiles.
# To keep the PNG byte-for-byte valid AND above the minimum, we insert
# a tEXt chunk (PNG-spec-compliant arbitrary metadata) as padding.
# Resulting size: ~267 bytes.
import struct, zlib as _zlib
def _png_chunk(name, data):
    c = name + data
    return struct.pack('>I', len(data)) + c + struct.pack('>I', _zlib.crc32(c) & 0xffffffff)
_ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0)   # 1×1, 8-bit greyscale
_idat = _zlib.compress(b'\x00\xff')                       # filter=None, pixel=white
_text = _png_chunk(b'tEXt', b'Comment\x00' + b'PAD' * 60)  # padding > MIN_IMAGE_BYTES
_png_bytes = (b'\x89PNG\r\n\x1a\n'
              + _png_chunk(b'IHDR', _ihdr)
              + _text
              + _png_chunk(b'IDAT', _idat)
              + _png_chunk(b'IEND', b''))
with open(path, 'wb') as f:
    f.write(_png_bytes)

shutil.copy(os.path.join(outdir, 'f00001.jpg'),
            os.path.join(outdir, 'f00005.jpg'))

pr("[ Quit ]\r\n")
rd()   # consumes child.send("\r")

# Restore terminal settings before exit (best-effort)
if _saved is not None and _fd is not None:
    try:
        import termios
        termios.tcsetattr(_fd, termios.TCSADRAIN, _saved)
    except Exception:
        pass

sys.exit(0)
PYEOF
    chmod +x "${MOCK_BIN}/photorec"
}

make_mock_identify() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/identify" <<'EOF'
#!/bin/sh
# Mock ImageMagick identify. Returns success for files that exist and
# contain known image signatures.
FILE="$1"
[ "$1" = "-format" ] && FILE="$3"
[ -f "${FILE}" ] || exit 1
# Peek first bytes
HEADER=$(head -c 4 "${FILE}" | od -An -tx1 | tr -d ' \n')
case "${HEADER}" in
    ffd8ff*) echo "${FILE} JPEG 100x100 RGB 8-bit"; exit 0 ;;
    89504e47) echo "${FILE} PNG 100x100 RGBA 8-bit"; exit 0 ;;
    *) exit 1 ;;
esac
EOF
    chmod +x "${MOCK_BIN}/identify"
}

make_mock_ewfexport() {
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/ewfexport" <<'EOF'
#!/bin/sh
# Mock ewfexport: convert .E01 -> .raw (here: copy).
SRC=""; DST=""
while [ $# -gt 0 ]; do
    case "$1" in
        -t) shift; DST="$1.raw" ;;
        -u|-q|-S|-f) : ;;
        *.E01) SRC="$1" ;;
    esac
    shift
done
[ -z "$SRC" ] || [ -z "$DST" ] && exit 1
cp "$SRC" "$DST"
exit 0
EOF
    chmod +x "${MOCK_BIN}/ewfexport"
}

make_test_image() {
    local ext="${1:-dd}"
    dd if=/dev/zero of="${TEST_DIR}/img.${ext}" bs=1M count=2 2>/dev/null
}

run_tool() {
    local case_id="$1"
    local image="$2"
    local out="$3"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${image}" \
            --analyst "Test" \
            --output-dir "${TEST_DIR}/carved" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    make_mock_photorec
    make_mock_identify
    make_test_image "dd"

    local out="${TEST_DIR}/a1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/img.dd" "${out}")
    assert_exit_code "A1: 4 unique files carved -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: number of valid (unique) files after dedup.
    # The tool writes 'validImages', not 'uniqueFiles'.
    local n
    n=$(json_value "${out}" "d['results']['properties'].get('validImages', 0)")
    assert_equal "A2: 4 unique files after dedup" "4" "${n}"

    # A3: duplicates counted separately
    local dup
    dup=$(json_value "${out}" "d['results']['properties'].get('duplicates', 0)")
    assert_equal "A3: 1 duplicate identified" "1" "${dup}"

    # A4: format breakdown
    local jpeg png
    jpeg=$(json_value "${out}" "d['results']['properties'].get('byFormat', {}).get('jpeg', 0)")
    png=$(json_value "${out}" "d['results']['properties'].get('byFormat', {}).get('png', 0)")
    assert_equal "A4a: 3 JPEG files" "3" "${jpeg}"
    assert_equal "A4b: 1 PNG file" "1" "${png}"
}

# =============================================================================
# B: Error conditions
# =============================================================================
test_b_errors() {
    test_header "Category B: Error conditions"

    make_mock_photorec
    make_mock_identify

    # B1: missing image
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/missing.dd" "${TEST_DIR}/b1.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B1: missing image -> ${code}" ;;
        *) fail "B1: missing image" "exit ${code}" ;;
    esac

    # B2: missing PhotoRec binary.
    # check_tools() calls _fail() which returns False; run() exits early;
    # main() returns 1 (validImages==0). Exit 99 is reserved for uncaught
    # exceptions. Accept either EXIT_FAILURE or EXIT_ENV.
    #
    # Case-ID hygiene: uses case_id 099 instead of a low number. Two
    # reasons matter:
    #   - On a forensic VM with real `testdisk` installed, PATH="/usr/bin:/bin"
    #     does not exclude photorec, and the tool would produce a non-empty
    #     {case_id}_photorec directory (still exiting 1, satisfying the
    #     assertion).
    #   - run_photorec() reuses existing PhotoRec output keyed on case_id;
    #     any later test sharing the same id would pick up B2's leftovers.
    # A unique high-numbered case_id keeps B2 independent of all other tests.
    # PATH="/usr/bin:/bin" is placed inside $() so the assignment is scoped
    # to the subshell and does not leak into the rest of the suite.
    make_test_image "dd"
    local code_b2
    code_b2=$(PATH="/usr/bin:/bin" python3 "${TOOL_PATH}" \
        "${PREFIX_PHOTO}-2026-01-01-099" "${TEST_DIR}/img.dd" \
        --analyst Test --output-dir "${TEST_DIR}/carved" \
        --json-out "${TEST_DIR}/b2.json" >/dev/null 2>&1; echo $?)
    case "${code_b2}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B2: missing photorec -> ${code_b2}" ;;
        *) fail "B2: missing photorec -> 99 or 1" "exit ${code_b2}" ;;
    esac

    # B3: unsupported file extension
    printf 'random data' > "${TEST_DIR}/b3_unknown.xyz"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/b3_unknown.xyz" "${TEST_DIR}/b3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "B3: unsupported extension -> ${code}" ;;
        *) fail "B3: unsupported extension" "exit ${code}" ;;
    esac
}

# =============================================================================
# C: Boundary cases / format dispatch
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    make_mock_photorec
    make_mock_identify
    make_mock_ewfexport

    # C1: .raw extension accepted
    make_test_image "raw"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/img.raw" "${TEST_DIR}/c1.json")
    assert_exit_code "C1: .raw extension accepted" "${EXIT_SUCCESS}" "${code}"

    # C2: .img extension accepted.
    make_test_image "img"
    local c2_log="${TEST_DIR}/c2_debug.log"
    code=$(PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" \
            "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/img.img" \
            --analyst Test --output-dir "${TEST_DIR}/carved" \
            --json-out "${TEST_DIR}/c2.json" \
            >"${c2_log}" 2>&1; echo $?)
    if [ "${code}" != "${EXIT_SUCCESS}" ]; then
        # Show last 10 lines of tool output to help diagnose the failure
        printf '  [C2-debug] tool exit=%s, last output:\n' "${code}"
        tail -10 "${c2_log}" | sed 's/^/    /'
    fi
    assert_exit_code "C2: .img extension accepted" "${EXIT_SUCCESS}" "${code}"

    # C3: .001 extension accepted (FTK-style)
    make_test_image "001"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/img.001" "${TEST_DIR}/c3.json")
    assert_exit_code "C3: .001 extension accepted" "${EXIT_SUCCESS}" "${code}"

    # C4: .E01 -> ewfexport conversion path
    make_test_image "E01"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-004" \
        "${TEST_DIR}/img.E01" "${TEST_DIR}/c4.json")
    assert_exit_code "C4: .E01 converted via ewfexport" "${EXIT_SUCCESS}" "${code}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    make_mock_photorec
    make_mock_identify
    make_test_image "dd"
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/img.dd" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_PHOTO}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: output triage directories exist.
    # The tool creates: {output_dir}/{case_id}_carved/valid  and  .../duplicates
    local cdir="${TEST_DIR}/carved/${PREFIX_PHOTO}-2026-01-01-001_carved"
    if [ -d "${cdir}/valid" ] && [ -d "${cdir}/duplicates" ]; then
        pass "D3: valid/ and duplicates/ created"
    else
        fail "D3: triage directories" "missing (looked in ${cdir})"
    fi

    # D4: every carved file has SHA-256.
    # Valid files are stored in validationDedup.properties.validFiles[],
    # not as separate carvedFile nodes.
    local with_hash
    with_hash=$(python3 -c "
import json
try:
    nodes = json.load(open('${out}'))['results']['nodes']
    files = next(
        (n.get('properties', {}).get('validFiles', [])
         for n in nodes if n.get('type') == 'validationDedup'),
        []
    )
    print(sum(1 for f in files if len(f.get('sha256', '')) == 64))
except Exception:
    print(0)
" 2>/dev/null)
    if [ "${with_hash:-0}" -ge 4 ] 2>/dev/null; then
        pass "D4: all carved files hashed (${with_hash} entries)"
    else
        fail "D4: carved files hashed" "got: ${with_hash}"
    fi

    # D5: source format recorded (sourceFormat is written to properties;
    # photorecTimeoutSeconds is not - PHOTOREC_TIMEOUT is used internally only).
    local src_fmt
    src_fmt=$(json_value "${out}" \
        "d['results']['properties'].get('sourceFormat', '')")
    if [ -n "${src_fmt}" ]; then
        pass "D5: sourceFormat recorded (${src_fmt})"
    else
        fail "D5: sourceFormat not recorded" "got: '${src_fmt}'"
    fi
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    make_mock_photorec
    make_mock_identify
    make_test_image "dd"

    # E1: success -> 0
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/img.dd" "${TEST_DIR}/e1.json")
    assert_exit_code "E1: success -> 0" "${EXIT_SUCCESS}" "${code}"

    # E2: missing photorec -> check_tools() returns False; main() returns 1.
    # Accept EXIT_FAILURE or EXIT_ENV (see B2 note).
    # Uses case_id 092 (NOT 002) for the same case-ID-hygiene reason
    # documented at B2: if the host has real photorec installed, this test
    # would otherwise leave a {002}_photorec/report.xml behind that could
    # pollute subsequent runs of C2 within the same test process.
    local code_e2
    code_e2=$(PATH="/usr/bin:/bin" python3 "${TOOL_PATH}" \
        "${PREFIX_PHOTO}-2026-01-01-092" "${TEST_DIR}/img.dd" \
        --analyst Test --output-dir "${TEST_DIR}/carved" \
        --json-out "${TEST_DIR}/e2.json" >/dev/null 2>&1; echo $?)
    case "${code_e2}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing photorec -> ${code_e2}" ;;
        *) fail "E2: missing photorec -> 99 or 1" "exit ${code_e2}" ;;
    esac

    # E3: missing image -> env or failure
    make_mock_photorec
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" \
        "${TEST_DIR}/no_such_image.dd" "${TEST_DIR}/e3.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E3: missing image -> ${code}" ;;
        *) fail "E3: missing image" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptfilecarving  [script-rev: 2026-05-25-r5]\n\n'
    test_a_happy_path
    test_b_errors
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptfilecarving"
}

main "$@"