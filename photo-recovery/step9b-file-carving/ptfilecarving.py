#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptfilecarving - Forensic file carving photo recovery tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SCRIPTNAME         = "ptfilecarving"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"
PHOTOREC_TIMEOUT   = 86400   # 24 h absolute ceiling
VALIDATE_TIMEOUT   = 30      # per file (identify)
EXIF_TIMEOUT       = 30      # per file (exiftool)
HASH_CHUNK         = 65536   # 64 KB SHA-256 read chunks

# PhotoRec format keywords to enable (everything else disabled)
IMAGE_FORMATS: Dict[str, str] = {
    "jpg": "JPEG", "png": "PNG", "gif": "GIF", "bmp": "BMP",
    "tiff": "TIFF", "heic": "HEIC/HEIF", "webp": "WebP",
    "cr2": "Canon RAW", "cr3": "Canon RAW3", "nef": "Nikon RAW",
    "arw": "Sony RAW", "dng": "Adobe DNG", "orf": "Olympus RAW",
    "raf": "Fuji RAW", "rw2": "Panasonic RAW",
}

# Extension → organized sub-folder
FORMAT_DIRS: Dict[str, str] = {
    "jpg": "jpg", "jpeg": "jpg", "png": "png",
    "tif": "tiff", "tiff": "tiff",
    "cr2": "raw", "cr3": "raw", "nef": "raw", "nrw": "raw",
    "arw": "raw", "srf": "raw", "sr2": "raw", "dng": "raw",
    "orf": "raw", "raf": "raw", "rw2": "raw", "pef": "raw", "raw": "raw",
    "heic": "other", "heif": "other", "webp": "other", "gif": "other", "bmp": "other",
}

IMAGE_FILE_KEYWORDS = {"image", "jpeg", "png", "tiff", "gif", "bitmap",
                       "raw", "canon", "nikon", "exif", "riff webp", "heic"}

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtFileCarving:
    """
    Forensic file carving photo recovery – ptlibs compliant.

    Pipeline: load Step 8 JSON → check tools → PhotoRec carving →
              validate + deduplicate (SHA-256) → EXIF + organise → report.

    Filenames and directory structure are NOT preserved.
    Files are renamed to {case_id}_{type}_{seq:06d}.{ext}.

    READ-ONLY: never modifies the forensic image.
    Compliant with NIST SP 800-86 §3.1.2.3 and ISO/IEC 27037:2012.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.force      = args.force
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.image_path: Optional[Path] = None

        self.carving_base   = self.output_dir / f"{self.case_id}_carved"
        self.photorec_work  = self.carving_base / "photorec_work"
        self.organized_dir  = self.carving_base / "organized"
        self.corrupted_dir  = self.carving_base / "corrupted"
        self.quarantine_dir = self.carving_base / "quarantine"
        self.duplicates_dir = self.carving_base / "duplicates"
        self.metadata_dir   = self.carving_base / "metadata"

        # All counters in one dict
        self._s: Dict[str, Any] = {
            "carved": 0, "valid": 0, "corrupted": 0, "invalid": 0,
            "dupes": 0, "unique": 0, "exif": 0, "gps": 0,
            "by_format": {}, "carving_sec": 0.0, "validate_sec": 0.0,
        }
        self._hash_db:     Dict[str, str] = {}   # sha256 → filepath
        self._unique_files: List[Dict]    = []

        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "method": "file_carving", "tool": "PhotoRec",
            "imagePath": None,
            "totalCarvedRaw": 0, "validAfterValidation": 0,
            "corruptedFiles": 0, "invalidFiles": 0,
            "duplicatesRemoved": 0, "finalUniqueFiles": 0,
            "withExif": 0, "withGps": 0, "byFormat": {},
            "carvingSeconds": 0, "validationSeconds": 0,
            "successRate": None,
            "carvingBaseDir": str(self.carving_base),
            "dryRun": self.dry_run,
        })
        ptprint(f"Initialized: case={self.case_id}", "INFO", condition=not self.args.json)

    # --- helpers ------------------------------------------------------------

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type, properties={"success": success, **kwargs}
        ))

    def _check_command(self, cmd: str) -> bool:
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def _run_command(self, cmd: List[str], timeout: int = 300) -> Dict[str, Any]:
        if self.dry_run:
            ptprint(f"[DRY-RUN] {' '.join(str(c) for c in cmd)}",
                    "INFO", condition=not self.args.json)
            return {"success": True, "stdout": "[DRY-RUN]", "stderr": "", "returncode": 0}
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, check=False)
            return {"success": proc.returncode == 0, "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(), "returncode": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": f"Timeout after {timeout}s", "returncode": -1}
        except Exception as exc:
            return {"success": False, "stdout": "", "stderr": str(exc), "returncode": -1}

    def _run_streaming(self, cmd: List[str], timeout: int) -> bool:
        """Run a long-running command with real-time stdout (for PhotoRec)."""
        if self.dry_run:
            ptprint(f"[DRY-RUN] {' '.join(str(c) for c in cmd)}",
                    "INFO", condition=not self.args.json)
            return True
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in proc.stdout:
                if not self.args.json:
                    print(line, end="", flush=True)
            proc.wait(timeout=timeout)
            return proc.returncode == 0
        except Exception as exc:
            ptprint(f"PhotoRec error: {exc}", "ERROR", condition=not self.args.json)
            return False

    def _fail(self, node_type: str, msg: str) -> bool:
        ptprint(msg, "ERROR", condition=not self.args.json)
        self._add_node(node_type, False, error=msg)
        return False

    def _sha256(self, filepath: Path) -> Optional[str]:
        h = hashlib.sha256()
        try:
            with open(filepath, "rb") as fh:
                for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    # --- phases -------------------------------------------------------------

    def load_fs_analysis(self) -> bool:
        """Load Step 8 filesystem analysis JSON and extract image path."""
        ptprint("\n[1/3] Loading Filesystem Analysis (Step 8)",
                "TITLE", condition=not self.args.json)

        f = self.output_dir / f"{self.case_id}_filesystem_analysis.json"
        if not f.exists():
            return self._fail("fsAnalysisLoad", f"{f.name} not found – run Step 8 first.")
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            return self._fail("fsAnalysisLoad", f"Cannot read analysis file: {exc}")

        if "result" in raw and "properties" in raw["result"]:
            p = raw["result"]["properties"]
            recommended, image_path_s = p.get("recommendedMethod"), p.get("imagePath")
        else:
            recommended  = raw.get("recommended_method") or raw.get("recommendedMethod")
            image_path_s = raw.get("image_file") or raw.get("imagePath")

        if recommended == "filesystem_scan" and not self.force:
            return self._fail("fsAnalysisLoad",
                              "Step 8 recommended filesystem_scan – use Step 9 or --force.")
        if recommended == "hybrid":
            ptprint("Hybrid recommended – file carving will complement Step 9.",
                    "WARNING", condition=not self.args.json)
        if not image_path_s:
            return self._fail("fsAnalysisLoad", "imagePath missing in analysis file.")

        self.image_path = Path(image_path_s)
        if not self.image_path.exists() and not self.dry_run:
            return self._fail("fsAnalysisLoad",
                              f"Forensic image not found: {self.image_path}")

        ptprint(f"Loaded: method={recommended} | image={self.image_path.name}",
                "OK", condition=not self.args.json)
        self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})
        self._add_node("fsAnalysisLoad", True, recommendedMethod=recommended,
                       imagePath=str(self.image_path))
        return True

    def check_tools(self) -> bool:
        """Verify photorec, file, identify, exiftool are installed."""
        ptprint("\n[2/3] Checking Required Tools", "TITLE", condition=not self.args.json)

        tools = {"photorec": "PhotoRec file carving", "file": "file type detection",
                 "identify": "ImageMagick validation", "exiftool": "EXIF extraction"}
        missing = []
        for t, desc in tools.items():
            found = self._check_command(t)
            ptprint(f"  {'✓' if found else '✗'} {t}: {desc}",
                    "OK" if found else "ERROR", condition=not self.args.json)
            if not found:
                missing.append(t)

        if missing:
            ptprint(f"Missing: {', '.join(missing)} – "
                    "sudo apt-get install testdisk imagemagick libimage-exiftool-perl",
                    "ERROR", condition=not self.args.json)
            self._add_node("toolsCheck", False, missingTools=missing)
            return False

        self._add_node("toolsCheck", True, toolsChecked=list(tools.keys()))
        return True

    def run_photorec(self) -> bool:
        """Phase: run PhotoRec with image-only config, stream progress."""
        ptprint("\n[3/3] Running PhotoRec File Carving", "TITLE", condition=not self.args.json)
        ptprint("  ⚠ This may take 2–8 hours – do not interrupt.",
                "WARNING", condition=not self.args.json)

        # Write batch config
        cmd_file = self.photorec_work / "photorec.cmd"
        if not self.dry_run:
            lines = ["fileopt,everything,disable"]
            lines += [f"fileopt,{fmt},enable" for fmt in IMAGE_FORMATS]
            lines += ["options,paranoid,enable", "options,expert,enable", "search"]
            cmd_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ptprint(f"  Config: {len(IMAGE_FORMATS)} formats enabled.",
                "INFO", condition=not self.args.json)

        cmd = ["photorec", "/log", "/d", str(self.photorec_work),
               "/cmd", str(self.image_path), "search"]
        ptprint(f"  Command: {' '.join(cmd)}", "INFO", condition=not self.args.json)

        start = datetime.now()
        ok = self._run_streaming(cmd, timeout=PHOTOREC_TIMEOUT)
        self._s["carving_sec"] = (datetime.now() - start).total_seconds()

        ptprint(f"{'PhotoRec completed' if ok else 'PhotoRec failed'} "
                f"in {self._s['carving_sec']/60:.1f} min",
                "OK" if ok else "ERROR", condition=not self.args.json)
        self._add_node("photorec", ok, carvingSeconds=round(self._s["carving_sec"], 1),
                       command=" ".join(cmd))
        return ok

    def collect_carved_files(self) -> List[Path]:
        """Collect all files from PhotoRec recup_dir.* output folders."""
        recup_dirs = sorted(self.photorec_work.glob("recup_dir.*"))
        if not recup_dirs and not self.dry_run:
            ptprint("No recup_dir folders found.", "ERROR", condition=not self.args.json)
            return []
        files = [f for rd in recup_dirs for f in rd.glob("f*.*")]
        self._s["carved"] = len(files)
        ptprint(f"  {len(recup_dirs)} recup_dir(s) | {len(files)} raw carved files.",
                "OK", condition=not self.args.json)
        return files

    def validate_and_deduplicate(self, carved_files: List[Path]) -> List[Dict]:
        """Validate each file (size → file → identify) and remove SHA-256 duplicates."""
        ptprint("\nValidating and deduplicating …", "TITLE", condition=not self.args.json)

        total = len(carved_files)
        valid_files: List[Dict] = []
        start = datetime.now()

        for idx, fp in enumerate(carved_files, 1):
            if idx % 100 == 0 or idx == total:
                ptprint(f"  {idx}/{total} ({idx*100//total}%)",
                        "INFO", condition=not self.args.json)

            status, vinfo = self._validate_file(fp)

            if status == "valid":
                digest = self._sha256(fp)
                if digest:
                    if digest in self._hash_db:
                        if not self.dry_run:
                            shutil.move(str(fp), str(self.duplicates_dir / fp.name))
                        self._s["dupes"] += 1
                    else:
                        self._hash_db[digest] = str(fp)
                        ext = fp.suffix.lstrip(".").lower()
                        self._s["by_format"][ext] = self._s["by_format"].get(ext, 0) + 1
                        self._s["valid"] += 1
                        valid_files.append({"path": fp, "hash": digest,
                                            "size": vinfo["size"],
                                            "format": vinfo.get("format"),
                                            "dimensions": vinfo.get("dimensions")})
            elif status == "corrupted":
                self._s["corrupted"] += 1
                if not self.dry_run:
                    shutil.move(str(fp), str(self.corrupted_dir / fp.name))
            else:
                self._s["invalid"] += 1
                if not self.dry_run:
                    shutil.move(str(fp), str(self.quarantine_dir / fp.name))

        self._s["validate_sec"] = (datetime.now() - start).total_seconds()
        self._s["unique"] = len(valid_files)

        ptprint(f"Validation done in {self._s['validate_sec']:.0f}s | "
                f"unique={self._s['unique']} | dupes={self._s['dupes']} | "
                f"corrupted={self._s['corrupted']} | invalid={self._s['invalid']}",
                "OK", condition=not self.args.json)
        self._add_node("validationDedup", True,
                       totalCarvedRaw=self._s["carved"], validUnique=self._s["unique"],
                       duplicatesRemoved=self._s["dupes"], corrupted=self._s["corrupted"],
                       invalid=self._s["invalid"],
                       validationSeconds=round(self._s["validate_sec"], 1))
        return valid_files

    def _validate_file(self, filepath: Path) -> Tuple[str, Dict]:
        """Three-stage validation: size → file → identify. Returns (status, info)."""
        info: Dict = {"size": 0, "format": None, "dimensions": None}
        try:
            info["size"] = filepath.stat().st_size
        except Exception:
            return "invalid", info

        if info["size"] < 100:
            return "invalid", info

        r = self._run_command(["file", "-b", str(filepath)], timeout=10)
        if r["success"] and not any(kw in r["stdout"].lower() for kw in IMAGE_FILE_KEYWORDS):
            return "invalid", info

        r = self._run_command(["identify", str(filepath)], timeout=VALIDATE_TIMEOUT)
        if r["success"]:
            m = re.search(r"(\w+)\s+(\d+)x(\d+)", r["stdout"])
            if m:
                info["format"] = m.group(1)
                info["dimensions"] = f"{m.group(2)}x{m.group(3)}"
            return "valid", info

        return ("corrupted" if info["size"] > 10240 else "invalid"), info

    def _extract_exif(self, filepath: Path) -> Optional[Dict]:
        """Extract EXIF via exiftool. Updates exif/gps counters."""
        r = self._run_command(["exiftool", "-json", "-charset", "utf8", str(filepath)],
                              timeout=EXIF_TIMEOUT)
        if not r["success"]:
            return None
        try:
            data = json.loads(r["stdout"])
            if data:
                exif = data[0]
                if {"DateTimeOriginal", "CreateDate", "GPSLatitude",
                    "Make", "Model"} & set(exif):
                    self._s["exif"] += 1
                    if "GPSLatitude" in exif:
                        self._s["gps"] += 1
                    return exif
        except Exception:
            pass
        return None

    def organise_and_rename(self, valid_files: List[Dict]) -> None:
        """Move files to organized/{type}/, rename to {case_id}_{type}_{seq:06d}.{ext}."""
        ptprint("\nOrganising and renaming files …", "TITLE", condition=not self.args.json)

        format_counters: Dict[str, int] = defaultdict(int)

        for fi in valid_files:
            fp      = fi["path"]
            ext     = fp.suffix.lstrip(".").lower()
            subdir  = FORMAT_DIRS.get(ext, "other")
            format_counters[subdir] += 1
            seq     = format_counters[subdir]
            new_name = f"{self.case_id}_{subdir}_{seq:06d}.{ext}"
            new_path = self.organized_dir / subdir / new_name

            if not self.dry_run:
                shutil.move(str(fp), str(new_path))

            exif_data = self._extract_exif(new_path if not self.dry_run else fp)
            if exif_data and not self.dry_run:
                (self.metadata_dir / f"{new_name}_metadata.json").write_text(
                    json.dumps(exif_data, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8"
                )

            self._unique_files.append({
                "newFilename":      new_name,
                "originalPhotorec": fp.name,
                "recoveredPath":    str((self.organized_dir / subdir / new_name)
                                       .relative_to(self.carving_base)),
                "hash":             fi["hash"],
                "sizeBytes":        fi["size"],
                "formatGroup":      subdir,
                "dimensions":       fi.get("dimensions"),
                "hasExif":          exif_data is not None,
                "hasGps":           bool(exif_data and exif_data.get("GPSLatitude")),
            })

        ptprint(f"{len(self._unique_files)} files organised.", "OK", condition=not self.args.json)

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full carving pipeline."""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FILE CARVING PHOTO RECOVERY v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_fs_analysis():
            self.ptjsonlib.set_status("finished"); return
        if not self.check_tools():
            self.ptjsonlib.set_status("finished"); return

        # Create directory tree inline
        for path in (self.photorec_work, self.organized_dir, self.corrupted_dir,
                     self.quarantine_dir, self.duplicates_dir, self.metadata_dir):
            if not self.dry_run:
                path.mkdir(parents=True, exist_ok=True)
        for sub in ("jpg", "png", "tiff", "raw", "other"):
            if not self.dry_run:
                (self.organized_dir / sub).mkdir(exist_ok=True)

        if not self.run_photorec():
            self.ptjsonlib.set_status("finished"); return

        carved = self.collect_carved_files()
        if not carved and not self.dry_run:
            ptprint("No carved files found.", "ERROR", condition=not self.args.json)
            self.ptjsonlib.set_status("finished"); return

        valid_files = self.validate_and_deduplicate(carved)
        if not valid_files and not self.dry_run:
            ptprint("No valid files after validation.", "ERROR", condition=not self.args.json)
            self.ptjsonlib.set_status("finished"); return

        self.organise_and_rename(valid_files)

        s = self._s
        success_rate = (round(s["unique"] / s["carved"] * 100, 1) if s["carved"] else None)

        self.ptjsonlib.add_properties({
            "totalCarvedRaw": s["carved"], "validAfterValidation": s["valid"],
            "corruptedFiles": s["corrupted"], "invalidFiles": s["invalid"],
            "duplicatesRemoved": s["dupes"], "finalUniqueFiles": s["unique"],
            "withExif": s["exif"], "withGps": s["gps"], "byFormat": s["by_format"],
            "carvingSeconds": round(s["carving_sec"], 1),
            "validationSeconds": round(s["validate_sec"], 1),
            "successRate": success_rate,
        })
        self._add_node("carvingSummary", True,
                       totalCarvedRaw=s["carved"], finalUniqueFiles=s["unique"],
                       duplicatesRemoved=s["dupes"], withExif=s["exif"],
                       withGps=s["gps"], byFormat=s["by_format"], successRate=success_rate)

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("FILE CARVING COMPLETED", "OK", condition=not self.args.json)
        ptprint(f"Carved: {s['carved']} | Valid: {s['valid']} | Dupes: {s['dupes']} | "
                f"Unique: {s['unique']}" + (f" | Rate: {success_rate}%" if success_rate else ""),
                "INFO", condition=not self.args.json)
        ptprint(f"Carving time: {s['carving_sec']/60:.1f} min",
                "INFO", condition=not self.args.json)
        ptprint("Next: Step 11 – Photo Cataloging", "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        self.ptjsonlib.set_status("finished")

    def _write_text_report(self, props: Dict) -> Path:
        """Write CARVING_REPORT.txt to carving_base."""
        txt = self.carving_base / "CARVING_REPORT.txt"
        self.carving_base.mkdir(parents=True, exist_ok=True)
        sep = "=" * 70
        lines = [sep, "FILE CARVING PHOTO RECOVERY REPORT", sep, "",
                 f"Case ID:   {self.case_id}",
                 f"Timestamp: {props.get('timestamp','')}",
                 f"Method:    {props.get('method','file_carving')}",
                 f"Tool:      {props.get('tool','PhotoRec')}", "",
                 "STATISTICS:",
                 f"  Total carved (raw):    {props.get('totalCarvedRaw',0)}",
                 f"  Valid after validation: {props.get('validAfterValidation',0)}",
                 f"  Duplicates removed:    {props.get('duplicatesRemoved',0)}",
                 f"  Final unique files:    {props.get('finalUniqueFiles',0)}",
                 f"  Corrupted:             {props.get('corruptedFiles',0)}",
                 f"  With EXIF:             {props.get('withExif',0)}",
                 f"  With GPS:              {props.get('withGps',0)}",
                 *([] if props.get("successRate") is None
                   else [f"  Success rate:          {props['successRate']}%"]),
                 "", "TIMING:",
                 f"  Carving:    {props.get('carvingSeconds',0)/60:.1f} min",
                 f"  Validation: {props.get('validationSeconds',0)/60:.1f} min",
                 "", "BY FORMAT:"]
        lines += [f"  {k.upper():8s}: {v}" for k, v in sorted(props.get("byFormat", {}).items())]
        lines += ["", sep, f"RECOVERED FILES (first 100 of {len(self._unique_files)}):", sep, ""]
        for rec in self._unique_files[:100]:
            dim = f" | {rec['dimensions']}" if rec.get("dimensions") else ""
            gps = " | GPS: Yes" if rec.get("hasGps") else ""
            lines += [rec["newFilename"],
                      f"  {rec['recoveredPath']}  |  {rec['sizeBytes']} B{dim}",
                      f"  EXIF: {'Yes' if rec.get('hasExif') else 'No'}{gps}", ""]
        if len(self._unique_files) > 100:
            lines.append(f"… and {len(self._unique_files) - 100} more files")
        txt.write_text("\n".join(lines), encoding="utf-8")
        return txt

    def save_report(self) -> Optional[str]:
        """Save JSON report and CARVING_REPORT.txt."""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        json_file = self.output_dir / f"{self.case_id}_carving_report.json"
        report = {
            "result": json.loads(self.ptjsonlib.get_result_json()),
            "recoveredFiles": self._unique_files,
            "hashDatabase": self._hash_db,
            "outputDirectories": {
                "organized":  str(self.organized_dir),
                "corrupted":  str(self.corrupted_dir),
                "quarantine": str(self.quarantine_dir),
                "duplicates": str(self.duplicates_dir),
                "metadata":   str(self.metadata_dir),
            },
        }
        json_file.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                             encoding="utf-8")
        ptprint(f"JSON report: {json_file}", "OK", condition=not self.args.json)

        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        txt = self._write_text_report(props)
        ptprint(f"Text report: {txt}", "OK", condition=not self.args.json)
        return str(json_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_help() -> List[Dict]:
    return [
        {"description": [
            "Forensic file carving photo recovery – ptlibs compliant",
            "Recovers images via PhotoRec byte-signature search (no filesystem needed)",
        ]},
        {"usage": ["ptfilecarving <case-id> [options]"]},
        {"usage_example": [
            "ptfilecarving PHOTO-2025-001",
            "ptfilecarving CASE-042 --json",
            "ptfilecarving TEST-001 --dry-run",
            "ptfilecarving CASE-007 --force",
        ]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate without running PhotoRec"],
            ["--force",            "",      "Override filesystem_scan recommendation from Step 8"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"notes": [
            "Pipeline: Step 8 JSON → tools → PhotoRec → validate+dedup → EXIF+organise → report",
            "Output:   organized/ | corrupted/ | quarantine/ | duplicates/ | metadata/",
            "Filenames NOT preserved – renamed to {case_id}_{type}_{seq:06d}.{ext}",
            "Expected time: 2–8 h per 64 GB | Success rate: 50–65 %",
            "READ-ONLY: never modifies the forensic image",
            "Compliant with NIST SP 800-86 §3.1.2.3 and ISO/IEC 27037:2012",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-v", "--verbose",    action="store_true")
    parser.add_argument("-q", "--quiet",      action="store_true")
    parser.add_argument("--dry-run",          action="store_true")
    parser.add_argument("--force",            action="store_true")
    parser.add_argument("-j", "--json",       action="store_true")
    parser.add_argument("--version", action="version", version=f"{SCRIPTNAME} {__version__}")
    parser.add_argument("--socket-address",   default=None)
    parser.add_argument("--socket-port",      default=None)
    parser.add_argument("--process-ident",    default=None)

    if len(sys.argv) == 1 or {"-h", "--help"} & set(sys.argv):
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    if args.json:
        args.quiet = True
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main() -> int:
    try:
        args = parse_args()
        tool = PtFileCarving(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("finalUniqueFiles", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())