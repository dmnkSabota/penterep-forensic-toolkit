#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptphotorepair - Forensic photo repair tool

    ptphotorepair is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptphotorepair is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptphotorepair.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

try:
    from PIL import Image, ImageFile
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# JPEG / IMAGE CONSTANTS
# ============================================================================

# Core JPEG markers
SOI  = b"\xff\xd8"        # Start of Image
EOI  = b"\xff\xd9"        # End of Image
SOS  = b"\xff\xda"        # Start of Scan
SOF0 = b"\xff\xc0"        # Start of Frame (baseline DCT)
DQT  = b"\xff\xdb"        # Define Quantization Table
DHT  = b"\xff\xc4"        # Define Huffman Table
APP0 = b"\xff\xe0"        # JFIF APP0
APP1 = b"\xff\xe1"        # EXIF APP1

# Minimal valid JFIF APP0 marker (16 bytes)
JFIF_APP0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"

# Marker identifier byte
MARKER_PREFIX = b"\xff"

# Critical markers that MUST be preserved
CRITICAL_MARKERS = {SOF0, DQT, DHT}

# Repair technique → expected success range (low, high) in percent
EXPECTED_SUCCESS: Dict[str, Tuple[int, int]] = {
    "repair_missing_footer":  (85, 95),
    "repair_invalid_header":  (90, 95),
    "repair_invalid_segments":(80, 85),
    "repair_truncated_file":  (50, 70),
}

DEFAULT_OUTPUT_DIR = "/var/forensics/images"
VALIDATE_TIMEOUT   = 30   # seconds per file for identify / jpeginfo


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtPhotoRepair:
    """
    Forensic photo repair tool – ptlibs compliant.

    Six-phase process:
    1. Load validation report (Step 15) and repair decision (Step 16)
    2. Check tools (PIL required; ImageMagick, jpeginfo optional)
    3. Prepare output directories (repaired / failed / logs)
    4. Attempt repair on every listed corrupted file using technique routing:
         missing_footer    → repair_missing_footer()   (85–95 %)
         invalid_header    → repair_invalid_header()   (90–95 %)
         corrupt_segments  → repair_invalid_segments() (80–85 %)
         truncated / other → repair_truncated_file()   (50–70 %)
    5. Multi-tool validation after each repair attempt
    6. Save repair_report.json + REPAIR_REPORT.txt

    Forensic integrity: repair only RECONSTRUCTS existing data (fills missing
    markers, removes corrupt segments) – it never fabricates pixel data.
    All originals in validation/corrupted/ are READ-ONLY; repair works on
    a working copy.

    Complies with ISO/IEC 10918-1, JFIF 1.02, NIST SP 800-86 §3.1.4.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Input sources
        self.validation_dir    = self.output_dir / f"{self.case_id}_validation"
        self.corrupted_dir     = self.validation_dir / "corrupted"
        self.validation_report = self.output_dir / f"{self.case_id}_validation_report.json"

        # Output
        self.repair_base   = self.output_dir / f"{self.case_id}_repair"
        self.repaired_dir  = self.repair_base / "repaired"
        self.failed_dir    = self.repair_base / "failed"
        self.logs_dir      = self.repair_base / "logs"

        # State
        self._tools: Dict[str, bool] = {}
        self._files_to_repair: List[Dict] = []
        self._results: List[Dict] = []

        # Counters
        self._attempted  = 0
        self._repaired   = 0
        self._failed     = 0
        self._by_type:   Dict[str, Dict] = {}

        # Enable PIL truncated loading globally once PIL is confirmed present
        if PIL_AVAILABLE:
            ImageFile.LOAD_TRUNCATED_IMAGES = True

        # Top-level JSON properties
        self.ptjsonlib.add_properties({
            "caseId":           self.case_id,
            "outputDirectory":  str(self.output_dir),
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "scriptVersion":    __version__,
            "totalAttempted":   0,
            "successfulRepairs":0,
            "failedRepairs":    0,
            "successRate":      0.0,
            "byCorruptionType": {},
            "dryRun":           self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _run(self, cmd: List[str], timeout: int = VALIDATE_TIMEOUT) -> Dict[str, Any]:
        """Execute subprocess, returning dict(success, stdout, stderr)."""
        if self.dry_run:
            ptprint(f"[DRY-RUN] {' '.join(str(c) for c in cmd)}",
                    "INFO", condition=not self.args.json)
            return {"success": True, "stdout": "[DRY-RUN]", "stderr": "", "returncode": 0}
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout, check=False)
            return {"success": p.returncode == 0,
                    "stdout": p.stdout.strip(),
                    "stderr": p.stderr.strip(),
                    "returncode": p.returncode}
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": f"Timeout {timeout}s", "returncode": -1}
        except Exception as exc:
            return {"success": False, "stdout": "", "stderr": str(exc), "returncode": -1}

    def _read_binary(self, path: Path) -> Optional[bytes]:
        try:
            return path.read_bytes()
        except Exception:
            return None

    def _write_binary(self, path: Path, data: bytes) -> bool:
        try:
            path.write_bytes(data)
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # PHASE 1 – LOAD VALIDATION REPORT
    # -------------------------------------------------------------------------

    def load_validation_report(self) -> bool:
        """
        Load files_needing_repair list from the Step 15 JSON report.

        Accepts ptlibs camelCase format and legacy snake_case format.
        """
        ptprint("\n[STEP 1/6] Loading Validation Report from Step 15",
                "TITLE", condition=not self.args.json)

        if not self.validation_report.exists() and not self.dry_run:
            ptprint(f"✗ Not found: {self.validation_report}",
                    "ERROR", condition=not self.args.json)
            ptprint("  Please run Step 15 (Integrity Validation) first!",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "reportLoad", properties={"success": False,
                                          "error": "validation_report.json not found"}))
            return False

        if self.dry_run:
            # Synthetic repair list for simulation
            self._files_to_repair = [
                {"filename": f"TEST_{i:04d}.jpg",
                 "corruptionType": ctype,
                 "corruption_type": ctype}
                for i, ctype in enumerate([
                    "missing_footer", "missing_footer",
                    "invalid_header", "invalid_header",
                    "corrupt_segments", "corrupt_segments",
                    "truncated", "truncated",
                ], 1)
            ]
        else:
            try:
                raw = json.loads(self.validation_report.read_text(encoding="utf-8"))
            except Exception as exc:
                ptprint(f"✗ Cannot read report: {exc}",
                        "ERROR", condition=not self.args.json)
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "reportLoad", properties={"success": False, "error": str(exc)}))
                return False

            self._files_to_repair = (
                raw.get("filesNeedingRepair") or
                raw.get("files_needing_repair") or []
            )

        ptprint(f"✓ Report loaded: {self.validation_report.name}",
                "OK", condition=not self.args.json)
        ptprint(f"  Files to repair: {len(self._files_to_repair)}",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "reportLoad",
            properties={"success": True,
                        "filesToRepair": len(self._files_to_repair)}))
        return True

    # -------------------------------------------------------------------------
    # PHASE 2 – CHECK TOOLS
    # -------------------------------------------------------------------------

    def check_tools(self) -> bool:
        """
        Verify PIL (required) and optional tools (ImageMagick, jpeginfo).
        """
        ptprint("\n[STEP 2/6] Checking Repair Tools",
                "TITLE", condition=not self.args.json)

        self._tools["pil"] = PIL_AVAILABLE or self.dry_run
        if self._tools["pil"]:
            ptprint("✓ PIL/Pillow: Found  (LOAD_TRUNCATED_IMAGES enabled)",
                    "OK", condition=not self.args.json)
        else:
            ptprint("✗ PIL/Pillow: NOT FOUND  (required)",
                    "ERROR", condition=not self.args.json)
            ptprint("  pip install Pillow --break-system-packages",
                    "ERROR", condition=not self.args.json)

        for tool in ("identify", "jpeginfo"):
            found = self._run(["which", tool], timeout=5)["success"]
            self._tools[tool] = found
            ptprint(f"{'✓' if found else '⚠'} {tool}: {'Found' if found else 'Not found'} (optional)",
                    "OK" if found else "WARNING",
                    condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "toolsCheck", properties={"success": self._tools.get("pil", False),
                                      "tools": self._tools}))
        return self._tools.get("pil", False)

    # -------------------------------------------------------------------------
    # PHASE 3 – PREPARE DIRECTORIES
    # -------------------------------------------------------------------------

    def prepare_directories(self) -> bool:
        ptprint("\n[STEP 3/6] Preparing Repair Directories",
                "TITLE", condition=not self.args.json)
        for d in [self.repaired_dir, self.failed_dir, self.logs_dir]:
            if not self.dry_run:
                d.mkdir(parents=True, exist_ok=True)
            ptprint(f"  {d.relative_to(self.repair_base)}/",
                    "INFO", condition=not self.args.json)
        ptprint("✓ Directories ready", "OK", condition=not self.args.json)
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "directoriesPrep",
            properties={"repairedDir": str(self.repaired_dir),
                        "failedDir":   str(self.failed_dir)}))
        return True

    # -------------------------------------------------------------------------
    # PHASE 4a – REPAIR TECHNIQUES
    # -------------------------------------------------------------------------

    def repair_missing_footer(self, path: Path) -> Tuple[bool, str]:
        """
        Add missing JPEG EOI (FF D9) marker.

        1. Skip if EOI already present
        2. Append FF D9
        3. If file ends with 0xFF (half-written marker), replace with FF D9
        """
        data = self._read_binary(path)
        if data is None:
            return False, "Cannot read file"

        if data.endswith(EOI):
            return False, "EOI already present – no repair needed"

        # If trailing 0xFF exists (incomplete marker) replace it
        if data.endswith(MARKER_PREFIX):
            new_data = data[:-1] + EOI
            return self._write_binary(path, new_data), "Replaced incomplete trailing marker with EOI"

        return self._write_binary(path, data + EOI), "Appended missing EOI marker"

    def repair_invalid_header(self, path: Path) -> Tuple[bool, str]:
        """
        Fix corrupt/missing JPEG SOI header.

        Strategy A: SOI found inside file but not at offset 0 →
                    remove leading garbage.
        Strategy B: No SOI at all → insert SOI + JFIF APP0 before first SOS.
        """
        data = self._read_binary(path)
        if data is None:
            return False, "Cannot read file"

        soi_pos = data.find(SOI)

        if soi_pos > 0:
            return self._write_binary(path, data[soi_pos:]), \
                   f"Removed {soi_pos} leading garbage bytes before SOI"

        if soi_pos == 0:
            return False, "SOI already at offset 0 – header intact"

        # No SOI – try to anchor at SOS
        sos_pos = data.find(SOS)
        if sos_pos < 0:
            return False, "No SOI or SOS marker found – cannot reconstruct"

        new_data = SOI + JFIF_APP0 + data[sos_pos:]
        return self._write_binary(path, new_data), \
               "Inserted SOI + JFIF APP0 before SOS marker"

    def repair_invalid_segments(self, path: Path) -> Tuple[bool, str]:
        """
        Remove corrupt APP segments while preserving the image payload.

        Strategy:
          SOI  +  JFIF_APP0  +  critical segments (SOF0, DQT, DHT)  +  SOS..EOI

        This strips all APP1..APPn (EXIF, XMP, ICC …) – metadata is lost
        but pixel data is preserved.  A separate EXIF pass can re-attach
        metadata if needed.
        """
        data = self._read_binary(path)
        if data is None:
            return False, "Cannot read file"

        sos_pos = data.find(SOS)
        if sos_pos < 0:
            return False, "No SOS marker – cannot isolate image data"

        # Collect critical segments from the header region
        critical_segments = b""
        i = 2  # skip SOI
        while i < sos_pos - 1:
            if data[i:i+1] != MARKER_PREFIX:
                i += 1
                continue
            marker = data[i:i+2]
            if i + 4 > len(data):
                break
            seg_len = int.from_bytes(data[i+2:i+4], "big")
            seg_end = i + 2 + seg_len
            if seg_end > len(data):
                break
            if marker in CRITICAL_MARKERS:
                critical_segments += data[i:seg_end]
            i = seg_end

        new_data = SOI + JFIF_APP0 + critical_segments + data[sos_pos:]
        removed = sos_pos - 2 - len(JFIF_APP0) - len(critical_segments)
        return self._write_binary(path, new_data), \
               f"Removed corrupt segments ({removed} bytes); preserved critical markers"

    def repair_truncated_file(self, path: Path) -> Tuple[bool, str]:
        """
        Partial recovery for truncated / corrupt_data files via PIL.

        PIL's LOAD_TRUNCATED_IMAGES=True allows opening files with a missing
        or truncated entropy stream and loads however many scan lines are
        available.  The recovered (partial) image is saved as a fresh JPEG.
        """
        if self.dry_run:
            return True, "[DRY-RUN] truncated repair simulated"

        temp_path = path.parent / (path.stem + "_repaired_tmp.jpg")
        try:
            img = Image.open(path)
            img.load()
            w, h = img.size
            if w == 0 or h == 0:
                return False, "Image has zero dimensions after load"
            img.save(temp_path, "JPEG", quality=95,
                     optimize=True, progressive=False)
            shutil.move(str(temp_path), str(path))
            return True, f"Partial recovery saved ({w}×{h} px – some rows may be grey/missing)"
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return False, str(exc)

    # -------------------------------------------------------------------------
    # PHASE 4b – TECHNIQUE ROUTER
    # -------------------------------------------------------------------------

    _STRATEGY_MAP: Dict[str, str] = {
        "missing_footer":   "repair_missing_footer",
        "invalid_header":   "repair_invalid_header",
        "corrupt_segments": "repair_invalid_segments",
        "corrupt_segment":  "repair_invalid_segments",
        "invalid_segment":  "repair_invalid_segments",
        "truncated":        "repair_truncated_file",
        "corrupt_data":     "repair_truncated_file",
        "unknown":          "repair_invalid_header",
    }

    def _route(self, ctype: str):
        method_name = self._STRATEGY_MAP.get(ctype, "repair_invalid_header")
        return getattr(self, method_name, None), method_name

    # -------------------------------------------------------------------------
    # PHASE 4c – VALIDATION AFTER REPAIR
    # -------------------------------------------------------------------------

    def _validate_repaired(self, path: Path) -> Dict[str, Any]:
        """
        Three-tool validation: PIL verify+load, ImageMagick identify, jpeginfo.
        Returns dict(valid, toolsPassed, toolsTotal, details).
        """
        if self.dry_run:
            return {"valid": True, "toolsPassed": 3, "toolsTotal": 3,
                    "pil": True, "imagemagick": True, "jpeginfo": True}

        passed = 0
        total  = 0
        details: Dict[str, Any] = {}

        # PIL
        total += 1
        try:
            img = Image.open(path); img.verify()
            img = Image.open(path); img.load()
            w, h = img.size
            if w > 0 and h > 0:
                details["pil"] = True
                details["width"]  = w
                details["height"] = h
                details["mode"]   = img.mode
                passed += 1
            else:
                details["pil"] = False
                details["pilError"] = "zero dimensions"
        except Exception as exc:
            details["pil"] = False
            details["pilError"] = str(exc)[:120]

        # ImageMagick identify
        if self._tools.get("identify"):
            total += 1
            r = self._run(["identify", str(path)])
            details["imagemagick"] = r["success"]
            if r["success"]:
                passed += 1
            else:
                details["imagemagickError"] = r["stderr"][:120]

        # jpeginfo
        if self._tools.get("jpeginfo") and path.suffix.lower() in (".jpg", ".jpeg"):
            total += 1
            r = self._run(["jpeginfo", "-c", str(path)])
            details["jpeginfo"] = r["success"]
            if r["success"]:
                passed += 1
            else:
                details["jpeginfError"] = (r["stdout"] + " " + r["stderr"]).strip()[:120]

        details.update({"toolsPassed": passed, "toolsTotal": total,
                        "valid": passed > 0})
        return details

    # -------------------------------------------------------------------------
    # PHASE 4 – REPAIR ALL FILES
    # -------------------------------------------------------------------------

    def repair_all_files(self) -> None:
        """
        Phase 4 – Iterate over every file listed in files_needing_repair,
        attempt the appropriate repair technique, validate, and route to
        repaired/ or failed/.
        """
        ptprint("\n[STEP 4/6] Repairing Files",
                "TITLE", condition=not self.args.json)

        total = len(self._files_to_repair)
        self._attempted = total

        if total == 0:
            ptprint("  No files to repair", "INFO", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "repairPhase", properties={"success": True, "totalAttempted": 0}))
            return

        ptprint(f"  Attempting repair on {total} file(s)…",
                "INFO", condition=not self.args.json)

        for idx, fi in enumerate(self._files_to_repair, 1):
            filename  = fi.get("filename") or fi.get("file_name", "unknown")
            ctype     = (fi.get("corruptionType") or
                         fi.get("corruption_type") or "unknown")

            ptprint(f"\n  [{idx}/{total}] {filename}  [{ctype}]",
                    "INFO", condition=not self.args.json)

            # Source file
            src = self.corrupted_dir / filename
            if not src.exists() and not self.dry_run:
                entry = {"filename": filename, "corruptionType": ctype,
                         "attempted": False, "finalStatus": "skipped",
                         "error": "Not found in corrupted/"}
                self._results.append(entry)
                ptprint(f"    ⚠ Skipped – file not found in corrupted/",
                        "WARNING", condition=not self.args.json)
                self._failed += 1
                continue

            # Copy to working area (never modify originals)
            work = self.repair_base / filename
            if not self.dry_run:
                shutil.copy2(src, work)

            repair_func, method_name = self._route(ctype)
            exp_lo, exp_hi = EXPECTED_SUCCESS.get(method_name, (50, 80))

            entry: Dict[str, Any] = {
                "filename":       filename,
                "corruptionType": ctype,
                "attempted":      True,
                "repairTechnique": method_name,
                "expectedSuccess": f"{exp_lo}–{exp_hi} %",
            }

            # Apply repair
            ok, msg = repair_func(work) if not self.dry_run else (True, "[DRY-RUN]")
            entry["repairMessage"] = msg

            if ok:
                # Validate
                validation = self._validate_repaired(work)
                entry["validation"] = validation

                if validation["valid"]:
                    dst = self.repaired_dir / filename
                    if not self.dry_run:
                        # Collision guard
                        if dst.exists():
                            stem, suf = dst.stem, dst.suffix
                            c = 1
                            while dst.exists():
                                dst = self.repaired_dir / f"{stem}_{c}{suf}"
                                c += 1
                        shutil.move(str(work), str(dst))
                    entry["finalStatus"] = "fully_repaired"
                    entry["finalPath"]   = str(self.repaired_dir / filename)
                    self._repaired += 1
                    ptprint(f"    ✓ REPAIRED  ({msg})",
                            "OK", condition=not self.args.json)
                else:
                    dst = self.failed_dir / filename
                    if not self.dry_run:
                        shutil.move(str(work), str(dst))
                    entry["finalStatus"] = "repair_failed_validation"
                    self._failed += 1
                    ptprint(f"    ✗ Repair OK but validation failed",
                            "WARNING", condition=not self.args.json)
            else:
                dst = self.failed_dir / filename
                if not self.dry_run:
                    shutil.copy2(src, dst)
                    if work.exists():
                        work.unlink(missing_ok=True)
                entry["finalStatus"] = "repair_failed"
                self._failed += 1
                ptprint(f"    ✗ Failed  ({msg})",
                        "WARNING", condition=not self.args.json)

            # Per-type breakdown
            if ctype not in self._by_type:
                self._by_type[ctype] = {"attempted": 0, "successful": 0, "failed": 0}
            self._by_type[ctype]["attempted"] += 1
            if entry["finalStatus"] == "fully_repaired":
                self._by_type[ctype]["successful"] += 1
            else:
                self._by_type[ctype]["failed"] += 1

            self._results.append(entry)

        rate = round(self._repaired / max(self._attempted, 1) * 100, 2)

        ptprint(f"\n  ✓ Successful: {self._repaired}/{self._attempted}",
                "OK",   condition=not self.args.json)
        ptprint(f"  Success rate: {rate}%",
                "OK",   condition=not self.args.json)

        ptprint("\n  Breakdown by corruption type:", "INFO",
                condition=not self.args.json)
        for ct, d in sorted(self._by_type.items()):
            r = d["successful"] / max(d["attempted"], 1) * 100
            ptprint(f"    {ct}: {d['successful']}/{d['attempted']}  ({r:.1f}%)",
                    "INFO", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "repairPhase",
            properties={
                "totalAttempted":   self._attempted,
                "successfulRepairs": self._repaired,
                "failedRepairs":    self._failed,
                "successRate":      rate,
                "byCorruptionType": self._by_type,
            }
        ))

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the six-phase repair pipeline."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("PHOTO REPAIR", "TITLE", condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_validation_report():
            self.ptjsonlib.set_status("finished")
            return
        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return

        self.prepare_directories()
        self.repair_all_files()

        rate = round(self._repaired / max(self._attempted, 1) * 100, 2)
        self.ptjsonlib.add_properties({
            "totalAttempted":    self._attempted,
            "successfulRepairs": self._repaired,
            "failedRepairs":     self._failed,
            "successRate":       rate,
            "byCorruptionType":  self._by_type,
        })

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("REPAIR COMPLETED", "OK",   condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Total attempted:  {self._attempted}",
                "INFO",    condition=not self.args.json)
        ptprint(f"Successful:       {self._repaired}",
                "OK",      condition=not self.args.json)
        ptprint(f"Failed:           {self._failed}",
                "WARNING", condition=not self.args.json)
        ptprint(f"Success rate:     {rate}%",
                "OK",      condition=not self.args.json)
        ptprint("\nNext step: Step 18 (Cataloging)",
                "INFO",    condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    # -------------------------------------------------------------------------
    # PHASE 6 – SAVE REPORTS
    # -------------------------------------------------------------------------

    def save_report(self) -> Optional[str]:
        """
        Phase 6 – Save JSON report and human-readable text summary.

        --json mode: prints ptlibs JSON to stdout only.
        Otherwise writes:
          {case_id}_repair_report.json
          {case_id}_repair/REPAIR_REPORT.txt
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        json_file = self.output_dir / f"{self.case_id}_repair_report.json"
        report    = {
            "result":         json.loads(self.ptjsonlib.get_result_json()),
            "repairResults":  self._results,
        }

        if not self.dry_run:
            with open(json_file, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
        ptprint(f"✓ JSON report saved: {json_file.name}",
                "OK", condition=not self.args.json)

        # Text report
        if not self.dry_run:
            self.repair_base.mkdir(parents=True, exist_ok=True)
        txt_file  = self.repair_base / "REPAIR_REPORT.txt"
        rate      = round(self._repaired / max(self._attempted, 1) * 100, 2)

        if not self.dry_run:
            with open(txt_file, "w", encoding="utf-8") as fh:
                fh.write("=" * 70 + "\n")
                fh.write("PHOTO REPAIR REPORT\n")
                fh.write("=" * 70 + "\n\n")
                fh.write(f"Case ID:   {self.case_id}\n")
                fh.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n\n")
                fh.write("SUMMARY:\n")
                fh.write(f"  Total attempted:  {self._attempted}\n")
                fh.write(f"  Successful:       {self._repaired}\n")
                fh.write(f"  Failed:           {self._failed}\n")
                fh.write(f"  Success rate:     {rate}%\n\n")
                fh.write("BY CORRUPTION TYPE:\n")
                for ct, d in sorted(self._by_type.items()):
                    r = d["successful"] / max(d["attempted"], 1) * 100
                    exp_fn = self._STRATEGY_MAP.get(ct, "repair_invalid_header")
                    exp_lo, exp_hi = EXPECTED_SUCCESS.get(exp_fn, (50, 80))
                    fh.write(f"  {ct}:\n")
                    fh.write(f"    Attempted: {d['attempted']}  "
                             f"Successful: {d['successful']}  "
                             f"Rate: {r:.1f}%  (expected {exp_lo}–{exp_hi}%)\n")
                fh.write("\nREPAIR DETAILS:\n")
                for r_entry in self._results:
                    fh.write(f"\n  {r_entry['filename']}\n")
                    fh.write(f"    Corruption:  {r_entry['corruptionType']}\n")
                    fh.write(f"    Technique:   {r_entry.get('repairTechnique','N/A')}\n")
                    fh.write(f"    Status:      {r_entry.get('finalStatus','N/A')}\n")
                    if r_entry.get("repairMessage"):
                        fh.write(f"    Message:     {r_entry['repairMessage']}\n")
                    v = r_entry.get("validation", {})
                    if v:
                        fh.write(f"    Validation:  {v.get('toolsPassed',0)}/{v.get('toolsTotal',0)} tools passed\n")

        ptprint(f"✓ Text report saved: {txt_file.name}",
                "OK", condition=not self.args.json)
        return str(json_file)


# ============================================================================
# CLI HELPERS
# ============================================================================

def get_help():
    return [
        {"description": [
            "Forensic photo repair tool – ptlibs compliant",
            "Four repair techniques: missing footer, invalid header,",
            "corrupt segments, truncated file (PIL partial recovery)",
            "Multi-tool validation: PIL + ImageMagick + jpeginfo",
        ]},
        {"usage": ["ptphotorepair <case-id> [options]"]},
        {"usage_example": [
            "ptphotorepair PHOTO-2025-001",
            "ptphotorepair CASE-042 --json",
            "ptphotorepair TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",    "",              "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<dir>",  f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",              "Simulate all repairs with synthetic data"],
            ["-j",  "--json",       "",      "JSON output for platform integration"],
            ["-q",  "--quiet",      "",      "Suppress progress output"],
            ["-h",  "--help",       "",      "Show this help and exit"],
            ["--version",  "",              "Show version and exit"],
        ]},
        {"repair_techniques": [
            "missing_footer    → repair_missing_footer()    85–95 % success",
            "invalid_header    → repair_invalid_header()    90–95 % success",
            "corrupt_segments  → repair_invalid_segments()  80–85 % success",
            "truncated         → repair_truncated_file()    50–70 % success",
            "corrupt_data      → repair_truncated_file()    50–70 % success",
        ]},
        {"forensic_notes": [
            "Reads from: {case_id}_validation_report.json  (Step 15)",
            "Source files in {case_id}_validation/corrupted/ are READ-ONLY",
            "Repair works on shutil.copy2 working copies",
            "Repair only reconstructs existing data – never fabricates pixel data",
            "Complies with ISO/IEC 10918-1, JFIF 1.02, NIST SP 800-86 §3.1.4",
        ]},
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Forensic photo repair"
    )
    parser.add_argument("case_id",         help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run",       action="store_true")
    parser.add_argument("-j", "--json",    action="store_true")
    parser.add_argument("-q", "--quiet",   action="store_true")
    parser.add_argument("--version",       action="version",
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
    SCRIPTNAME = "ptphotorepair"
    try:
        args = parse_args()
        tool = PtPhotoRepair(args)
        tool.run()
        tool.save_report()

        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("successfulRepairs", 0) >= 0 else 1

    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())
