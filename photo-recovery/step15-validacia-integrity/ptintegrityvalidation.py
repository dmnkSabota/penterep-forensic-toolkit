#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptintegrityvalidation - Forensic photo integrity validation tool

    ptintegrityvalidation is free software: you can redistribute it and/or
    modify it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptintegrityvalidation is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptintegrityvalidation.
    If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

try:
    from PIL import Image, UnidentifiedImageError
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/images"
VALIDATE_TIMEOUT   = 30    # seconds per file for identify / jpeginfo / pngcheck
FILE_TIMEOUT       = 10    # seconds for `file` command

# JPEG / PNG / GIF / TIFF / BMP / WEBP magic bytes
# Key = upper-case format group, value = list of byte prefixes
MAGIC_BYTES: Dict[str, List[bytes]] = {
    "JPEG": [b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1",
             b"\xff\xd8\xff\xe2", b"\xff\xd8\xff\xe8", b"\xff\xd8\xff"],
    "PNG":  [b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"],
    "GIF":  [b"GIF87a", b"GIF89a"],
    "TIFF": [b"\x49\x49\x2a\x00", b"\x4d\x4d\x00\x2a"],
    "BMP":  [b"BM"],
    "WEBP": [b"RIFF"],
}

# Map extension → MAGIC_BYTES key
EXT_TO_MAGIC: Dict[str, str] = {
    "jpg": "JPEG", "jpeg": "JPEG",
    "png": "PNG",
    "gif": "GIF",
    "tif": "TIFF", "tiff": "TIFF",
    "bmp": "BMP",
    "webp": "WEBP",
}

# Corruption taxonomy
# level 1 = easiest to repair, 5 = impossible
CORRUPTION_TYPES: Dict[str, Dict] = {
    "truncated":        {"level": 1, "repairable": True,      "technique": "Add missing footer bytes"},
    "invalid_header":   {"level": 2, "repairable": True,      "technique": "Fix/rebuild file header"},
    "corrupt_segments": {"level": 2, "repairable": True,      "technique": "Remove/skip corrupt segments"},
    "corrupt_data":     {"level": 3, "repairable": "partial", "technique": "Partial pixel recovery possible"},
    "fragmented":       {"level": 4, "repairable": False,     "technique": "Manual defragmentation needed"},
    "false_positive":   {"level": 5, "repairable": False,     "technique": "Not an image – discard"},
    "unknown":          {"level": 3, "repairable": "unknown", "technique": "Manual inspection needed"},
}

# Expected integrity scores (documentation reference)
EXPECTED_INTEGRITY = {
    "fs_based":  ">95 %",
    "carved":    "70–85 %",
}


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtIntegrityValidation:
    """
    Forensic photo integrity validation tool – ptlibs compliant.

    Six-phase process:
    1. Load master catalog from Step 13
    2. Check validation tools (ImageMagick, PIL, file, jpeginfo, pngcheck)
    3. Prepare output directory structure
    4. Validate every file with a multi-tool approach:
         magic bytes → file command → ImageMagick identify → PIL verify+load
         → format-specific (jpeginfo / pngcheck)
    5. Assess repairability, classify corruption type and level
    6. Organise into valid / corrupted / unrecoverable; save reports

    Decision logic:
      ALL tools pass  + valid magic  → valid
      ≥1 tool passes               → corrupted (repairable analysis follows)
      ALL tools fail               → unrecoverable

    Complies with ISO/IEC 10918-1, PNG ISO/IEC 15948:2004, NIST SP 800-86.
    READ-ONLY on source files – shutil.copy2 only, no destructive operations.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Paths
        self.consolidated_dir  = self.output_dir / f"{self.case_id}_consolidated"
        self.validation_base   = self.output_dir / f"{self.case_id}_validation"
        self.valid_dir         = self.validation_base / "valid"
        self.corrupted_dir     = self.validation_base / "corrupted"
        self.unrecoverable_dir = self.validation_base / "unrecoverable"

        # Catalog
        self.catalog: Optional[Dict] = None

        # Tool availability (filled in Phase 2)
        self._tools: Dict[str, bool] = {}

        # Results
        self._results:      List[Dict] = []
        self._need_repair:  List[Dict] = []

        # Counters
        self._total          = 0
        self._valid          = 0
        self._corrupted      = 0
        self._unrecoverable  = 0
        self._by_format:     Dict[str, Dict] = {}
        self._by_source:     Dict[str, Dict] = {}
        self._corruption_types: Dict[str, int] = {}

        # Top-level JSON properties
        self.ptjsonlib.add_properties({
            "caseId":             self.case_id,
            "outputDirectory":    str(self.output_dir),
            "timestamp":          datetime.now(timezone.utc).isoformat(),
            "scriptVersion":      __version__,
            "totalFiles":         0,
            "validFiles":         0,
            "corruptedFiles":     0,
            "unrecoverableFiles": 0,
            "integrityScore":     0.0,
            "filesNeedingRepair": 0,
            "byFormat":           {},
            "bySource":           {},
            "corruptionTypes":    {},
            "dryRun":             self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------------------

    def _run_command(self, cmd: List[str], timeout: int = 30) -> Dict[str, Any]:
        """Execute a subprocess."""
        result = {"success": False, "stdout": "", "stderr": "", "returncode": -1}
        if self.dry_run:
            ptprint(f"[DRY-RUN] {' '.join(str(c) for c in cmd)}",
                    "INFO", condition=not self.args.json)
            result["success"] = True
            result["stdout"]  = "[DRY-RUN]"
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

    def _tool_present(self, name: str) -> bool:
        res = self._run_command(["which", name], timeout=5)
        return res["success"]

    def _file_path(self, relative: str) -> Path:
        return self.consolidated_dir / relative

    # -------------------------------------------------------------------------
    # PHASE 1 – LOAD MASTER CATALOG
    # -------------------------------------------------------------------------

    def load_master_catalog(self) -> bool:
        """
        Load master_catalog.json from Step 13.

        Accepts both camelCase (ptlibs output) and snake_case (legacy) keys.

        Returns:
            bool: True if loaded successfully
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
            with open(cat_file, "r", encoding="utf-8") as fh:
                self.catalog = json.load(fh)
        except Exception as exc:
            ptprint(f"✗ Cannot read catalog: {exc}",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "catalogLoad",
                properties={"success": False, "error": str(exc)}
            ))
            return False

        summary = self.catalog.get("summary", {})
        # Support both camelCase and snake_case
        self._total = (summary.get("totalFiles") or
                       summary.get("total_files") or
                       len(self.catalog.get("files", [])))

        ptprint(f"✓ Catalog loaded: {cat_file.name}",
                "OK", condition=not self.args.json)
        ptprint(f"  Files to validate: {self._total}",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_properties({"totalFiles": self._total})
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "catalogLoad",
            properties={"success": True, "totalFiles": self._total,
                        "sourceFile": str(cat_file)}
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 2 – CHECK TOOLS
    # -------------------------------------------------------------------------

    def check_tools(self) -> bool:
        """
        Verify available validation tools.

        Required: PIL/Pillow (pip install Pillow)
        Optional: identify (ImageMagick), file, jpeginfo, pngcheck

        Returns:
            bool: True if at least PIL is available
        """
        ptprint("\n[STEP 2/6] Checking Validation Tools",
                "TITLE", condition=not self.args.json)

        # PIL
        self._tools["pil"] = PIL_AVAILABLE or self.dry_run
        if self._tools["pil"]:
            ptprint("✓ PIL/Pillow: Found",
                    "OK", condition=not self.args.json)
        else:
            ptprint("✗ PIL/Pillow: NOT FOUND (required)",
                    "ERROR", condition=not self.args.json)
            ptprint("  Install: pip install Pillow --break-system-packages",
                    "ERROR", condition=not self.args.json)

        # Optional tools
        optional = {
            "identify":  "ImageMagick identify",
            "file":      "MIME type detection",
            "jpeginfo":  "JPEG-specific validation",
            "pngcheck":  "PNG-specific validation",
        }
        for tool, desc in optional.items():
            found = self._tool_present(tool)
            self._tools[tool] = found
            level = "OK" if found else "WARNING"
            ptprint(f"{'✓' if found else '⚠'} {tool}: {'Found' if found else 'Not found'} ({desc})",
                    level, condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "toolsCheck",
            properties={"success": self._tools.get("pil", False),
                        "tools": self._tools}
        ))
        return self._tools.get("pil", False)

    # -------------------------------------------------------------------------
    # PHASE 3 – PREPARE DIRECTORIES
    # -------------------------------------------------------------------------

    def prepare_directories(self) -> bool:
        """
        Create validation output directory tree.

        Structure:
            {case_id}_validation/
                valid/           fully functional images
                corrupted/       partially readable, candidates for repair (Step 17)
                unrecoverable/   false positives / irrecoverable fragments
        """
        ptprint("\n[STEP 3/6] Preparing Validation Directories",
                "TITLE", condition=not self.args.json)

        for d in [self.valid_dir, self.corrupted_dir, self.unrecoverable_dir]:
            if not self.dry_run:
                d.mkdir(parents=True, exist_ok=True)
            ptprint(f"  {d.relative_to(self.validation_base)}/",
                    "INFO", condition=not self.args.json)

        ptprint("✓ Directories ready", "OK", condition=not self.args.json)
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "directoriesPrep",
            properties={
                "success":          True,
                "validDir":         str(self.valid_dir),
                "corruptedDir":     str(self.corrupted_dir),
                "unrecoverableDir": str(self.unrecoverable_dir),
            }
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 4 – PER-FILE VALIDATION
    # -------------------------------------------------------------------------

    def _check_magic(self, filepath: Path, ext: str) -> bool:
        """Return True if the file's first bytes match its format's magic signature."""
        magic_key = EXT_TO_MAGIC.get(ext.lower())
        if not magic_key:
            return True  # Unknown format – skip magic check, give benefit of doubt
        signatures = MAGIC_BYTES.get(magic_key, [])
        try:
            header = filepath.read_bytes()[:16]
            return any(header.startswith(sig) for sig in signatures)
        except Exception:
            return False

    def _validate_file_command(self, filepath: Path) -> Optional[Dict]:
        """Run `file --mime-type` and return dict(success, mime_type)."""
        if not self._tools.get("file"):
            return None
        res = self._run_command(["file", "-b", "--mime-type", str(filepath)],
                                timeout=FILE_TIMEOUT)
        if not res["success"]:
            return None
        mime = res["stdout"]
        return {"success": mime.startswith("image/"), "mimeType": mime,
                "error": None if mime.startswith("image/") else f"Not image MIME: {mime}"}

    def _validate_imagemagick(self, filepath: Path) -> Optional[Dict]:
        """Run `identify` and return dict(success, geometry, error)."""
        if not self._tools.get("identify"):
            return None
        res = self._run_command(["identify", str(filepath)], timeout=VALIDATE_TIMEOUT)
        if res["success"]:
            return {"success": True, "tool": "imagemagick"}
        return {"success": False, "tool": "imagemagick",
                "error": res["stderr"][:200] if res["stderr"] else "identify failed"}

    def _validate_pil(self, filepath: Path) -> Dict:
        """
        Validate with PIL: open → verify → reopen → load.

        Returns dict(success, width?, height?, mode?, error?, corruptionType?)
        """
        if self.dry_run:
            return {"success": True, "tool": "pil",
                    "width": 1920, "height": 1080, "mode": "RGB"}
        try:
            img = Image.open(filepath)
            img.verify()
            # verify() closes the file – must reopen
            img = Image.open(filepath)
            img.load()
            w, h = img.size
            if w == 0 or h == 0:
                return {"success": False, "tool": "pil",
                        "error": "Invalid dimensions (0×0)",
                        "corruptionType": "corrupt_data"}
            return {"success": True, "tool": "pil",
                    "width": w, "height": h, "mode": img.mode}
        except (UnidentifiedImageError, Exception) as exc:
            err = str(exc).lower()
            if "truncated" in err or "premature end" in err:
                ctype = "truncated"
            elif "cannot identify" in err or "cannot decode" in err:
                ctype = "invalid_header"
            elif "corrupt" in err or "broken" in err:
                ctype = "corrupt_segments"
            else:
                ctype = "corrupt_data"
            return {"success": False, "tool": "pil",
                    "error": str(exc)[:200], "corruptionType": ctype}

    def _validate_jpeginfo(self, filepath: Path) -> Optional[Dict]:
        """Run `jpeginfo -c` for JPEG-specific validation."""
        if not self._tools.get("jpeginfo"):
            return None
        res = self._run_command(["jpeginfo", "-c", str(filepath)], timeout=VALIDATE_TIMEOUT)
        # jpeginfo exits 0 for OK, non-zero for errors; stderr contains diagnosis
        if res["success"]:
            return {"success": True, "tool": "jpeginfo"}
        detail = (res["stdout"] + " " + res["stderr"]).strip()[:200]
        ctype  = "truncated" if "truncated" in detail.lower() else "corrupt_segments"
        return {"success": False, "tool": "jpeginfo",
                "error": detail, "corruptionType": ctype}

    def _validate_pngcheck(self, filepath: Path) -> Optional[Dict]:
        """Run `pngcheck -v` for PNG-specific validation."""
        if not self._tools.get("pngcheck"):
            return None
        res = self._run_command(["pngcheck", "-v", str(filepath)], timeout=VALIDATE_TIMEOUT)
        if res["success"]:
            return {"success": True, "tool": "pngcheck"}
        detail = (res["stdout"] + " " + res["stderr"]).strip()[:200]
        ctype  = "truncated" if "truncated" in detail.lower() else "corrupt_segments"
        return {"success": False, "tool": "pngcheck",
                "error": detail, "corruptionType": ctype}

    def _validate_single(self, file_info: Dict) -> Dict:
        """
        Run the full multi-tool validation pipeline on one file.

        Pipeline:
          size check → magic bytes → file command → ImageMagick
          → PIL → format-specific (jpeginfo or pngcheck)

        Returns:
            dict(status, magicValid, toolsPassed, toolsTotal, …)
        """
        path_rel = file_info.get("path") or file_info.get("consolidated_path", "")
        filepath  = self._file_path(path_rel)

        # Size check
        try:
            size = filepath.stat().st_size if not self.dry_run else 1024
        except OSError:
            return {"status": "unrecoverable", "error": "File not found",
                    "magicValid": False, "toolsPassed": 0, "toolsTotal": 0}

        if size == 0:
            return {"status": "unrecoverable", "error": "Empty file (0 bytes)",
                    "magicValid": False, "toolsPassed": 0, "toolsTotal": 0}

        ext       = (file_info.get("format") or
                     file_info.get("extension") or
                     Path(file_info.get("filename", "")).suffix.lstrip(".")).lower()
        magic_ok  = self._check_magic(filepath, ext) if not self.dry_run else True

        # Collect tool results (skip None returns)
        raw_results: List[Dict] = []

        for result in [
            self._validate_file_command(filepath),
            self._validate_imagemagick(filepath),
            self._validate_pil(filepath),
            self._validate_jpeginfo(filepath) if ext in ("jpg", "jpeg") else None,
            self._validate_pngcheck(filepath) if ext == "png" else None,
        ]:
            if result is not None:
                raw_results.append(result)

        passed = sum(1 for r in raw_results if r.get("success"))
        total  = len(raw_results)

        base = {
            "fileSize":   size,
            "magicValid": magic_ok,
            "toolsPassed": passed,
            "toolsTotal":  total,
            "toolResults": raw_results,
        }

        if passed == total and magic_ok:
            # Find PIL result for dimensions
            pil = next((r for r in raw_results if r.get("tool") == "pil"), {})
            return {**base, "status": "valid",
                    "width": pil.get("width"),
                    "height": pil.get("height"),
                    "mode": pil.get("mode")}

        if passed > 0:
            # At least one tool passed → corrupted but potentially repairable
            ctype = "invalid_header" if not magic_ok else "unknown"
            for r in raw_results:
                if not r.get("success") and r.get("corruptionType"):
                    ctype = r["corruptionType"]
                    break
            errors = [r.get("error", "") for r in raw_results
                      if not r.get("success") and r.get("error")]
            return {**base, "status": "corrupted",
                    "corruptionType": ctype, "errors": errors}

        # All failed → unrecoverable
        errors = [r.get("error", "") for r in raw_results if r.get("error")]
        return {**base, "status": "unrecoverable",
                "corruptionType": "false_positive", "errors": errors}

    def _repair_info(self, ctype: str) -> Dict:
        """Return repairability metadata for a corruption type."""
        info = CORRUPTION_TYPES.get(ctype, CORRUPTION_TYPES["unknown"])
        return {
            "corruptionType": ctype,
            "level":       info["level"],
            "repairable":  info["repairable"],
            "technique":   info["technique"],
        }

    def validate_all_files(self) -> None:
        """
        Phase 4 – Iterate through every catalog entry and validate it.

        Updates self._results, self._valid, self._corrupted,
        self._unrecoverable, self._by_format, self._by_source,
        self._corruption_types, self._need_repair.
        """
        ptprint("\n[STEP 4/6] Validating Files",
                "TITLE", condition=not self.args.json)

        files = self.catalog.get("files", [])
        total = len(files)

        for idx, fi in enumerate(files, 1):
            if idx % 50 == 0 or idx == total:
                pct = idx * 100 // total
                ptprint(f"  {idx}/{total} ({pct}%)",
                        "INFO", condition=not self.args.json)

            v = self._validate_single(fi)

            fmt    = (fi.get("format") or fi.get("extension") or "unknown").lower()
            source = (fi.get("recoveryMethod") or fi.get("recovery_method") or "unknown")
            status = v["status"]

            entry: Dict[str, Any] = {
                "fileId":        fi.get("id"),
                "filename":      fi.get("filename"),
                "path":          fi.get("path"),
                "format":        fmt,
                "recoveryMethod": source,
                "status":        status,
                "fileSize":      v.get("fileSize"),
                "magicValid":    v.get("magicValid"),
                "toolsPassed":   v.get("toolsPassed"),
                "toolsTotal":    v.get("toolsTotal"),
            }

            if status == "valid":
                self._valid += 1
                entry.update({
                    "width": v.get("width"),
                    "height": v.get("height"),
                    "mode": v.get("mode"),
                })

            elif status == "corrupted":
                self._corrupted += 1
                ctype = v.get("corruptionType", "unknown")
                entry["corruptionType"] = ctype
                entry["errors"] = v.get("errors", [])
                ri = self._repair_info(ctype)
                entry["repairInfo"] = ri

                if ri["repairable"] not in (False,):
                    self._need_repair.append({
                        "fileId":         fi.get("id"),
                        "filename":       fi.get("filename"),
                        "corruptionType": ctype,
                        "level":          ri["level"],
                        "repairable":     ri["repairable"],
                        "technique":      ri["technique"],
                    })

                self._corruption_types[ctype] = \
                    self._corruption_types.get(ctype, 0) + 1

            else:  # unrecoverable
                self._unrecoverable += 1
                entry["errors"] = v.get("errors", [])
                ct = v.get("corruptionType", "false_positive")
                self._corruption_types[ct] = \
                    self._corruption_types.get(ct, 0) + 1

            # Per-format and per-source breakdown
            for bucket, key in [(self._by_format, fmt), (self._by_source, source)]:
                if key not in bucket:
                    bucket[key] = {"total": 0, "valid": 0, "corrupted": 0, "unrecoverable": 0}
                bucket[key]["total"] += 1
                bucket[key][status]  += 1

            self._results.append(entry)

        integrity = round(self._valid / max(self._total, 1) * 100, 2)

        ptprint(f"✓ Valid:           {self._valid}",
                "OK",      condition=not self.args.json)
        ptprint(f"  Corrupted:       {self._corrupted}",
                "WARNING", condition=not self.args.json)
        ptprint(f"  Unrecoverable:   {self._unrecoverable}",
                "ERROR",   condition=not self.args.json)
        ptprint(f"  Integrity score: {integrity}%",
                "OK",      condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "fileValidation",
            properties={
                "validFiles":        self._valid,
                "corruptedFiles":    self._corrupted,
                "unrecoverableFiles": self._unrecoverable,
                "integrityScore":    integrity,
                "filesNeedingRepair": len(self._need_repair),
                "corruptionTypes":   self._corruption_types,
            }
        ))

    # -------------------------------------------------------------------------
    # PHASE 5 – ORGANISE INTO DIRECTORIES
    # -------------------------------------------------------------------------

    def organise_files(self) -> None:
        """
        Phase 5 – Copy validated files into valid / corrupted / unrecoverable.

        Uses shutil.copy2 (preserves timestamps). Never moves or deletes
        the source file in the consolidated directory.
        """
        ptprint("\n[STEP 5/6] Organising Files",
                "TITLE", condition=not self.args.json)

        for entry in self._results:
            src = self._file_path(entry.get("path", ""))
            if not src.exists() and not self.dry_run:
                continue

            target_root = {
                "valid":         self.valid_dir,
                "corrupted":     self.corrupted_dir,
                "unrecoverable": self.unrecoverable_dir,
            }.get(entry["status"], self.unrecoverable_dir)

            dst = target_root / entry["filename"]

            # Collision guard
            if not self.dry_run and dst.exists():
                stem, suffix = dst.stem, dst.suffix
                counter = 1
                while dst.exists():
                    dst = target_root / f"{stem}_{counter}{suffix}"
                    counter += 1

            if not self.dry_run:
                try:
                    shutil.copy2(src, dst)
                except Exception as exc:
                    ptprint(f"  ⚠ Copy failed for {entry['filename']}: {exc}",
                            "WARNING", condition=not self.args.json)

        ptprint("✓ Files organised into validation directories",
                "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "filesOrganised",
            properties={
                "validDir":         str(self.valid_dir),
                "corruptedDir":     str(self.corrupted_dir),
                "unrecoverableDir": str(self.unrecoverable_dir),
            }
        ))

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full six-phase validation pipeline."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("PHOTO INTEGRITY VALIDATION", "TITLE", condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_master_catalog():
            self.ptjsonlib.set_status("finished")
            return

        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return

        self.prepare_directories()
        self.validate_all_files()
        self.organise_files()

        # Final properties
        integrity = round(self._valid / max(self._total, 1) * 100, 2)
        self.ptjsonlib.add_properties({
            "validFiles":         self._valid,
            "corruptedFiles":     self._corrupted,
            "unrecoverableFiles": self._unrecoverable,
            "integrityScore":     integrity,
            "filesNeedingRepair": len(self._need_repair),
            "byFormat":           self._by_format,
            "bySource":           self._by_source,
            "corruptionTypes":    self._corruption_types,
        })

        # Console summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("VALIDATION COMPLETED", "OK",   condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Total files:      {self._total}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Valid:          {self._valid}",
                "OK",   condition=not self.args.json)
        ptprint(f"  Corrupted:      {self._corrupted}",
                "WARNING", condition=not self.args.json)
        ptprint(f"  Unrecoverable:  {self._unrecoverable}",
                "ERROR", condition=not self.args.json)
        ptprint(f"Integrity score:  {integrity}%",
                "OK",   condition=not self.args.json)
        ptprint(f"Files for repair: {len(self._need_repair)}",
                "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint("\nNext step: Step 16 (Final Report) / Step 17 (Photo Repair)",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    # -------------------------------------------------------------------------
    # PHASE 6 – REPORTS
    # -------------------------------------------------------------------------

    def save_report(self) -> Optional[str]:
        """
        Phase 6 – Save JSON report and human-readable text summary.

        --json mode: prints ptlibs JSON to stdout.
        Otherwise writes:
          - {case_id}_validation_report.json
          - {case_id}_validation/VALIDATION_REPORT.txt

        Returns:
            Path to JSON file, or None in --json mode
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        json_file = self.output_dir / f"{self.case_id}_validation_report.json"
        report    = {
            "result":            json.loads(self.ptjsonlib.get_result_json()),
            "validationResults": self._results,
            "filesNeedingRepair": self._need_repair,
        }

        if not self.dry_run:
            with open(json_file, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
        ptprint(f"✓ JSON report saved: {json_file.name}",
                "OK", condition=not self.args.json)

        # Text report
        self.validation_base.mkdir(parents=True, exist_ok=True)
        txt_file = self.validation_base / "VALIDATION_REPORT.txt"
        props    = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        integrity = props.get("integrityScore", 0.0)

        if not self.dry_run:
            with open(txt_file, "w", encoding="utf-8") as fh:
                fh.write("=" * 70 + "\n")
                fh.write("PHOTO INTEGRITY VALIDATION REPORT\n")
                fh.write("=" * 70 + "\n\n")
                fh.write(f"Case ID:   {self.case_id}\n")
                fh.write(f"Timestamp: {props.get('timestamp','')}\n\n")
                fh.write("SUMMARY:\n")
                fh.write(f"  Total files:         {props.get('totalFiles',0)}\n")
                fh.write(f"  Valid:               {props.get('validFiles',0)} ({integrity}%)\n")
                fh.write(f"  Corrupted:           {props.get('corruptedFiles',0)}\n")
                fh.write(f"  Unrecoverable:       {props.get('unrecoverableFiles',0)}\n")
                fh.write(f"  Files needing repair:{props.get('filesNeedingRepair',0)}\n\n")
                fh.write("INTEGRITY SCORE INTERPRETATION:\n")
                if integrity >= 95:
                    fh.write("  EXCELLENT – ready for delivery\n\n")
                elif integrity >= 85:
                    fh.write("  GOOD – most photos usable\n\n")
                elif integrity >= 70:
                    fh.write("  FAIR – significant corruption, repair recommended\n\n")
                else:
                    fh.write("  POOR – heavy corruption, source media badly damaged\n\n")
                fh.write("BY FORMAT:\n")
                for fmt, data in sorted(self._by_format.items()):
                    t = data["total"]
                    v = data["valid"]
                    pct = v / t * 100 if t else 0
                    fh.write(f"  {fmt:8s}: {v}/{t} valid ({pct:.1f}%)\n")
                fh.write("\nBY SOURCE:\n")
                for src, data in sorted(self._by_source.items()):
                    t   = data["total"]
                    v   = data["valid"]
                    pct = v / t * 100 if t else 0
                    exp = EXPECTED_INTEGRITY.get(src, "?")
                    fh.write(f"  {src}: {v}/{t} valid ({pct:.1f}%)  expected {exp}\n")
                if self._corruption_types:
                    fh.write("\nCORRUPTION TYPES:\n")
                    for ct, cnt in sorted(self._corruption_types.items(),
                                          key=lambda x: -x[1]):
                        info = CORRUPTION_TYPES.get(ct, {})
                        fh.write(f"  {ct}: {cnt}  (L{info.get('level','?')}, "
                                 f"repairable={info.get('repairable','?')})\n")
                if self._need_repair:
                    fh.write(f"\nFILES NEEDING REPAIR (first 30 of {len(self._need_repair)}):\n")
                    for nf in self._need_repair[:30]:
                        fh.write(f"  [{nf['corruptionType']}] {nf['filename']}: "
                                 f"{nf['technique']}\n")
        ptprint(f"✓ Text report saved: {txt_file.name}",
                "OK", condition=not self.args.json)
        return str(json_file)


# ============================================================================
# CLI HELPERS
# ============================================================================

def get_help():
    return [
        {"description": [
            "Forensic photo integrity validation tool – ptlibs compliant",
            "Multi-tool validation: magic bytes, file, ImageMagick, PIL, jpeginfo, pngcheck",
            "Classifies files as valid / corrupted / unrecoverable",
        ]},
        {"usage": ["ptintegrityvalidation <case-id> [options]"]},
        {"usage_example": [
            "ptintegrityvalidation PHOTO-2025-001",
            "ptintegrityvalidation CASE-042 --json",
            "ptintegrityvalidation TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",    "",              "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<dir>",  f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",              "Simulate without reading files or copying"],
            ["-j",  "--json",       "",      "JSON output for platform integration"],
            ["-q",  "--quiet",      "",      "Suppress progress output"],
            ["-h",  "--help",       "",      "Show this help and exit"],
            ["--version",  "",              "Show version and exit"],
        ]},
        {"validation_pipeline": [
            "Phase 1: Load master_catalog.json from Step 13",
            "Phase 2: Check tools (PIL required; ImageMagick, file, jpeginfo, pngcheck optional)",
            "Phase 3: Prepare valid / corrupted / unrecoverable directories",
            "Phase 4: Per-file: size → magic bytes → file → identify → PIL → format-specific",
            "Phase 5: Copy files into categorised output directories",
            "Phase 6: Save JSON report + VALIDATION_REPORT.txt",
        ]},
        {"corruption_types": [
            "L1 truncated       – missing footer bytes (easily repairable)",
            "L2 invalid_header  – corrupt file header (repairable)",
            "L2 corrupt_segments– bad JPEG/PNG segments (repairable)",
            "L3 corrupt_data    – pixel data corruption (partial recovery)",
            "L4 fragmented      – file fragments (manual defragmentation)",
            "L5 false_positive  – not an image (discard)",
        ]},
        {"expected_integrity": [
            "FS-based recovery (12A): >95% valid",
            "File carving (12B):      70–85% valid",
            "Active files:            ~99% valid",
            "Deleted files:           ~78% valid (partial overwrites)",
        ]},
        {"forensic_notes": [
            "READ-ONLY on source consolidated directory (copy2 only)",
            "Requires Step 13 (Consolidation) output",
            "ISO/IEC 10918-1, PNG ISO/IEC 15948:2004, NIST SP 800-86 compliant",
        ]},
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Forensic photo integrity validation"
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
    SCRIPTNAME = "ptintegrityvalidation"
    try:
        args = parse_args()
        tool = PtIntegrityValidation(args)
        tool.run()
        tool.save_report()

        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("integrityScore", 0) > 0 else 1

    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())
