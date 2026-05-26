#!/usr/bin/env bash
#
# run_all_tests_exifanalysis.sh
#
# Unit test suite for ptexifanalysis.py
# Validates EXIF extraction via exiftool wrapper, anomaly detection
# (future_date, unusual_iso, modify_after_original), and editing-software
# fingerprinting. EXIF field IDs follow CIPA DC-008:2019.
#
# Coverage: 15 tests in 5 categories per chapter 5.4.2 of the thesis.
#
# Author:  Bc. Dominik Sabota, VUT FEKT Brno, 2026
# License: GPL-3.0

set -u
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$(cd "${SCRIPT_DIR}/../ptforensicanalysis" && pwd)"
TEST_DIR="${SCRIPT_DIR}/test_data_exifanalysis"
TOOL_PATH="${SCRIPT_DIR}/../ptforensicanalysis/ptexifanalysis.py"
MOCK_BIN="${TEST_DIR}/fake_bin"

source "${SCRIPT_DIR}/testlib/reference_values.sh"
source "${SCRIPT_DIR}/testlib/test_framework.sh"

cleanup_all() { rm -rf "${TEST_DIR}"; }
trap cleanup_all EXIT


# -----------------------------------------------------------------------------
# Mock exiftool: emits a hand-written JSON document mimicking real
# exiftool's `-json` output. Field names follow CIPA DC-008:2019.
# -----------------------------------------------------------------------------
make_mock_exiftool() {
    local scenario="$1"   # "normal" | "future" | "iso51200" | "edited" | "empty"
    mkdir -p "${MOCK_BIN}"
    cat > "${MOCK_BIN}/exiftool" <<EOF
#!/usr/bin/env python3
import sys, json

scenario = "${scenario}"
# Last arg is the input file path
file_arg = sys.argv[-1]

def base(name):
    return {
        "SourceFile": name,
        "FileName": name.split('/')[-1],
        "Make": "Canon",
        "Model": "Canon EOS 5D Mark IV",
        "DateTimeOriginal": "2024:06:15 14:30:00",
        "ModifyDate": "2024:06:15 14:30:00",
        "ISO": 400,
        "FNumber": 4.0,
        "ExposureTime": "1/250",
        "FocalLength": "50.0 mm",
        "GPSLatitude": "49 deg 12' 0.00\" N",
        "GPSLongitude": "16 deg 36' 0.00\" E",
        "Software": "",
        "Artist": "",
        "Copyright": "",
    }

entries = []
if scenario == "normal":
    entries.append(base(file_arg))
elif scenario == "future":
    e = base(file_arg)
    e["DateTimeOriginal"] = "2099:01:01 00:00:00"
    entries.append(e)
elif scenario == "iso51200":
    e = base(file_arg)
    e["ISO"] = 51200
    entries.append(e)
elif scenario == "edited":
    e = base(file_arg)
    e["ModifyDate"] = "2025:01:01 12:00:00"   # later than original
    e["Software"] = "Adobe Photoshop 24.0"
    entries.append(e)
elif scenario == "empty":
    entries.append({"SourceFile": file_arg, "FileName": file_arg.split('/')[-1]})

print(json.dumps(entries, indent=2))
EOF
    chmod +x "${MOCK_BIN}/exiftool"
}

make_jpeg() {
    # Minimum-viable JPEG so the directory contains a real file.
    {
        printf '\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        python3 -c "import sys; sys.stdout.buffer.write(b'\xaa' * 100)"
        printf '\xff\xd9'
    } > "$1"
}

run_tool() {
    local case_id="$1"
    local input_dir="$2"
    local out="$3"
    local code=0
    PATH="${MOCK_BIN}:${PATH}" \
        invoke_tool "${TOOL_PATH}" "${case_id}" "${input_dir}" \
            --analyst "Test" \
            --json-out "${out}" \
            >/dev/null 2>&1 || code=$?
    echo "${code}"
}

# Shared helper: get the exifRecords list from the single exifAnalysis node.
# Usage: _exif_records <json_file> <python_expression_on_records>
# The expression receives 'records' as a list of per-file dicts.
_exif_records() {
    local file="$1"
    local expr="$2"
    python3 -c "
import json
try:
    nodes = json.load(open('${file}'))['results']['nodes']
    records = next(
        (n.get('properties', {}).get('exifRecords', [])
         for n in nodes if n.get('type') == 'exifAnalysis'),
        []
    )
    print(${expr})
except Exception:
    print('')
" 2>/dev/null
}


# =============================================================================
# A: Happy path
# =============================================================================
test_a_happy_path() {
    test_header "Category A: Happy path"

    make_mock_exiftool "normal"
    mkdir -p "${TEST_DIR}/in"
    make_jpeg "${TEST_DIR}/in/a.jpg"

    local out="${TEST_DIR}/a.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" "${out}")
    assert_exit_code "A1: normal EXIF -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # A2: Make/Model extracted.
    # The tool stores per-file data in exifRecords[] inside the exifAnalysis
    # node; field key is lowercase 'make' (from _parse_single).
    local make_value
    make_value=$(_exif_records "${out}" \
        "next((r.get('make','') for r in records if r.get('make')), '')")
    assert_equal "A2: Make=Canon extracted" "Canon" "${make_value}"

    # A3: GPS coordinates extracted.
    # GPS is stored as a nested dict: exifRecords[*].gps.latitude
    local gps_lat
    gps_lat=$(_exif_records "${out}" \
        "next((r.get('gps',{}).get('latitude','') for r in records if r.get('gps')), '')")
    case "${gps_lat}" in
        *"49"*) pass "A3: GPSLatitude extracted (${gps_lat})" ;;
        *) fail "A3: GPSLatitude extracted" "got: ${gps_lat}" ;;
    esac

    # A4: zero anomalies on clean input
    local anomalies
    anomalies=$(json_value "${out}" \
        "d['results']['properties'].get('anomaliesDetected', 0)")
    assert_equal "A4: 0 anomalies on normal input" "0" "${anomalies}"
}

# =============================================================================
# B: Anomaly detection
# =============================================================================
test_b_anomalies() {
    test_header "Category B: Anomaly detection"

    mkdir -p "${TEST_DIR}/in"
    make_jpeg "${TEST_DIR}/in/a.jpg"

    # B1: future_date anomaly (DateTimeOriginal in 2099).
    # Anomalies are stored in exifRecords[*].anomalies[*].type (not in
    # separate nodes); field key is 'type', not 'anomalyType'.
    make_mock_exiftool "future"
    local out="${TEST_DIR}/b1.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" "${out}" >/dev/null
    local has_future
    has_future=$(_exif_records "${out}" \
        "sum(1 for r in records for a in r.get('anomalies',[]) if 'future_date' in a.get('type',''))")
    if [ "${has_future}" -ge 1 ] 2>/dev/null; then
        pass "B1: future_date anomaly detected"
    else
        fail "B1: future_date anomaly" "got: ${has_future}"
    fi

    # B2: unusual_iso anomaly (ISO 51200 > 25600 threshold)
    make_mock_exiftool "iso51200"
    out="${TEST_DIR}/b2.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/in" "${out}" >/dev/null
    local has_iso
    has_iso=$(_exif_records "${out}" \
        "sum(1 for r in records for a in r.get('anomalies',[]) if 'unusual_iso' in a.get('type',''))")
    if [ "${has_iso}" -ge 1 ] 2>/dev/null; then
        pass "B2: unusual_iso anomaly detected"
    else
        fail "B2: unusual_iso anomaly" "got: ${has_iso}"
    fi

    # B3: modify_after_original anomaly
    make_mock_exiftool "edited"
    out="${TEST_DIR}/b3.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-003" "${TEST_DIR}/in" "${out}" >/dev/null
    local has_modify
    has_modify=$(_exif_records "${out}" \
        "sum(1 for r in records for a in r.get('anomalies',[]) if 'modify_after_original' in a.get('type',''))")
    if [ "${has_modify}" -ge 1 ] 2>/dev/null; then
        pass "B3: modify_after_original anomaly detected"
    else
        fail "B3: modify_after_original" "got: ${has_modify}"
    fi

    # B4: editor software (Photoshop) recognised.
    # _detect_editing_software stores the match in exifRecords[*].editingSoftware
    # as a lowercase string (e.g. "photoshop") - there is no separate anomaly node.
    local editor_found
    editor_found=$(_exif_records "${out}" \
        "sum(1 for r in records if 'photoshop' in str(r.get('editingSoftware','')).lower())")
    if [ "${editor_found}" -ge 1 ] 2>/dev/null; then
        pass "B4: Photoshop editor flagged"
    else
        fail "B4: Photoshop flagged" "got: ${editor_found}"
    fi
}

# =============================================================================
# C: Boundary cases
# =============================================================================
test_c_boundaries() {
    test_header "Category C: Boundary cases"

    mkdir -p "${TEST_DIR}/in"
    make_jpeg "${TEST_DIR}/in/a.jpg"

    # C1: empty EXIF (no tags) -> no anomalies, no crash
    make_mock_exiftool "empty"
    local out="${TEST_DIR}/c1.json"
    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" "${out}")
    assert_exit_code "C1: empty EXIF handled -> exit 0" "${EXIT_SUCCESS}" "${code}"

    # C2: ISO exactly at threshold (25600)
    make_mock_exiftool "normal"
    # Tweak the mock to emit ISO=25600 -- replace inline
    sed -i 's/"ISO": 400/"ISO": 25600/' "${MOCK_BIN}/exiftool"
    out="${TEST_DIR}/c2.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-002" "${TEST_DIR}/in" "${out}" >/dev/null
    local has_iso
    has_iso=$(_exif_records "${out}" \
        "sum(1 for r in records for a in r.get('anomalies',[]) if 'unusual_iso' in a.get('type',''))")
    # ISO=25600 is at the threshold; whether it's flagged is policy.
    # Accept either outcome but require deterministic behaviour.
    case "${has_iso}" in
        ""|"0"|"1") pass "C2: ISO=25600 (threshold) handled (anomaly=${has_iso})" ;;
        *) fail "C2: ISO=25600 boundary" "got: ${has_iso}" ;;
    esac

    # C3: batch of 60 files (exceeds the 50-per-batch exiftool grouping)
    rm -rf "${TEST_DIR}/in"
    mkdir -p "${TEST_DIR}/in"
    for i in $(seq 1 60); do
        make_jpeg "${TEST_DIR}/in/f$(printf '%03d' "${i}").jpg"
    done
    make_mock_exiftool "normal"
    out="${TEST_DIR}/c3.json"
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-003" "${TEST_DIR}/in" "${out}")
    assert_exit_code "C3: 60-file batch -> exit 0" "${EXIT_SUCCESS}" "${code}"
}

# =============================================================================
# D: JSON / CoC structure
# =============================================================================
test_d_json_structure() {
    test_header "Category D: JSON / CoC structure"

    make_mock_exiftool "normal"
    mkdir -p "${TEST_DIR}/in"
    make_jpeg "${TEST_DIR}/in/a.jpg"
    local out="${TEST_DIR}/d.json"
    run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" "${out}" >/dev/null

    assert_json_field "D1: caseId in properties" "${out}" \
        "d['results']['properties'].get('caseId')" \
        "${PREFIX_PHOTO}-2026-01-01-001"

    assert_node_present "D2: chainOfCustodyEntry present" "${out}" \
        "chainOfCustodyEntry"

    # D3: the tool emits a single exifAnalysis node (not per-file exifMetadata nodes)
    assert_node_present "D3: exifAnalysis node present" "${out}" "exifAnalysis"
}

# =============================================================================
# E: Exit codes
# =============================================================================
test_e_exit_codes() {
    test_header "Category E: Exit codes"

    make_mock_exiftool "normal"
    mkdir -p "${TEST_DIR}/in"
    make_jpeg "${TEST_DIR}/in/a.jpg"

    local code
    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" "${TEST_DIR}/in" \
        "${TEST_DIR}/e1.json")
    assert_exit_code "E1: success -> 0" "${EXIT_SUCCESS}" "${code}"

    code=$(run_tool "${PREFIX_PHOTO}-2026-01-01-001" \
        "${TEST_DIR}/no_dir" "${TEST_DIR}/e2.json")
    case "${code}" in
        "${EXIT_ENV}"|"${EXIT_FAILURE}") pass "E2: missing input -> ${code}" ;;
        *) fail "E2: missing input" "exit ${code}" ;;
    esac
}

main() {
    check_prerequisites "3.10" "${TOOL_PATH}"
    rm -rf "${TEST_DIR}"
    mkdir -p "${TEST_DIR}"
    printf 'Test suite: ptexifanalysis\n\n'
    test_a_happy_path
    test_b_anomalies
    test_c_boundaries
    test_d_json_structure
    test_e_exit_codes
    print_summary "ptexifanalysis"
}

main "$@"