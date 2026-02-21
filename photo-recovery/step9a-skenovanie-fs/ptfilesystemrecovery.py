#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptfilesystemrecovery - Forensic filesystem-based photo recovery tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SCRIPTNAME         = "ptfilesystemrecovery"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"
FLS_TIMEOUT        = 1800   # 30 min for large media
ICAT_TIMEOUT       = 60     # per file
EXIF_TIMEOUT       = 30     # per file

IMAGE_EXTENSIONS: set = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif",
    ".heic", ".heif", ".webp",
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".dng", ".orf", ".raf", ".rw2", ".pef", ".raw",
}

FORMAT_GROUPS: Dict[str, List[str]] = {
    "jpeg": [".jpg", ".jpeg"],
    "png":  [".png"],
    "tiff": [".tif", ".tiff"],
    "bmp":  [".bmp"],
    "gif":  [".gif"],
    "heic": [".heic", ".heif"],
    "webp": [".webp"],
    "raw":  [".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
             ".dng", ".orf", ".raf", ".rw2", ".pef", ".raw"],
}

IMAGE_FILE_KEYWORDS = {"image", "jpeg", "png", "tiff", "gif", "bitmap",
                       "raw", "canon", "nikon", "exif", "riff webp"}

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtFilesystemRecovery:
    """
    Forensic filesystem-based photo recovery – ptlibs compliant.

    Pipeline: load Step 8 JSON → check tools → scan (fls) →
              extract (icat) + validate + EXIF → report.

    READ-ONLY: never modifies the forensic image.
    Compliant with ISO/IEC 27037:2012 and NIST SP 800-86.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.force      = args.force
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.image_path:  Optional[Path] = None
        self.fs_analysis: Optional[Dict] = None

        self.recovery_base = self.output_dir / f"{self.case_id}_recovered"
        self.active_dir    = self.recovery_base / "active"
        self.deleted_dir   = self.recovery_base / "deleted"
        self.corrupted_dir = self.recovery_base / "corrupted"
        self.metadata_dir  = self.recovery_base / "metadata"

        # All counters in one dict – avoids 8 separate attributes
        self._s: Dict[str, Any] = {
            "scanned": 0, "active": 0, "deleted": 0,
            "extracted": 0, "valid": 0, "corrupted": 0, "invalid": 0,
            "exif": 0, "by_format": {},
        }
        self._recovered_files: List[Dict] = []

        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "method": "filesystem_scan",
            "imagePath": None,
            "partitionsProcessed": 0,
            "totalFilesScanned": 0, "imageFilesFound": 0,
            "activeImages": 0, "deletedImages": 0,
            "imagesExtracted": 0, "validImages": 0,
            "corruptedImages": 0, "invalidImages": 0,
            "withExif": 0, "byFormat": {}, "successRate": None,
            "recoveryBaseDir": str(self.recovery_base),
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

    def _run_command(self, cmd: List[str], timeout: int = 300,
                     binary: bool = False) -> Dict[str, Any]:
        if self.dry_run:
            ptprint(f"[DRY-RUN] {' '.join(str(c) for c in cmd)}",
                    "INFO", condition=not self.args.json)
            return {"success": True, "stdout": b"" if binary else "", "stderr": "", "returncode": 0}
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
            stdout = proc.stdout if binary else proc.stdout.decode(errors="replace").strip()
            return {"success": proc.returncode == 0, "stdout": stdout,
                    "stderr": proc.stderr.decode(errors="replace").strip(),
                    "returncode": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": b"" if binary else "",
                    "stderr": f"Timeout after {timeout}s", "returncode": -1}
        except Exception as exc:
            return {"success": False, "stdout": b"" if binary else "",
                    "stderr": str(exc), "returncode": -1}

    def _format_group(self, ext: str) -> str:
        ext = ext.lower()
        for group, exts in FORMAT_GROUPS.items():
            if ext in exts:
                return group
        return ext.lstrip(".")

    def _fail(self, node_type: str, msg: str) -> bool:
        """Log error, add failure node, return False – reduces 3-line repetition."""
        ptprint(msg, "ERROR", condition=not self.args.json)
        self._add_node(node_type, False, error=msg)
        return False

    # --- phases -------------------------------------------------------------

    def load_fs_analysis(self) -> bool:
        """Load filesystem analysis JSON produced by Step 8 (ptfilesystemanalysis)."""
        ptprint("\n[1/3] Loading Filesystem Analysis (Step 8)",
                "TITLE", condition=not self.args.json)

        f = self.output_dir / f"{self.case_id}_filesystem_analysis.json"
        if not f.exists():
            return self._fail("fsAnalysisLoad", f"{f.name} not found – run Step 8 first.")
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            return self._fail("fsAnalysisLoad", f"Cannot read analysis file: {exc}")

        # Normalise ptlibs JSON structure to flat dict
        if "result" in raw and "properties" in raw["result"]:
            p = raw["result"]["properties"]
            partitions: List[Dict] = next(
                (n.get("properties", {}).get("partitions", [])
                 for n in raw["result"].get("nodes", [])
                 if n.get("type") == "partitionAnalysis"),
                []
            )
            self.fs_analysis = {"recommended_method": p.get("recommendedMethod"),
                                "image_file": p.get("imagePath"), "partitions": partitions}
        else:
            self.fs_analysis = raw

        recommended  = self.fs_analysis.get("recommended_method") or self.fs_analysis.get("recommendedMethod")
        image_path_s = self.fs_analysis.get("image_file") or self.fs_analysis.get("imagePath")

        if not image_path_s:
            return self._fail("fsAnalysisLoad", "imagePath missing in analysis file.")

        self.image_path = Path(image_path_s)
        if not self.image_path.exists() and not self.dry_run:
            return self._fail("fsAnalysisLoad", f"Forensic image not found: {self.image_path}")

        if recommended == "file_carving" and not self.force:
            return self._fail("fsAnalysisLoad",
                              "Step 8 recommended file_carving – use Step 10B or --force.")

        if recommended == "hybrid":
            ptprint("Hybrid recommended – will scan FS; also run Step 10B afterwards.",
                    "WARNING", condition=not self.args.json)

        partitions = self.fs_analysis.get("partitions", [])
        ptprint(f"Loaded: method={recommended} | partitions={len(partitions)} | "
                f"image={self.image_path.name}", "OK", condition=not self.args.json)
        self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})
        self._add_node("fsAnalysisLoad", True, recommendedMethod=recommended,
                       imagePath=str(self.image_path), partitionsFound=len(partitions))
        return True

    def check_tools(self) -> bool:
        """Verify fls, icat, file, identify, exiftool are installed."""
        ptprint("\n[2/3] Checking Required Tools", "TITLE", condition=not self.args.json)

        tools = {"fls": "TSK file listing", "icat": "TSK inode extraction",
                 "file": "file type detection", "identify": "ImageMagick validation",
                 "exiftool": "EXIF extraction"}
        missing = []
        for t, desc in tools.items():
            found = self._check_command(t)
            ptprint(f"  {'✓' if found else '✗'} {t}: {desc}",
                    "OK" if found else "ERROR", condition=not self.args.json)
            if not found:
                missing.append(t)

        if missing:
            ptprint(f"Missing: {', '.join(missing)} – "
                    "sudo apt-get install sleuthkit imagemagick libimage-exiftool-perl",
                    "ERROR", condition=not self.args.json)
            self._add_node("toolsCheck", False, missingTools=missing)
            return False

        self._add_node("toolsCheck", True, toolsChecked=list(tools.keys()))
        return True

    def scan_and_filter(self, partition: Dict) -> Tuple[List[Dict], List[Dict]]:
        """
        Run fls on one partition and return (active_images, deleted_images).
        Merges scan + filter into one pass – avoids storing the full entries list.
        """
        offset   = partition.get("offset", 0)
        part_num = partition.get("number", 0)
        ptprint(f"  [fls] partition {part_num} (offset={offset}) …",
                "INFO", condition=not self.args.json)

        r = self._run_command(["fls", "-r", "-d", "-p", "-o", str(offset),
                               str(self.image_path)], timeout=FLS_TIMEOUT)
        if not r["success"]:
            ptprint(f"  fls failed: {r['stderr']}", "ERROR", condition=not self.args.json)
            return [], []

        active, deleted = [], []
        for line in r["stdout"].splitlines():
            line = line.strip()
            if not line or line.startswith("d/d"):
                continue
            self._s["scanned"] += 1

            inode_m = re.search(r"(\d+):", line)
            path_m  = re.search(r":\s+(.+)$", line)
            if not inode_m or not path_m:
                continue

            filepath   = path_m.group(1).strip()
            ext        = Path(filepath).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue

            is_deleted = "*" in line.split(":")[0]
            group = self._format_group(ext)
            self._s["by_format"][group] = self._s["by_format"].get(group, 0) + 1

            entry = {"inode": int(inode_m.group(1)), "path": filepath,
                     "filename": Path(filepath).name, "deleted": is_deleted}
            if is_deleted:
                deleted.append(entry); self._s["deleted"] += 1
            else:
                active.append(entry);  self._s["active"]  += 1

        ptprint(f"  Images: {len(active) + len(deleted)} "
                f"(active={len(active)}, deleted={len(deleted)})",
                "OK", condition=not self.args.json)
        return active, deleted

    def _extract_single(self, entry: Dict, offset: int, out_base: Path) -> Optional[Path]:
        """Extract one file via icat, preserving directory structure."""
        dest = out_base / entry["path"].lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["icat", "-o", str(offset), str(self.image_path), str(entry["inode"])]

        if self.dry_run:
            self._run_command(cmd)
            return dest
        try:
            with open(dest, "wb") as fh:
                proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE,
                                      timeout=ICAT_TIMEOUT, check=False)
            if proc.returncode == 0:
                return dest
            ptprint(f"    icat {entry['inode']}: "
                    f"{proc.stderr.decode(errors='replace').strip()}",
                    "WARNING", condition=not self.args.json)
        except Exception as exc:
            ptprint(f"    icat {entry['inode']}: {exc}",
                    "WARNING", condition=not self.args.json)
        if dest.exists():
            dest.unlink()
        return None

    def _validate_image(self, filepath: Path) -> Tuple[str, Dict]:
        """
        Three-stage validation: size → file command → identify.
        Returns (status, info).  status ∈ {valid, corrupted, invalid}
        """
        info: Dict = {"size": 0, "imageFormat": None, "dimensions": None}
        try:
            info["size"] = filepath.stat().st_size
        except Exception as exc:
            return "invalid", {**info, "error": str(exc)}

        if info["size"] == 0:
            return "invalid", info

        r = self._run_command(["file", "-b", str(filepath)], timeout=10)
        if r["success"] and not any(kw in r["stdout"].lower() for kw in IMAGE_FILE_KEYWORDS):
            return "invalid", info

        r = self._run_command(["identify", str(filepath)], timeout=30)
        if r["success"]:
            m = re.search(r"(\w+)\s+(\d+)x(\d+)", r["stdout"])
            if m:
                info["imageFormat"] = m.group(1)
                info["dimensions"]  = f"{m.group(2)}x{m.group(3)}"
            return "valid", info

        return ("corrupted" if info["size"] > 1024 else "invalid"), info

    def _extract_metadata(self, filepath: Path, entry: Dict) -> Dict:
        """Extract FS timestamps and EXIF for one recovered file."""
        meta: Dict = {"filename": filepath.name, "originalPath": entry["path"],
                      "inode": entry["inode"], "deleted": entry["deleted"],
                      "fsMetadata": {}, "exifMetadata": {}, "hasExif": False}
        try:
            st = filepath.stat()
            meta["fsMetadata"] = {
                "sizeBytes":    st.st_size,
                "modifiedTime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "accessedTime": datetime.fromtimestamp(st.st_atime, tz=timezone.utc).isoformat(),
                "createdTime":  datetime.fromtimestamp(st.st_ctime, tz=timezone.utc).isoformat(),
            }
        except Exception as exc:
            meta["fsMetadata"]["error"] = str(exc)

        r = self._run_command(["exiftool", "-json", "-charset", "utf8", str(filepath)],
                              timeout=EXIF_TIMEOUT)
        if r["success"]:
            try:
                data = json.loads(r["stdout"])
                if data:
                    meta["exifMetadata"] = data[0]
                    if {"DateTimeOriginal", "CreateDate", "GPSLatitude", "Make", "Model"} & set(data[0]):
                        meta["hasExif"] = True
                        self._s["exif"] += 1
            except Exception as exc:
                meta["exifMetadata"] = {"parseError": str(exc)}
        return meta

    def process_partition(self, partition: Dict) -> None:
        """Scan → extract → validate → metadata pipeline for one partition."""
        part_num = partition.get("number", 0)
        offset   = partition.get("offset", 0)
        ptprint(f"\n  Partition {part_num} (offset={offset})",
                "TITLE", condition=not self.args.json)

        active_imgs, deleted_imgs = self.scan_and_filter(partition)
        all_targets = ([(e, self.active_dir,  "active")  for e in active_imgs] +
                       [(e, self.deleted_dir, "deleted") for e in deleted_imgs])
        if not all_targets:
            ptprint("  No image files found.", "WARNING", condition=not self.args.json)
            return

        total = len(all_targets)
        ptprint(f"  Extracting {total} image files …", "INFO", condition=not self.args.json)
        self._add_node("partitionRecovery", True, partitionNumber=part_num,
                       offset=offset, totalImages=total)

        for idx, (entry, out_base, label) in enumerate(all_targets, 1):
            if idx % 50 == 0 or idx == total:
                ptprint(f"    {idx}/{total} ({idx*100//total}%)",
                        "INFO", condition=not self.args.json)

            extracted = self._extract_single(entry, offset, out_base)
            if extracted is None:
                self._s["invalid"] += 1; continue
            self._s["extracted"] += 1

            status, vinfo = self._validate_image(extracted)

            if status == "valid":
                self._s["valid"] += 1
                meta = self._extract_metadata(extracted, entry)
                if not self.dry_run:
                    (self.metadata_dir / f"{extracted.name}_metadata.json").write_text(
                        json.dumps(meta, indent=2, ensure_ascii=False, default=str), "utf-8")
                self._recovered_files.append({
                    "filename":      extracted.name,
                    "originalPath":  entry["path"],
                    "recoveredPath": str(extracted.relative_to(self.recovery_base)),
                    "inode":         entry["inode"],
                    "status":        label,
                    "sizeBytes":     vinfo["size"],
                    "format":        vinfo.get("imageFormat"),
                    "dimensions":    vinfo.get("dimensions"),
                    "hasExif":       meta.get("hasExif", False),
                })
            elif status == "corrupted":
                self._s["corrupted"] += 1
                if not self.dry_run:
                    shutil.move(str(extracted), str(self.corrupted_dir / extracted.name))
            else:
                self._s["invalid"] += 1
                if not self.dry_run and extracted.exists():
                    extracted.unlink()

        ptprint(f"  Partition {part_num} done.", "OK", condition=not self.args.json)

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full recovery pipeline."""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FILESYSTEM-BASED PHOTO RECOVERY v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_fs_analysis():
            self.ptjsonlib.set_status("finished"); return
        if not self.check_tools():
            self.ptjsonlib.set_status("finished"); return

        # Create output directories inline – no need for a separate phase
        for path in (self.active_dir, self.deleted_dir, self.corrupted_dir, self.metadata_dir):
            if not self.dry_run:
                path.mkdir(parents=True, exist_ok=True)
        ptprint("[3/3] Output directories ready.", "OK", condition=not self.args.json)

        partitions = self.fs_analysis.get("partitions", [])
        for partition in partitions:
            self.process_partition(partition)

        s = self._s
        total_images = s["active"] + s["deleted"]
        success_rate = round(s["valid"] / s["extracted"] * 100, 1) if s["extracted"] else None

        self.ptjsonlib.add_properties({
            "partitionsProcessed": len(partitions),
            "totalFilesScanned":   s["scanned"],
            "imageFilesFound":     total_images,
            "activeImages":        s["active"],
            "deletedImages":       s["deleted"],
            "imagesExtracted":     s["extracted"],
            "validImages":         s["valid"],
            "corruptedImages":     s["corrupted"],
            "invalidImages":       s["invalid"],
            "withExif":            s["exif"],
            "byFormat":            s["by_format"],
            "successRate":         success_rate,
        })
        self._add_node("recoverySummary", True,
                       imageFilesFound=total_images, imagesExtracted=s["extracted"],
                       validImages=s["valid"], corruptedImages=s["corrupted"],
                       withExif=s["exif"], byFormat=s["by_format"], successRate=success_rate)

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("RECOVERY COMPLETED", "OK", condition=not self.args.json)
        ptprint(f"Images: {total_images} (active={s['active']}, deleted={s['deleted']}) | "
                f"Valid: {s['valid']} | Corrupted: {s['corrupted']} | Invalid: {s['invalid']}",
                "INFO", condition=not self.args.json)
        if success_rate is not None:
            ptprint(f"Success rate: {success_rate}%", "OK", condition=not self.args.json)
        ptprint("Next: Step 11 – Photo Cataloging", "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        self.ptjsonlib.set_status("finished")

    def _write_text_report(self, props: Dict) -> Path:
        """Write RECOVERY_REPORT.txt to recovery_base."""
        txt = self.recovery_base / "RECOVERY_REPORT.txt"
        self.recovery_base.mkdir(parents=True, exist_ok=True)
        sep = "=" * 70
        lines = [sep, "FILESYSTEM-BASED PHOTO RECOVERY REPORT", sep, "",
                 f"Case ID:   {self.case_id}",
                 f"Timestamp: {props.get('timestamp','')}",
                 f"Method:    {props.get('method','filesystem_scan')}", "",
                 "STATISTICS:",
                 f"  Images found:   {props.get('imageFilesFound',0)} "
                 f"(active={props.get('activeImages',0)}, deleted={props.get('deletedImages',0)})",
                 f"  Extracted:      {props.get('imagesExtracted',0)}",
                 f"  Valid:          {props.get('validImages',0)}",
                 f"  Corrupted:      {props.get('corruptedImages',0)}",
                 f"  With EXIF:      {props.get('withExif',0)}",
                 *([] if props.get("successRate") is None
                   else [f"  Success rate:   {props['successRate']}%"]),
                 "", "BY FORMAT:"]
        lines += [f"  {k.upper():8s}: {v}" for k, v in sorted(props.get("byFormat", {}).items())]
        lines += ["", sep, f"RECOVERED FILES (first 100 of {len(self._recovered_files)}):", sep, ""]
        for rec in self._recovered_files[:100]:
            dim = f" | {rec['dimensions']}" if rec.get("dimensions") else ""
            lines += [rec["filename"],
                      f"  {rec['originalPath']}  →  {rec['recoveredPath']}",
                      f"  {rec['sizeBytes']} B{dim} | EXIF: {'Yes' if rec.get('hasExif') else 'No'}",
                      ""]
        if len(self._recovered_files) > 100:
            lines.append(f"… and {len(self._recovered_files) - 100} more files")
        txt.write_text("\n".join(lines), encoding="utf-8")
        return txt

    def save_report(self) -> Optional[str]:
        """Save JSON report and RECOVERY_REPORT.txt."""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        json_file = self.output_dir / f"{self.case_id}_recovery_report.json"
        report = {
            "result": json.loads(self.ptjsonlib.get_result_json()),
            "recoveredFiles": self._recovered_files,
            "outputDirectories": {
                "active": str(self.active_dir), "deleted": str(self.deleted_dir),
                "corrupted": str(self.corrupted_dir), "metadata": str(self.metadata_dir),
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
            "Forensic filesystem-based photo recovery – ptlibs compliant",
            "Recovers images via fls + icat; preserves filenames, structure, EXIF",
        ]},
        {"usage": ["ptfilesystemrecovery <case-id> [options]"]},
        {"usage_example": [
            "ptfilesystemrecovery PHOTO-2025-001",
            "ptfilesystemrecovery CASE-042 --json",
            "ptfilesystemrecovery TEST-001 --dry-run",
            "ptfilesystemrecovery CASE-007 --force",
        ]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate without running external commands"],
            ["--force",            "",      "Override file_carving recommendation from Step 8"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"notes": [
            "Pipeline: load Step 8 JSON → tools → fls scan → icat+validate+EXIF → report",
            "Output:   active/ | deleted/ | corrupted/ | metadata/ | RECOVERY_REPORT.txt",
            "READ-ONLY: never modifies the forensic image",
            "Requires Step 8 (ptfilesystemanalysis) results",
            "Complies with ISO/IEC 27037:2012 and NIST SP 800-86",
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
        tool = PtFilesystemRecovery(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("validImages", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())