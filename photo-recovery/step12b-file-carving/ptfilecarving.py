#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptfilecarving - Forensic file carving photo recovery tool

    ptfilecarving is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptfilecarving is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptfilecarving.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import re
import json
import shutil
import hashlib
import subprocess
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/images"
PHOTOREC_TIMEOUT   = 86400   # 24 hours absolute ceiling for PhotoRec
VALIDATE_TIMEOUT   = 30      # seconds per file for identify
EXIF_TIMEOUT       = 30      # seconds per file for exiftool
HASH_CHUNK         = 65536   # 64 KB read chunks for SHA-256

# Image formats that PhotoRec will be instructed to search for.
# Key = PhotoRec keyword / extension, Value = human description.
IMAGE_FORMATS: Dict[str, str] = {
    "jpg":  "JPEG images",
    "png":  "PNG images",
    "gif":  "GIF images",
    "bmp":  "Bitmap images",
    "tiff": "TIFF images",
    "heic": "HEIC/HEIF images (Apple)",
    "webp": "WebP images",
    # RAW formats
    "cr2":  "Canon RAW (older)",
    "cr3":  "Canon RAW (newer)",
    "nef":  "Nikon RAW",
    "arw":  "Sony RAW",
    "dng":  "Adobe / Generic DNG RAW",
    "orf":  "Olympus RAW",
    "raf":  "Fuji RAW",
    "rw2":  "Panasonic RAW",
}

# Extension → output sub-folder inside organized/
FORMAT_DIRS: Dict[str, str] = {
    "jpg": "jpg", "jpeg": "jpg",
    "png": "png",
    "tif": "tiff", "tiff": "tiff",
    "cr2": "raw", "cr3": "raw",
    "nef": "raw", "nrw": "raw",
    "arw": "raw", "srf": "raw", "sr2": "raw",
    "dng": "raw",
    "orf": "raw",
    "raf": "raw",
    "rw2": "raw",
    "pef": "raw",
    "raw": "raw",
    "heic": "other", "heif": "other",
    "webp": "other",
    "gif":  "other",
    "bmp":  "other",
}


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtFileCarving:
    """
    Forensic file carving photo recovery tool - ptlibs compliant.

    Six-phase recovery process:
    1. Load filesystem analysis from Step 10 (image path, method check)
    2. Check required tools (photorec, file, identify, exiftool)
    3. Prepare output directory structure
    4. Run PhotoRec carving + collect raw carved files
    5. Validate (file + ImageMagick) and deduplicate (SHA-256)
    6. Extract EXIF, organise by type, rename systematically, save reports

    NOTE: original filenames and directory structure are NOT preserved.
    Files are renamed to {case_id}_{type}_{sequence:06d}.{ext}.

    Complies with NIST SP 800-86 Section 3.1.2.3 and ISO/IEC 27037:2012.
    READ-ONLY: never modifies the forensic image.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.force      = self.args.force
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State filled during run
        self.image_path  = None
        self.fs_analysis = None

        # Output directory tree
        self.carving_base   = self.output_dir / f"{self.case_id}_carved"
        self.photorec_work  = self.carving_base / "photorec_work"
        self.organized_dir  = self.carving_base / "organized"
        self.corrupted_dir  = self.carving_base / "corrupted"
        self.quarantine_dir = self.carving_base / "quarantine"
        self.duplicates_dir = self.carving_base / "duplicates"
        self.metadata_dir   = self.carving_base / "metadata"

        # Counters
        self._total_carved_raw   = 0
        self._valid              = 0
        self._corrupted          = 0
        self._invalid            = 0
        self._duplicates_removed = 0
        self._final_unique       = 0
        self._with_exif          = 0
        self._with_gps           = 0
        self._by_format: Dict[str, int] = {}
        self._carving_seconds    = 0.0
        self._validate_seconds   = 0.0

        # Per-file tracking
        self._hash_db: Dict[str, str] = {}   # sha256 → filepath str
        self._unique_files: List[Dict] = []

        # Top-level JSON properties
        self.ptjsonlib.add_properties({
            "caseId":               self.case_id,
            "outputDirectory":      str(self.output_dir),
            "timestamp":            datetime.now(timezone.utc).isoformat(),
            "scriptVersion":        __version__,
            "method":               "file_carving",
            "tool":                 "PhotoRec",
            "imagePath":            None,
            "totalCarvedRaw":       0,
            "validAfterValidation": 0,
            "corruptedFiles":       0,
            "invalidFiles":         0,
            "duplicatesRemoved":    0,
            "finalUniqueFiles":     0,
            "withExif":             0,
            "withGps":              0,
            "byFormat":             {},
            "carvingSeconds":       0,
            "validationSeconds":    0,
            "successRate":          None,
            "carvingBaseDir":       str(self.carving_base),
            "dryRun":               self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------------------

    def _run_command(self, cmd: List[str], timeout: Optional[int] = 300,
                     stream_output: bool = False) -> Dict[str, Any]:
        """
        Execute a subprocess.

        When stream_output=True the process is run with real-time stdout
        (used for PhotoRec) and returncode is returned after completion.
        """
        result = {"success": False, "stdout": "", "stderr": "", "returncode": -1}

        if self.dry_run:
            ptprint(f"[DRY-RUN] Would execute: {' '.join(str(c) for c in cmd)}",
                    "INFO", condition=not self.args.json)
            result["success"] = True
            result["stdout"]  = "[DRY-RUN] Simulated success"
            return result

        try:
            if stream_output:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                )
                for line in proc.stdout:
                    if not self.args.json:
                        print(line, end='', flush=True)
                proc.wait(timeout=timeout)
                result.update({"success": proc.returncode == 0,
                               "returncode": proc.returncode})
            else:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=timeout, check=False
                )
                result.update({
                    "success":    proc.returncode == 0,
                    "stdout":     proc.stdout.strip(),
                    "stderr":     proc.stderr.strip(),
                    "returncode": proc.returncode,
                })
        except subprocess.TimeoutExpired:
            result["stderr"] = f"Command timeout after {timeout}s"
        except Exception as exc:
            result["stderr"] = str(exc)

        return result

    def _sha256(self, filepath: Path) -> Optional[str]:
        """Return hex SHA-256 digest of a file, or None on error."""
        h = hashlib.sha256()
        try:
            with open(filepath, "rb") as fh:
                for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # PHASE 1 – LOAD STEP 10 ANALYSIS
    # -------------------------------------------------------------------------

    def load_fs_analysis(self) -> bool:
        """
        Load filesystem analysis results from Step 10 and extract the image path.

        Accepts both the ptlibs JSON format (result.properties) and the legacy
        flat format produced by the original step10 wrapper script.

        Warns if Step 10 recommended filesystem_scan but continues unless
        --force is absent AND method is not file_carving or hybrid.

        Returns:
            bool: True if image path resolved successfully
        """
        ptprint("\n[STEP 1/6] Loading Filesystem Analysis from Step 10",
                "TITLE", condition=not self.args.json)

        analysis_file = self.output_dir / f"{self.case_id}_filesystem_analysis.json"

        if not analysis_file.exists():
            ptprint(f"✗ File not found: {analysis_file.name}",
                    "ERROR", condition=not self.args.json)
            ptprint("  Please run Step 10 (Filesystem Analysis) first!",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False, "error": "filesystem_analysis.json not found"}
            ))
            return False

        try:
            with open(analysis_file, 'r', encoding='utf-8') as fh:
                raw = json.load(fh)
        except Exception as exc:
            ptprint(f"✗ Cannot read analysis file: {exc}",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False, "error": str(exc)}
            ))
            return False

        # Support ptlibs JSON and flat/legacy JSON
        if "result" in raw and "properties" in raw["result"]:
            props       = raw["result"]["properties"]
            recommended = props.get("recommendedMethod")
            image_path_str = props.get("imagePath")
        else:
            self.fs_analysis = raw
            recommended    = raw.get("recommended_method")
            image_path_str = raw.get("image_file") or raw.get("imagePath")

        # Method compatibility check
        if recommended == "filesystem_scan" and not self.force:
            ptprint("⚠ Step 10 recommended filesystem_scan, not file_carving",
                    "WARNING", condition=not self.args.json)
            ptprint("  Use --force to override, or run Step 12A instead",
                    "WARNING", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False,
                            "error": "Method mismatch: filesystem_scan recommended"}
            ))
            return False

        if recommended == "hybrid":
            ptprint("⚠ Step 10 recommended hybrid approach",
                    "WARNING", condition=not self.args.json)
            ptprint("  File carving will complement filesystem-based recovery (Step 12A)",
                    "INFO", condition=not self.args.json)

        if not image_path_str:
            ptprint("✗ Image path missing in analysis file",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False, "error": "imagePath missing"}
            ))
            return False

        self.image_path = Path(image_path_str)
        if not self.image_path.exists() and not self.dry_run:
            ptprint(f"✗ Forensic image not found: {self.image_path}",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False,
                            "error": f"Image file missing: {self.image_path}"}
            ))
            return False

        ptprint(f"✓ Analysis loaded: {analysis_file.name}",
                "OK", condition=not self.args.json)
        ptprint(f"  Image:   {self.image_path.name}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Method:  {recommended}",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "fsAnalysisLoad",
            properties={
                "success":           True,
                "sourceFile":        str(analysis_file),
                "recommendedMethod": recommended,
                "imagePath":         str(self.image_path),
            }
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 2 – CHECK TOOLS
    # -------------------------------------------------------------------------

    def check_tools(self) -> bool:
        """
        Verify all required external tools are installed.

        Required: photorec (testdisk package), file (coreutils),
                  identify (ImageMagick), exiftool.

        Returns:
            bool: True if all tools present
        """
        ptprint("\n[STEP 2/6] Checking Required Tools",
                "TITLE", condition=not self.args.json)

        required = {
            "photorec":  "PhotoRec – file carving engine",
            "file":      "File type detection",
            "identify":  "ImageMagick – image validation",
            "exiftool":  "EXIF metadata extraction",
        }
        missing = []

        for tool, description in required.items():
            res = self._run_command(["which", tool], timeout=5)
            if res["success"]:
                ptprint(f"✓ {tool}: Found ({description})",
                        "OK", condition=not self.args.json)
            else:
                ptprint(f"✗ {tool}: NOT FOUND ({description})",
                        "ERROR", condition=not self.args.json)
                missing.append(tool)

        if missing:
            ptprint(f"✗ Missing tools: {', '.join(missing)}",
                    "ERROR", condition=not self.args.json)
            ptprint("  Install: sudo apt-get install testdisk imagemagick libimage-exiftool-perl",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "toolsCheck",
                properties={"success": False, "missingTools": missing}
            ))
            return False

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "toolsCheck",
            properties={"success": True, "toolsChecked": list(required.keys())}
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 3 – PREPARE DIRECTORIES
    # -------------------------------------------------------------------------

    def prepare_directories(self) -> bool:
        """
        Create output directory structure.

        Structure:
            {case_id}_carved/
                photorec_work/          PhotoRec raw output (recup_dir.*)
                organized/              Final renamed files by type
                    jpg/  png/  tiff/  raw/  other/
                corrupted/              Partially damaged files
                quarantine/             Invalid / false positives
                duplicates/             SHA-256 duplicates
                metadata/               Per-file EXIF JSON catalogs

        Returns:
            bool: True always
        """
        ptprint("\n[STEP 3/6] Preparing Output Directories",
                "TITLE", condition=not self.args.json)

        base_dirs = [self.photorec_work, self.organized_dir, self.corrupted_dir,
                     self.quarantine_dir, self.duplicates_dir, self.metadata_dir]
        for d in base_dirs:
            if not self.dry_run:
                d.mkdir(parents=True, exist_ok=True)
            ptprint(f"  {d.relative_to(self.carving_base)}/",
                    "INFO", condition=not self.args.json)

        # Type sub-folders
        for sub in ["jpg", "png", "tiff", "raw", "other"]:
            if not self.dry_run:
                (self.organized_dir / sub).mkdir(exist_ok=True)

        ptprint("✓ Output directories ready",
                "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "directoriesPrep",
            properties={
                "success":        True,
                "carvingBase":    str(self.carving_base),
                "photorec_work":  str(self.photorec_work),
                "organizedDir":   str(self.organized_dir),
                "corruptedDir":   str(self.corrupted_dir),
                "quarantineDir":  str(self.quarantine_dir),
                "duplicatesDir":  str(self.duplicates_dir),
                "metadataDir":    str(self.metadata_dir),
            }
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 4 – PHOTOREC CARVING
    # -------------------------------------------------------------------------

    def _write_photorec_config(self) -> Path:
        """
        Write a PhotoRec batch-mode command file that enables only image
        formats and enables paranoid + expert search options.

        Returns:
            Path to the generated command file
        """
        cmd_file = self.photorec_work / "photorec.cmd"
        lines = ["fileopt,everything,disable"]
        for fmt in IMAGE_FORMATS:
            lines.append(f"fileopt,{fmt},enable")
        lines += [
            "options,paranoid,enable",
            "options,expert,enable",
            "search",
        ]
        if not self.dry_run:
            cmd_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ptprint(f"  Config: {cmd_file.name}  ({len(IMAGE_FORMATS)} formats enabled)",
                "INFO", condition=not self.args.json)
        return cmd_file

    def run_photorec(self) -> bool:
        """
        Phase 4a – Run PhotoRec on the forensic image.

        PhotoRec is invoked in non-interactive mode:
            photorec /log /d photorec_work/ /cmd image.dd search

        This phase can take 2–8 hours for large media.
        Progress is streamed to the console in non-JSON mode.

        Returns:
            bool: True if PhotoRec exited successfully
        """
        ptprint("\n[STEP 4/6] Running PhotoRec File Carving",
                "TITLE", condition=not self.args.json)
        ptprint("  ⚠ This process may take 2–8 hours – do not interrupt",
                "WARNING", condition=not self.args.json)

        self._write_photorec_config()

        cmd = [
            "photorec",
            "/log",
            "/d", str(self.photorec_work),
            "/cmd", str(self.image_path),
            "search",
        ]

        ptprint(f"  Command: {' '.join(cmd)}", "INFO", condition=not self.args.json)

        start = datetime.now()
        result = self._run_command(cmd, timeout=PHOTOREC_TIMEOUT, stream_output=True)
        self._carving_seconds = (datetime.now() - start).total_seconds()

        if result["success"]:
            ptprint(f"✓ PhotoRec completed in {self._carving_seconds/60:.1f} min",
                    "OK", condition=not self.args.json)
        else:
            ptprint(f"✗ PhotoRec failed: {result.get('stderr', '')}",
                    "ERROR", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "photorec",
            properties={
                "success":         result["success"],
                "carvingSeconds":  round(self._carving_seconds, 1),
                "command":         " ".join(cmd),
            }
        ))
        return result["success"]

    def collect_carved_files(self) -> List[Path]:
        """
        Phase 4b – Collect all files from PhotoRec's recup_dir.* folders.

        Returns:
            List of Path objects for every carved file
        """
        ptprint("\n  Collecting carved files from recup_dir folders …",
                "INFO", condition=not self.args.json)

        recup_dirs = sorted(self.photorec_work.glob("recup_dir.*"))

        if not recup_dirs and not self.dry_run:
            ptprint("  ✗ No recup_dir folders found – PhotoRec produced no output",
                    "ERROR", condition=not self.args.json)
            return []

        all_files: List[Path] = []
        for rd in recup_dirs:
            all_files.extend(rd.glob("f*.*"))

        self._total_carved_raw = len(all_files)
        ptprint(f"  ✓ {len(recup_dirs)} recup_dir folder(s), {len(all_files)} files",
                "OK", condition=not self.args.json)
        return all_files

    # -------------------------------------------------------------------------
    # PHASE 5 – VALIDATE + DEDUPLICATE
    # -------------------------------------------------------------------------

    def _validate_file(self, filepath: Path) -> Tuple[bool, str, Dict]:
        """
        Three-stage file validation.

        Stage 1 – minimum size (≥ 100 bytes)
        Stage 2 – `file` command confirms image type
        Stage 3 – ImageMagick `identify` confirms readable structure

        Returns:
            (is_valid, status, info)
            status ∈ {'valid', 'corrupted', 'invalid'}
        """
        info: Dict[str, Any] = {
            "size": 0, "fileType": None,
            "imageFormat": None, "dimensions": None,
            "validationErrors": [],
        }

        # Stage 1 – size
        try:
            size = filepath.stat().st_size
            info["size"] = size
        except Exception as exc:
            info["validationErrors"].append(f"stat: {exc}")
            return False, "invalid", info

        if size < 100:
            info["validationErrors"].append(f"Too small ({size} bytes)")
            return False, "invalid", info

        # Stage 2 – file
        res = self._run_command(["file", "-b", str(filepath)], timeout=10)
        if res["success"]:
            info["fileType"] = res["stdout"]
            keywords = ["image", "jpeg", "png", "tiff", "gif", "bitmap",
                        "raw", "canon", "nikon", "exif", "riff webp", "heic"]
            if not any(kw in res["stdout"].lower() for kw in keywords):
                info["validationErrors"].append(f"file: not an image ({res['stdout'][:80]})")
                return False, "invalid", info

        # Stage 3 – identify
        res = self._run_command(["identify", str(filepath)], timeout=VALIDATE_TIMEOUT)
        if res["success"]:
            m = re.search(r"(\w+)\s+(\d+)x(\d+)", res["stdout"])
            if m:
                info["imageFormat"] = m.group(1)
                info["dimensions"]  = f"{m.group(2)}x{m.group(3)}"
            return True, "valid", info

        info["validationErrors"].append("identify failed – likely corrupted")
        return False, ("corrupted" if size > 10240 else "invalid"), info

    def validate_and_deduplicate(self, carved_files: List[Path]) -> List[Dict]:
        """
        Phase 5 – Validate every carved file and remove SHA-256 duplicates.

        Categories:
            valid      → kept, hash-checked for duplicates
            corrupted  → moved to corrupted/
            invalid    → moved to quarantine/

        Returns:
            List of dicts describing each unique valid file
        """
        ptprint("\n[STEP 5/6] Validating and Deduplicating",
                "TITLE", condition=not self.args.json)

        total = len(carved_files)
        valid_files: List[Dict] = []
        start = datetime.now()

        for idx, filepath in enumerate(carved_files, 1):
            if idx % 50 == 0 or idx == total:
                pct = idx * 100 // total
                ptprint(f"  Progress: {idx}/{total} ({pct}%)",
                        "INFO", condition=not self.args.json)

            is_valid, vstatus, vinfo = self._validate_file(filepath)

            if vstatus == "valid":
                digest = self._sha256(filepath)
                if digest:
                    if digest in self._hash_db:
                        # Duplicate
                        dest = self.duplicates_dir / filepath.name
                        if not self.dry_run:
                            shutil.move(str(filepath), str(dest))
                        self._duplicates_removed += 1
                    else:
                        self._hash_db[digest] = str(filepath)
                        ext = filepath.suffix.lstrip(".").lower()
                        self._by_format[ext] = self._by_format.get(ext, 0) + 1
                        self._valid += 1
                        valid_files.append({
                            "path":      filepath,
                            "hash":      digest,
                            "size":      vinfo["size"],
                            "format":    vinfo.get("imageFormat"),
                            "dimensions": vinfo.get("dimensions"),
                        })

            elif vstatus == "corrupted":
                self._corrupted += 1
                dest = self.corrupted_dir / filepath.name
                if not self.dry_run:
                    shutil.move(str(filepath), str(dest))

            else:  # invalid
                self._invalid += 1
                dest = self.quarantine_dir / filepath.name
                if not self.dry_run:
                    shutil.move(str(filepath), str(dest))

        self._validate_seconds = (datetime.now() - start).total_seconds()
        self._final_unique = len(valid_files)

        ptprint(f"✓ Validation done in {self._validate_seconds:.0f}s",
                "OK", condition=not self.args.json)
        ptprint(f"  Valid (unique): {self._final_unique}",
                "OK", condition=not self.args.json)
        ptprint(f"  Duplicates removed: {self._duplicates_removed}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Corrupted: {self._corrupted}",
                "WARNING", condition=not self.args.json)
        ptprint(f"  Invalid:   {self._invalid}",
                "WARNING", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "validationDedup",
            properties={
                "totalCarvedRaw":    self._total_carved_raw,
                "validUnique":       self._final_unique,
                "duplicatesRemoved": self._duplicates_removed,
                "corrupted":         self._corrupted,
                "invalid":           self._invalid,
                "validationSeconds": round(self._validate_seconds, 1),
            }
        ))
        return valid_files

    # -------------------------------------------------------------------------
    # PHASE 6 – EXIF + ORGANISE + RENAME
    # -------------------------------------------------------------------------

    def _extract_exif(self, filepath: Path) -> Optional[Dict]:
        """
        Extract EXIF metadata using exiftool.

        Returns parsed dict or None if no meaningful EXIF present.
        Updates self._with_exif and self._with_gps counters.
        """
        res = self._run_command(
            ["exiftool", "-json", "-charset", "utf8", str(filepath)],
            timeout=EXIF_TIMEOUT
        )
        if not res["success"]:
            return None
        try:
            data = json.loads(res["stdout"])
            if not data:
                return None
            exif = data[0]
            meaningful = {"DateTimeOriginal", "CreateDate", "GPSLatitude",
                          "Make", "Model", "LensModel", "FocalLength"}
            if meaningful & set(exif.keys()):
                self._with_exif += 1
                if "GPSLatitude" in exif:
                    self._with_gps += 1
                return exif
        except Exception:
            pass
        return None

    def organise_and_rename(self, valid_files: List[Dict]) -> List[Dict]:
        """
        Phase 6 – Move each unique valid file into organized/{type}/,
        rename it to {case_id}_{type}_{seq:06d}.{ext}, extract EXIF,
        save per-file metadata JSON.

        Returns:
            List of dicts with final file info (written to JSON report)
        """
        ptprint("\n[STEP 6/6] Organising and Renaming Files",
                "TITLE", condition=not self.args.json)

        format_counters: Dict[str, int] = defaultdict(int)
        organised: List[Dict] = []

        for file_info in valid_files:
            filepath = file_info["path"]
            ext      = filepath.suffix.lstrip(".").lower()
            subdir   = FORMAT_DIRS.get(ext, "other")
            target   = self.organized_dir / subdir

            format_counters[subdir] += 1
            seq      = format_counters[subdir]
            new_name = f"{self.case_id}_{subdir}_{seq:06d}.{ext}"
            new_path = target / new_name

            if not self.dry_run:
                shutil.move(str(filepath), str(new_path))

            # EXIF
            exif_data = self._extract_exif(new_path if not self.dry_run else filepath)

            if exif_data and not self.dry_run:
                meta_file = self.metadata_dir / f"{new_name}_metadata.json"
                with open(meta_file, "w", encoding="utf-8") as fh:
                    json.dump(exif_data, fh, indent=2, ensure_ascii=False, default=str)

            organised.append({
                "newFilename":          new_name,
                "originalPhotorec":     filepath.name,
                "recoveredPath":        str(new_path.relative_to(self.carving_base))
                                        if not self.dry_run else new_name,
                "hash":                 file_info["hash"],
                "sizeBytes":            file_info["size"],
                "formatGroup":          subdir,
                "dimensions":           file_info.get("dimensions"),
                "hasExif":              exif_data is not None,
                "hasGps":               exif_data.get("GPSLatitude") is not None
                                        if exif_data else False,
            })

        ptprint(f"✓ {len(organised)} files organised",
                "OK", condition=not self.args.json)
        self._unique_files = organised
        return organised

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full six-phase carving pipeline."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("FILE CARVING PHOTO RECOVERY", "TITLE", condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        # Phase 1 – Load Step 10
        if not self.load_fs_analysis():
            self.ptjsonlib.set_status("finished")
            return

        # Phase 2 – Tools
        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return

        # Phase 3 – Directories
        if not self.prepare_directories():
            self.ptjsonlib.set_status("finished")
            return

        # Phase 4 – PhotoRec + collect
        if not self.run_photorec():
            self.ptjsonlib.set_status("finished")
            return

        carved = self.collect_carved_files()
        if not carved and not self.dry_run:
            ptprint("✗ No carved files collected – aborting",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.set_status("finished")
            return

        # Phase 5 – Validate + deduplicate
        valid_files = self.validate_and_deduplicate(carved)

        if not valid_files and not self.dry_run:
            ptprint("✗ No valid files after validation – aborting",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.set_status("finished")
            return

        # Phase 6 – Organise + rename + EXIF
        self.organise_and_rename(valid_files)

        # Final stats
        success_rate: Optional[float] = None
        if self._total_carved_raw > 0:
            success_rate = round(self._final_unique / self._total_carved_raw * 100, 1)

        self.ptjsonlib.add_properties({
            "totalCarvedRaw":       self._total_carved_raw,
            "validAfterValidation": self._valid,
            "corruptedFiles":       self._corrupted,
            "invalidFiles":         self._invalid,
            "duplicatesRemoved":    self._duplicates_removed,
            "finalUniqueFiles":     self._final_unique,
            "withExif":             self._with_exif,
            "withGps":              self._with_gps,
            "byFormat":             self._by_format,
            "carvingSeconds":       round(self._carving_seconds, 1),
            "validationSeconds":    round(self._validate_seconds, 1),
            "successRate":          success_rate,
        })

        # Summary node
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "carvingSummary",
            properties={
                "totalCarvedRaw":    self._total_carved_raw,
                "finalUniqueFiles":  self._final_unique,
                "duplicatesRemoved": self._duplicates_removed,
                "withExif":          self._with_exif,
                "withGps":           self._with_gps,
                "byFormat":          self._by_format,
                "successRate":       success_rate,
            }
        ))

        # Console summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("FILE CARVING COMPLETED", "OK", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Total carved (raw):  {self._total_carved_raw}",
                "INFO", condition=not self.args.json)
        ptprint(f"Valid after check:   {self._valid}",
                "INFO", condition=not self.args.json)
        ptprint(f"Duplicates removed:  {self._duplicates_removed}",
                "INFO", condition=not self.args.json)
        ptprint(f"Final unique files:  {self._final_unique}",
                "OK",   condition=not self.args.json)
        if success_rate is not None:
            ptprint(f"Success rate:        {success_rate}%",
                    "OK", condition=not self.args.json)
        ptprint(f"Carving time:        {self._carving_seconds/60:.1f} min",
                "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint("\nNext step: Step 13 (Photo Cataloging)",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    # -------------------------------------------------------------------------
    # REPORTING
    # -------------------------------------------------------------------------

    def save_report(self) -> Optional[str]:
        """
        Persist the JSON report and human-readable text summary.

        In --json mode: prints JSON to stdout only.
        Otherwise writes:
          - {case_id}_carving_report.json
          - {case_id}_carved/CARVING_REPORT.txt

        Returns:
            Path to JSON file, or None in --json mode
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        json_file = self.output_dir / f"{self.case_id}_carving_report.json"

        report = {
            "result":        json.loads(self.ptjsonlib.get_result_json()),
            "recoveredFiles": self._unique_files,
            "hashDatabase":   self._hash_db,
            "outputDirectories": {
                "organized":  str(self.organized_dir),
                "corrupted":  str(self.corrupted_dir),
                "quarantine": str(self.quarantine_dir),
                "duplicates": str(self.duplicates_dir),
                "metadata":   str(self.metadata_dir),
            },
        }

        with open(json_file, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False, default=str)

        ptprint(f"✓ JSON report saved: {json_file}",
                "OK", condition=not self.args.json)

        # Text summary
        txt_file = self.carving_base / "CARVING_REPORT.txt"
        self.carving_base.mkdir(parents=True, exist_ok=True)

        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        with open(txt_file, "w", encoding="utf-8") as fh:
            fh.write("=" * 70 + "\n")
            fh.write("FILE CARVING PHOTO RECOVERY REPORT\n")
            fh.write("=" * 70 + "\n\n")
            fh.write(f"Case ID:   {self.case_id}\n")
            fh.write(f"Timestamp: {props.get('timestamp','')}\n")
            fh.write(f"Method:    {props.get('method','file_carving')}\n")
            fh.write(f"Tool:      {props.get('tool','PhotoRec')}\n\n")
            fh.write("STATISTICS:\n")
            fh.write(f"  Total carved (raw):    {props.get('totalCarvedRaw',0)}\n")
            fh.write(f"  Valid after validation: {props.get('validAfterValidation',0)}\n")
            fh.write(f"  Corrupted files:        {props.get('corruptedFiles',0)}\n")
            fh.write(f"  Invalid files:          {props.get('invalidFiles',0)}\n")
            fh.write(f"  Duplicates removed:     {props.get('duplicatesRemoved',0)}\n")
            fh.write(f"  Final unique files:     {props.get('finalUniqueFiles',0)}\n")
            fh.write(f"  With EXIF:              {props.get('withExif',0)}\n")
            fh.write(f"  With GPS:               {props.get('withGps',0)}\n")
            if props.get("successRate") is not None:
                fh.write(f"  Success rate:           {props['successRate']}%\n")
            fh.write("\nTIMING:\n")
            fh.write(f"  Carving:    {props.get('carvingSeconds',0)/60:.1f} min\n")
            fh.write(f"  Validation: {props.get('validationSeconds',0)/60:.1f} min\n")
            fh.write("\nBY FORMAT:\n")
            for fmt, cnt in sorted(props.get("byFormat", {}).items()):
                fh.write(f"  {fmt.upper():8s}: {cnt}\n")
            fh.write("\n" + "=" * 70 + "\n")
            fh.write("RECOVERED FILES (first 100):\n")
            fh.write("=" * 70 + "\n\n")
            for rec in self._unique_files[:100]:
                fh.write(f"{rec['newFilename']}\n")
                fh.write(f"  Original PhotoRec: {rec['originalPhotorec']}\n")
                fh.write(f"  Path:              {rec['recoveredPath']}\n")
                fh.write(f"  Size:              {rec['sizeBytes']} bytes\n")
                if rec.get("dimensions"):
                    fh.write(f"  Dimensions:        {rec['dimensions']}\n")
                fh.write(f"  EXIF: {'Yes' if rec.get('hasExif') else 'No'}")
                if rec.get("hasGps"):
                    fh.write("  GPS: Yes")
                fh.write("\n\n")
            if len(self._unique_files) > 100:
                fh.write(f"… and {len(self._unique_files)-100} more files\n")

        ptprint(f"✓ Text report saved: {txt_file}",
                "OK", condition=not self.args.json)
        return str(json_file)


# ============================================================================
# CLI HELPERS
# ============================================================================

def get_help():
    """Return help structure for ptprinthelper.help_print."""
    return [
        {"description": [
            "Forensic file carving photo recovery tool – ptlibs compliant",
            "Recovers image files using PhotoRec byte-signature search",
            "Works without a filesystem – use for damaged/unrecognised media",
        ]},
        {"usage": ["ptfilecarving <case-id> [options]"]},
        {"usage_example": [
            "ptfilecarving PHOTO-2025-001",
            "ptfilecarving CASE-042 --json",
            "ptfilecarving TEST-001 --dry-run",
            "ptfilecarving CASE-007 --force   # override filesystem_scan recommendation",
        ]},
        {"options": [
            ["case-id",    "",              "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<dir>",  f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",              "Simulate without executing external commands"],
            ["--force",    "",              "Run even if Step 10 recommended filesystem_scan"],
            ["-j",  "--json",       "",      "JSON output for platform integration"],
            ["-q",  "--quiet",      "",      "Suppress progress output"],
            ["-h",  "--help",       "",      "Show this help message and exit"],
            ["--version",  "",              "Show version and exit"],
        ]},
        {"recovery_phases": [
            "Phase 1: Load filesystem analysis (Step 10 JSON)",
            "Phase 2: Check tools (photorec, file, identify, exiftool)",
            "Phase 3: Prepare output directories",
            "Phase 4: Run PhotoRec + collect from recup_dir.*",
            "Phase 5: Validate (file + ImageMagick) + deduplicate (SHA-256)",
            "Phase 6: Extract EXIF, organise by type, rename, save reports",
        ]},
        {"output_structure": [
            "organized/  – final renamed files by type (jpg/png/tiff/raw/other)",
            "corrupted/  – partially damaged files",
            "quarantine/ – invalid / false positives",
            "duplicates/ – SHA-256 duplicates",
            "metadata/   – per-file EXIF JSON catalogs",
        ]},
        {"limitations": [
            "Original filenames are NOT preserved (renamed to CASEID_type_NNNNNN.ext)",
            "Original directory structure is NOT preserved",
            "FS timestamps are NOT preserved (EXIF dates remain intact)",
            "Expected time: 2–8 hours for 64 GB media",
            "Expected success rate: 50–65% (vs >95% for filesystem-based recovery)",
        ]},
        {"forensic_notes": [
            "READ-ONLY: never modifies the forensic image",
            "Requires Step 10 (Filesystem Analysis) to have been run first",
            "NIST SP 800-86 Section 3.1.2.3 / ISO/IEC 27037:2012 compliant",
        ]},
    ]


def parse_args():
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Forensic file carving photo recovery"
    )

    parser.add_argument("case_id",        help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--force",        action="store_true")
    parser.add_argument("-j", "--json",   action="store_true")
    parser.add_argument("-q", "--quiet",  action="store_true")
    parser.add_argument("--version",      action='version',
                        version=f'{SCRIPTNAME} {__version__}')

    # Platform integration
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
    """Entry point."""
    global SCRIPTNAME
    SCRIPTNAME = "ptfilecarving"

    try:
        args = parse_args()
        tool = PtFileCarving(args)
        tool.run()
        tool.save_report()

        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("finalUniqueFiles", 0) > 0 else 1

    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    sys.exit(main())
