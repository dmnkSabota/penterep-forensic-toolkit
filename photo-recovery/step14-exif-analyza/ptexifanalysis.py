#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptexifanalysis - Forensic EXIF metadata analysis tool

    ptexifanalysis is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptexifanalysis is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptexifanalysis.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import csv
import json
import subprocess
from collections import defaultdict, Counter
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/images"
EXIF_TIMEOUT       = 30    # seconds per file
EXIF_BATCH         = 50    # files per exiftool batch call

# Software names that indicate post-processing / editing
EDITING_SOFTWARE = {
    'photoshop', 'lightroom', 'gimp', 'affinity', 'capture one',
    'instagram', 'snapseed', 'vsco', 'facetune', 'pixelmator',
    'darktable', 'rawtherapee', 'luminar', 'on1', 'dxo',
}

# Quality score thresholds (% of files with DateTimeOriginal)
QUALITY_THRESHOLDS = {
    "excellent": 90,
    "good":      70,
    "fair":      50,
}


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtExifAnalysis:
    """
    Forensic EXIF metadata analysis tool – ptlibs compliant.

    Six-phase analysis process:
    1. Load master catalog from Step 13 (consolidated/)
    2. Verify ExifTool availability
    3. Batch-extract EXIF data with exiftool -j -G -a -s -n
    4. Analyse time, cameras, settings and GPS
    5. Detect edited photos and anomalies; compute quality score
    6. Save JSON database, CSV export and text report

    Complies with EXIF 2.32 / CIPA DC-008-2019 and ISO 12234-2:2001.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State
        self.catalog: Optional[Dict]     = None
        self.consolidated_dir            = self.output_dir / f"{self.case_id}_consolidated"
        self.analysis_dir                = self.output_dir / f"{self.case_id}_exif_analysis"

        # EXIF data store
        self._exif_db: List[Dict]        = []    # one dict per file
        self._timeline: Dict[str, List]  = defaultdict(list)
        self._gps_locations: List[Dict]  = []
        self._edited: List[Dict]         = []
        self._anomalies: List[Dict]      = []

        # Counters
        self._total              = 0
        self._with_exif          = 0
        self._without_exif       = 0
        self._with_datetime      = 0
        self._with_gps           = 0
        self._edited_count       = 0
        self._anomaly_count      = 0

        # Aggregates
        self._cameras: Counter   = Counter()
        self._iso_vals:    List[float] = []
        self._aperture_vals: List[float] = []
        self._focal_vals:  List[float] = []
        self._dates:       List[datetime] = []

        # Top-level JSON properties
        self.ptjsonlib.add_properties({
            "caseId":            self.case_id,
            "outputDirectory":   str(self.output_dir),
            "timestamp":         datetime.now(timezone.utc).isoformat(),
            "scriptVersion":     __version__,
            "totalFiles":        0,
            "filesWithExif":     0,
            "filesWithoutExif":  0,
            "withDatetime":      0,
            "withGps":           0,
            "editedPhotos":      0,
            "anomalies":         0,
            "uniqueCameras":     0,
            "dateRange":         {},
            "qualityScore":      None,
            "qualityPct":        None,
            "settingsRange":     {},
            "byCamera":          {},
            "dryRun":            self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------------------

    def _run_command(self, cmd: List[str], timeout: int = 300) -> Dict[str, Any]:
        """Execute a subprocess, return dict(success, stdout, stderr)."""
        result = {"success": False, "stdout": "", "stderr": "", "returncode": -1}
        if self.dry_run:
            ptprint(f"[DRY-RUN] {' '.join(str(c) for c in cmd)}",
                    "INFO", condition=not self.args.json)
            result["success"] = True
            result["stdout"]  = "[]"   # empty JSON array – safe to parse
            return result
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, check=False)
            result.update({
                "success":    proc.returncode == 0,
                "stdout":     proc.stdout.strip(),
                "stderr":     proc.stderr.strip(),
                "returncode": proc.returncode,
            })
        except subprocess.TimeoutExpired:
            result["stderr"] = f"Timeout after {timeout}s"
        except Exception as exc:
            result["stderr"] = str(exc)
        return result

    def _resolve_path(self, relative: str) -> Path:
        """Resolve a catalog-relative path to an absolute filesystem path."""
        return self.consolidated_dir / relative

    # -------------------------------------------------------------------------
    # PHASE 1 – LOAD MASTER CATALOG
    # -------------------------------------------------------------------------

    def load_master_catalog(self) -> bool:
        """
        Load master_catalog.json produced by Step 13.

        Returns:
            bool: True if catalog loaded successfully
        """
        ptprint("\n[STEP 1/6] Loading Master Catalog from Step 13",
                "TITLE", condition=not self.args.json)

        cat_file = self.consolidated_dir / "master_catalog.json"

        if not cat_file.exists():
            ptprint(f"✗ Not found: {cat_file}",
                    "ERROR", condition=not self.args.json)
            ptprint("  Please run Step 13 (Consolidation) first!",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "catalogLoad",
                properties={"success": False, "error": "master_catalog.json not found"}
            ))
            return False

        try:
            with open(cat_file, 'r', encoding='utf-8') as fh:
                self.catalog = json.load(fh)
        except Exception as exc:
            ptprint(f"✗ Cannot read catalog: {exc}",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "catalogLoad",
                properties={"success": False, "error": str(exc)}
            ))
            return False

        self._total = self.catalog["summary"]["totalFiles"]

        ptprint(f"✓ Catalog loaded: {cat_file.name}",
                "OK", condition=not self.args.json)
        ptprint(f"  Files to analyse: {self._total}",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_properties({"totalFiles": self._total})
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "catalogLoad",
            properties={"success": True, "totalFiles": self._total,
                        "sourceFile": str(cat_file)}
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 2 – CHECK EXIFTOOL
    # -------------------------------------------------------------------------

    def check_exiftool(self) -> bool:
        """
        Verify ExifTool is installed and retrieve its version.

        Returns:
            bool: True if exiftool found
        """
        ptprint("\n[STEP 2/6] Checking ExifTool",
                "TITLE", condition=not self.args.json)

        res = self._run_command(["which", "exiftool"], timeout=5)
        if not res["success"]:
            ptprint("✗ ExifTool not found",
                    "ERROR", condition=not self.args.json)
            ptprint("  Install: sudo apt-get install libimage-exiftool-perl",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "toolsCheck",
                properties={"success": False, "error": "exiftool not found"}
            ))
            return False

        ver_res = self._run_command(["exiftool", "-ver"], timeout=5)
        version = ver_res["stdout"] if ver_res["success"] else "unknown"

        ptprint(f"✓ ExifTool v{version}", "OK", condition=not self.args.json)
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "toolsCheck",
            properties={"success": True, "exiftoolVersion": version}
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 3 – BATCH EXIF EXTRACTION
    # -------------------------------------------------------------------------

    def _exiftool_batch(self, filepaths: List[Path]) -> List[Dict]:
        """
        Call exiftool on a batch of files and return list of parsed dicts.

        Uses: exiftool -j -G -a -s -n <files…>
        """
        cmd = ["exiftool", "-j", "-G", "-a", "-s", "-n"] + \
              [str(p) for p in filepaths]
        res = self._run_command(cmd, timeout=EXIF_TIMEOUT * len(filepaths))
        if not res["success"] or not res["stdout"]:
            return []
        try:
            return json.loads(res["stdout"])
        except Exception:
            return []

    def _parse_single(self, raw: Dict, file_info: Dict) -> Dict:
        """
        Flatten relevant EXIF fields from a raw exiftool dict.

        Helper keys tried in priority order for each logical field.
        """
        def get(*keys):
            for k in keys:
                v = raw.get(k)
                if v not in (None, "", "0000:00:00 00:00:00"):
                    return v
            return None

        return {
            # Identity
            "fileId":         file_info["id"],
            "filename":       file_info["filename"],
            "path":           file_info["path"],
            "recoveryMethod": file_info.get("recoveryMethod", ""),
            # Camera
            "make":           get("EXIF:Make",   "IFD0:Make"),
            "model":          get("EXIF:Model",  "IFD0:Model"),
            "serialNumber":   get("EXIF:SerialNumber", "MakerNotes:SerialNumber"),
            # Timestamps
            "datetimeOriginal": get("EXIF:DateTimeOriginal"),
            "createDate":       get("EXIF:CreateDate"),
            "modifyDate":       get("EXIF:ModifyDate", "IFD0:ModifyDate"),
            # Settings
            "iso":            get("EXIF:ISO"),
            "fNumber":        get("EXIF:FNumber", "EXIF:ApertureValue"),
            "exposureTime":   get("EXIF:ExposureTime"),
            "focalLength":    get("EXIF:FocalLength"),
            "flash":          get("EXIF:Flash"),
            # Dimensions
            "width":          get("EXIF:ExifImageWidth",  "File:ImageWidth"),
            "height":         get("EXIF:ExifImageHeight", "File:ImageHeight"),
            "orientation":    get("EXIF:Orientation",     "IFD0:Orientation"),
            # GPS (numeric with -n)
            "gpsLatitude":    get("EXIF:GPSLatitude"),
            "gpsLongitude":   get("EXIF:GPSLongitude"),
            "gpsAltitude":    get("EXIF:GPSAltitude"),
            # Software
            "software":       get("EXIF:Software", "IFD0:Software"),
        }

    def extract_exif(self) -> bool:
        """
        Phase 3 – batch-extract EXIF from every file in the master catalog.

        Files are processed in batches of EXIF_BATCH to avoid OS argument
        length limits and allow progress reporting.

        Returns:
            bool: True if at least one file yielded EXIF data
        """
        ptprint("\n[STEP 3/6] Extracting EXIF Data",
                "TITLE", condition=not self.args.json)
        ptprint(f"  Processing {self._total} files in batches of {EXIF_BATCH}…",
                "INFO", condition=not self.args.json)

        files = self.catalog["files"]
        total = len(files)

        for batch_start in range(0, total, EXIF_BATCH):
            batch = files[batch_start: batch_start + EXIF_BATCH]

            # Resolve absolute paths
            paths = [self._resolve_path(fi["path"]) for fi in batch]
            existing = [(fi, p) for fi, p in zip(batch, paths)
                        if p.exists() or self.dry_run]

            if not existing:
                continue

            raw_list = self._exiftool_batch([p for _, p in existing])

            # Match raw results back to file_info by index
            for idx, (fi, _) in enumerate(existing):
                raw = raw_list[idx] if idx < len(raw_list) else {}
                parsed = self._parse_single(raw, fi)

                # Only store if at least one meaningful field populated
                meaningful = sum(1 for k in ("datetimeOriginal", "make", "model",
                                             "iso", "gpsLatitude", "software")
                                 if parsed.get(k))
                if meaningful > 0:
                    self._exif_db.append(parsed)
                    self._with_exif += 1
                else:
                    self._without_exif += 1

            done = min(batch_start + EXIF_BATCH, total)
            ptprint(f"  {done}/{total} ({done * 100 // total}%)",
                    "INFO", condition=not self.args.json)

        ptprint(f"✓ With EXIF:    {self._with_exif}",
                "OK",      condition=not self.args.json)
        ptprint(f"  Without EXIF: {self._without_exif}",
                "WARNING", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "exifExtraction",
            properties={
                "filesWithExif":    self._with_exif,
                "filesWithoutExif": self._without_exif,
            }
        ))
        return self._with_exif > 0

    # -------------------------------------------------------------------------
    # PHASE 4 – ANALYSE
    # -------------------------------------------------------------------------

    def analyse_time(self) -> None:
        """
        Analyse DateTimeOriginal / CreateDate across all EXIF records.

        Builds self._dates, self._timeline, updates self._with_datetime.
        """
        ptprint("\n  [4a] Time analysis …", "INFO", condition=not self.args.json)

        for exif in self._exif_db:
            dt_str = exif.get("datetimeOriginal") or exif.get("createDate")
            if not dt_str:
                continue
            try:
                dt = datetime.strptime(str(dt_str), "%Y:%m:%d %H:%M:%S")
                self._dates.append(dt)
                exif["parsedDatetime"] = dt.isoformat()

                # Timeline bucket
                day_key = dt.strftime("%Y-%m-%d")
                self._timeline[day_key].append({
                    "filename": exif["filename"],
                    "time":     dt.strftime("%H:%M:%S"),
                    "camera":   f"{exif.get('make','?')} {exif.get('model','')}".strip(),
                })
                self._with_datetime += 1
            except (ValueError, TypeError):
                pass

        if self._dates:
            earliest = min(self._dates)
            latest   = max(self._dates)
            span     = (latest - earliest).days
            ptprint(f"    {earliest.date()} → {latest.date()}  ({span} days)",
                    "INFO", condition=not self.args.json)

    def analyse_cameras(self) -> None:
        """Count Make+Model combinations."""
        ptprint("  [4b] Camera analysis …", "INFO", condition=not self.args.json)

        for exif in self._exif_db:
            key = f"{exif.get('make','Unknown')} {exif.get('model','Unknown')}".strip()
            self._cameras[key] += 1

        ptprint(f"    {len(self._cameras)} unique device(s)",
                "INFO", condition=not self.args.json)

    def analyse_settings_gps(self) -> None:
        """Extract ISO / aperture / focal length ranges and GPS coordinates."""
        ptprint("  [4c] Settings + GPS …", "INFO", condition=not self.args.json)

        for exif in self._exif_db:
            # ISO
            if exif.get("iso"):
                try:
                    self._iso_vals.append(float(exif["iso"]))
                except (ValueError, TypeError):
                    pass

            # F-number / aperture
            if exif.get("fNumber"):
                try:
                    self._aperture_vals.append(float(exif["fNumber"]))
                except (ValueError, TypeError):
                    pass

            # Focal length (may arrive as "85 mm" or 85.0)
            if exif.get("focalLength"):
                try:
                    fl = float(str(exif["focalLength"]).replace("mm", "").strip())
                    self._focal_vals.append(fl)
                except (ValueError, TypeError):
                    pass

            # GPS
            if exif.get("gpsLatitude") and exif.get("gpsLongitude"):
                try:
                    lat = float(exif["gpsLatitude"])
                    lon = float(exif["gpsLongitude"])
                    self._gps_locations.append({
                        "filename":  exif["filename"],
                        "latitude":  lat,
                        "longitude": lon,
                        "altitude":  exif.get("gpsAltitude"),
                    })
                    self._with_gps += 1
                except (ValueError, TypeError):
                    pass

        ptprint(f"    GPS: {self._with_gps} photos",
                "INFO", condition=not self.args.json)

    def run_analysis_phases(self) -> None:
        """Run all four analysis sub-phases (4a–4d)."""
        ptprint("\n[STEP 4/6] Analysing EXIF Data",
                "TITLE", condition=not self.args.json)
        self.analyse_time()
        self.analyse_cameras()
        self.analyse_settings_gps()

    # -------------------------------------------------------------------------
    # PHASE 5 – EDIT DETECTION + QUALITY SCORE
    # -------------------------------------------------------------------------

    def detect_edits_and_anomalies(self) -> None:
        """
        Phase 5 – Scan every EXIF record for editing software tags and anomalies.

        Anomalies checked:
          - Future DateTimeOriginal
          - Unusually high ISO (>25600)
          - ModifyDate later than DateTimeOriginal (post-processing indicator)
        """
        ptprint("\n[STEP 5/6] Edit Detection and Anomaly Analysis",
                "TITLE", condition=not self.args.json)

        now = datetime.now()

        for exif in self._exif_db:
            # --- Edit detection ---
            sw = (exif.get("software") or "").lower()
            if sw and any(e in sw for e in EDITING_SOFTWARE):
                self._edited.append({
                    "filename": exif["filename"],
                    "software": exif["software"],
                })
                self._edited_count += 1
                exif["edited"] = True

            # --- Anomalies ---
            # Future date
            if exif.get("parsedDatetime"):
                try:
                    dt = datetime.fromisoformat(exif["parsedDatetime"])
                    if dt > now:
                        self._anomalies.append({
                            "filename": exif["filename"],
                            "type":     "future_date",
                            "detail":   f"DateTimeOriginal in future: {dt.date()}",
                        })
                        self._anomaly_count += 1
                except (ValueError, TypeError):
                    pass

            # Unusual ISO
            if exif.get("iso"):
                try:
                    if int(float(exif["iso"])) > 25600:
                        self._anomalies.append({
                            "filename": exif["filename"],
                            "type":     "unusual_iso",
                            "detail":   f"ISO {exif['iso']} (>25600)",
                        })
                        self._anomaly_count += 1
                except (ValueError, TypeError):
                    pass

            # ModifyDate > DateTimeOriginal
            if exif.get("modifyDate") and exif.get("datetimeOriginal"):
                try:
                    orig   = datetime.strptime(str(exif["datetimeOriginal"]), "%Y:%m:%d %H:%M:%S")
                    modify = datetime.strptime(str(exif["modifyDate"]),       "%Y:%m:%d %H:%M:%S")
                    if modify > orig and not exif.get("edited"):
                        self._anomalies.append({
                            "filename": exif["filename"],
                            "type":     "modify_after_original",
                            "detail":   f"ModifyDate {modify.date()} > DateTimeOriginal {orig.date()}",
                        })
                        self._anomaly_count += 1
                        exif["possiblyEdited"] = True
                except (ValueError, TypeError):
                    pass

        ptprint(f"✓ Edited photos:  {self._edited_count}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Anomalies:       {self._anomaly_count}",
                "WARNING" if self._anomaly_count else "INFO",
                condition=not self.args.json)

    def compute_quality_score(self) -> str:
        """
        Derive EXIF quality score based on percentage of files with DateTimeOriginal.

        Returns:
            Quality label: 'excellent', 'good', 'fair', or 'poor'
        """
        if self._total == 0:
            return "poor"
        pct = self._with_datetime / self._total * 100
        for label, threshold in QUALITY_THRESHOLDS.items():
            if pct >= threshold:
                return label
        return "poor"

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full six-phase EXIF analysis pipeline."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("EXIF METADATA ANALYSIS", "TITLE", condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        # Phase 1
        if not self.load_master_catalog():
            self.ptjsonlib.set_status("finished")
            return

        # Phase 2
        if not self.check_exiftool():
            self.ptjsonlib.set_status("finished")
            return

        # Phase 3
        if not self.extract_exif():
            ptprint("✗ No EXIF data extracted – aborting",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.set_status("finished")
            return

        # Phase 4
        self.run_analysis_phases()

        # Phase 5
        self.detect_edits_and_anomalies()
        quality_label = self.compute_quality_score()
        quality_pct   = round(self._with_datetime / max(self._total, 1) * 100, 1)

        # Build aggregates for JSON
        def _range_stats(vals: List[float]) -> Optional[Dict]:
            if not vals:
                return None
            return {
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "avg": round(sum(vals) / len(vals), 2),
            }

        date_range: Dict = {}
        if self._dates:
            date_range = {
                "earliest": min(self._dates).strftime("%Y-%m-%d %H:%M:%S"),
                "latest":   max(self._dates).strftime("%Y-%m-%d %H:%M:%S"),
                "spanDays": (max(self._dates) - min(self._dates)).days,
            }

        settings_range = {
            "iso":         _range_stats(self._iso_vals),
            "aperture":    _range_stats(self._aperture_vals),
            "focalLength": _range_stats(self._focal_vals),
        }

        self.ptjsonlib.add_properties({
            "filesWithExif":    self._with_exif,
            "filesWithoutExif": self._without_exif,
            "withDatetime":     self._with_datetime,
            "withGps":          self._with_gps,
            "editedPhotos":     self._edited_count,
            "anomalies":        self._anomaly_count,
            "uniqueCameras":    len(self._cameras),
            "dateRange":        date_range,
            "qualityScore":     quality_label,
            "qualityPct":       quality_pct,
            "settingsRange":    settings_range,
            "byCamera":         dict(self._cameras.most_common(10)),
        })

        # Summary node
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "analysisSummary",
            properties={
                "qualityScore":   quality_label,
                "qualityPct":     quality_pct,
                "uniqueCameras":  len(self._cameras),
                "withGps":        self._with_gps,
                "editedPhotos":   self._edited_count,
                "anomalies":      self._anomaly_count,
                "dateRange":      date_range,
            }
        ))

        # Console summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("EXIF ANALYSIS COMPLETED", "OK", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Total files:     {self._total}",
                "INFO", condition=not self.args.json)
        ptprint(f"  With EXIF:     {self._with_exif}",
                "OK",   condition=not self.args.json)
        ptprint(f"  With datetime: {self._with_datetime}",
                "OK",   condition=not self.args.json)
        ptprint(f"  With GPS:      {self._with_gps}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Edited:        {self._edited_count}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Anomalies:     {self._anomaly_count}",
                "WARNING" if self._anomaly_count else "INFO",
                condition=not self.args.json)
        ptprint(f"Quality score:   {quality_label.upper()} ({quality_pct}%)",
                "OK", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint("\nNext step: Step 15 (Integrity Validation / Final Report)",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    # -------------------------------------------------------------------------
    # PHASE 6 – SAVE REPORTS
    # -------------------------------------------------------------------------

    def save_report(self) -> Optional[str]:
        """
        Phase 6 – Persist all output artefacts.

        --json mode: prints ptlibs JSON to stdout only.
        Otherwise writes to {case_id}_exif_analysis/:
          - exif_database.json   (complete per-file EXIF + stats)
          - exif_data.csv        (spreadsheet-ready export)
          - EXIF_REPORT.txt      (human-readable summary)

        Returns:
            Path to exif_database.json, or None in --json mode
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        if not self.dry_run:
            self.analysis_dir.mkdir(parents=True, exist_ok=True)

        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]

        # ── JSON database ──────────────────────────────────────────────────
        json_file = self.analysis_dir / "exif_database.json"
        database  = {
            "caseId":      self.case_id,
            "timestamp":   props.get("timestamp"),
            "statistics":  props,
            "exifData":    self._exif_db,
            "timeline":    dict(self._timeline),
            "gpsLocations": self._gps_locations,
            "editedPhotos": self._edited,
            "anomalies":   self._anomalies,
        }
        if not self.dry_run:
            with open(json_file, "w", encoding="utf-8") as fh:
                json.dump(database, fh, indent=2, ensure_ascii=False, default=str)
        ptprint(f"✓ JSON database: {json_file.name}",
                "OK", condition=not self.args.json)

        # ── CSV export ─────────────────────────────────────────────────────
        csv_file = self.analysis_dir / "exif_data.csv"
        if self._exif_db and not self.dry_run:
            all_keys = sorted({k for rec in self._exif_db for k in rec})
            with open(csv_file, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=all_keys)
                writer.writeheader()
                writer.writerows(self._exif_db)
            ptprint(f"✓ CSV export:    {csv_file.name}",
                    "OK", condition=not self.args.json)

        # ── Text report ────────────────────────────────────────────────────
        txt_file = self.analysis_dir / "EXIF_REPORT.txt"
        if not self.dry_run:
            with open(txt_file, "w", encoding="utf-8") as fh:
                fh.write("=" * 70 + "\n")
                fh.write("EXIF METADATA ANALYSIS REPORT\n")
                fh.write("=" * 70 + "\n\n")
                fh.write(f"Case ID:   {self.case_id}\n")
                fh.write(f"Timestamp: {props.get('timestamp','')}\n\n")
                fh.write("SUMMARY:\n")
                fh.write(f"  Total files:          {props.get('totalFiles',0)}\n")
                fh.write(f"  Files with EXIF:      {props.get('filesWithExif',0)}\n")
                fh.write(f"  Files with datetime:  {props.get('withDatetime',0)}\n")
                fh.write(f"  Files with GPS:       {props.get('withGps',0)}\n")
                fh.write(f"  Edited photos:        {props.get('editedPhotos',0)}\n")
                fh.write(f"  Anomalies:            {props.get('anomalies',0)}\n\n")
                fh.write(f"QUALITY SCORE: {props.get('qualityScore','?').upper()}"
                         f"  ({props.get('qualityPct',0)}%)\n\n")
                dr = props.get("dateRange", {})
                if dr:
                    fh.write("DATE RANGE:\n")
                    fh.write(f"  Earliest: {dr.get('earliest','?')}\n")
                    fh.write(f"  Latest:   {dr.get('latest','?')}\n")
                    fh.write(f"  Span:     {dr.get('spanDays',0)} days\n\n")
                fh.write(f"UNIQUE CAMERAS: {props.get('uniqueCameras',0)}\n")
                for cam, cnt in list(props.get("byCamera", {}).items())[:10]:
                    pct = cnt / max(self._with_exif, 1) * 100
                    fh.write(f"  {cam}: {cnt} ({pct:.1f}%)\n")
                fh.write("\n")
                sr = props.get("settingsRange", {})
                if sr.get("iso"):
                    iso = sr["iso"]
                    fh.write(f"ISO:          {iso['min']} – {iso['max']}  (avg {iso['avg']})\n")
                if sr.get("aperture"):
                    ap = sr["aperture"]
                    fh.write(f"Aperture:     f/{ap['min']} – f/{ap['max']}  (avg f/{ap['avg']})\n")
                if sr.get("focalLength"):
                    fl = sr["focalLength"]
                    fh.write(f"Focal length: {fl['min']} – {fl['max']} mm  (avg {fl['avg']} mm)\n")
                fh.write("\n")
                if self._timeline:
                    fh.write("TIMELINE (first 20 days):\n")
                    for day in sorted(self._timeline)[:20]:
                        fh.write(f"  {day}: {len(self._timeline[day])} photos\n")
                    fh.write("\n")
                if self._gps_locations:
                    fh.write(f"GPS LOCATIONS ({len(self._gps_locations)} photos):\n")
                    for loc in self._gps_locations[:10]:
                        fh.write(f"  {loc['filename']}: "
                                 f"{loc['latitude']:.6f}, {loc['longitude']:.6f}\n")
                    fh.write("\n")
                if self._anomalies:
                    fh.write(f"ANOMALIES ({len(self._anomalies)}):\n")
                    for an in self._anomalies[:20]:
                        fh.write(f"  [{an['type']}] {an['filename']}: {an['detail']}\n")
            ptprint(f"✓ Text report:   {txt_file.name}",
                    "OK", condition=not self.args.json)

        return str(json_file)


# ============================================================================
# CLI HELPERS
# ============================================================================

def get_help():
    return [
        {"description": [
            "Forensic EXIF metadata analysis tool – ptlibs compliant",
            "Extracts and analyses EXIF data from all consolidated recovered photos",
            "Builds timeline, identifies cameras, detects edits and anomalies",
        ]},
        {"usage": ["ptexifanalysis <case-id> [options]"]},
        {"usage_example": [
            "ptexifanalysis PHOTO-2025-001",
            "ptexifanalysis CASE-042 --json",
            "ptexifanalysis TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",    "",              "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<dir>",  f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",              "Simulate without running exiftool"],
            ["-j",  "--json",       "",      "JSON output for platform integration"],
            ["-q",  "--quiet",      "",      "Suppress progress output"],
            ["-h",  "--help",       "",      "Show this help and exit"],
            ["--version",  "",              "Show version and exit"],
        ]},
        {"analysis_phases": [
            "Phase 1: Load master_catalog.json from Step 13",
            "Phase 2: Verify ExifTool installation",
            "Phase 3: Batch-extract EXIF (exiftool -j -G -a -s -n)",
            "Phase 4: Analyse time / cameras / settings / GPS",
            "Phase 5: Detect edited photos and anomalies; quality score",
            "Phase 6: Save exif_database.json + exif_data.csv + EXIF_REPORT.txt",
        ]},
        {"quality_score": [
            "excellent  >90 % DateTimeOriginal  – full timeline possible",
            "good       70–90 %                 – partial timeline",
            "fair       50–70 %                 – limited analysis",
            "poor       <50 %                   – heavy metadata loss",
        ]},
        {"forensic_notes": [
            "READ-ONLY on source files",
            "Requires Step 13 (Consolidation) to have been run first",
            "EXIF 2.32 / CIPA DC-008-2019 / ISO 12234-2:2001 compliant",
        ]},
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Forensic EXIF metadata analysis"
    )
    parser.add_argument("case_id",        help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("-j", "--json",   action="store_true")
    parser.add_argument("-q", "--quiet",  action="store_true")
    parser.add_argument("--version",      action="version",
                        version=f"{SCRIPTNAME} {__version__}")
    parser.add_argument("--socket-address", type=str, default=None)
    parser.add_argument("--socket-port",    type=str, default=None)
    parser.add_argument("--process-ident",  type=str, default=None)

    if len(sys.argv) == 1 or "-h" in sys.argv or "--help" in sys.argv:
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    if args.json:
        args.quiet = True
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main():
    global SCRIPTNAME
    SCRIPTNAME = "ptexifanalysis"
    try:
        args = parse_args()
        tool = PtExifAnalysis(args)
        tool.run()
        tool.save_report()

        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("filesWithExif", 0) > 0 else 1

    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())
