#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptfilesystemrecovery - Forensic filesystem-based photo recovery tool
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import (
        DEFAULT_OUTPUT_DIR, IMAGE_EXTENSIONS, FORMAT_GROUP_MAP,
        FLS_RECOVERY_TIMEOUT, ICAT_TIMEOUT,
    )
except ImportError:
    from _constants import (
        DEFAULT_OUTPUT_DIR, IMAGE_EXTENSIONS, FORMAT_GROUP_MAP,
        FLS_RECOVERY_TIMEOUT, ICAT_TIMEOUT,
    )

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptfilesystemrecovery"


class PtFilesystemRecovery(ForensicToolBase):
    """Filesystem-based photo recovery - fls + icat (Sleuth Kit), NIST SP 800-86, ISO/IEC 27037:2012."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.image_path = Path(args.image)
        self.offset = args.offset
        self.output_dir = Path(args.output_dir) / f"{self.case_id}_recovered"

        self.active_dir = self.output_dir / "active"
        self.deleted_dir = self.output_dir / "deleted"

        self.active_files: List[Dict] = []
        self.deleted_files: List[Dict] = []
        self.valid = 0
        self.corrupted = 0
        self.with_exif = 0
        self.by_format: Dict[str, int] = {}

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({"imagePath": str(self.image_path), "offset": self.offset})

    def check_tools(self) -> bool:
        ptprint("\n[1/3] Checking required tools", "TITLE", condition=self._out())
        tools = {"fls": "file listing", "icat": "inode extraction",
                 "file": "type detection", "identify": "image validation",
                 "exiftool": "EXIF extraction"}
        missing = [t for t in tools if not self._check_command(t)]
        for t, desc in tools.items():
            ptprint(f"  [{'OK' if t not in missing else 'ERROR'}] {t}: {desc}",
                    "OK" if t not in missing else "ERROR", condition=self._out())
        if missing:
            ptprint(f"Missing: {', '.join(missing)} - sudo apt-get install sleuthkit imagemagick libimage-exiftool-perl",
                    "ERROR", condition=self._out())
            self._add_node("toolsCheck", False, missingTools=missing)
            return False
        self._add_node("toolsCheck", True, toolsChecked=list(tools))
        return True

    def scan_files(self) -> bool:
        ptprint("\n[2/3] Scanning filesystem", "TITLE", condition=self._out())
        ptprint(f"  fls (offset={self.offset}) ...", "INFO", condition=self._out())

        r = self._run_command(["fls", "-r", "-p", "-o", str(self.offset), str(self.image_path)],
                              timeout=FLS_RECOVERY_TIMEOUT)
        if not r["success"] and not self.dry_run:
            return self._fail("filesystemScan", f"fls failed: {r['stderr']}")

        pattern = re.compile(r"^\S+\s+\*?\s*(\d+)(?:-\d+)*:\s+(.+)$")
        for line in r["stdout"].splitlines():
            line = line.strip()
            if not line or line.startswith("d/d"):
                continue
            m = pattern.match(line)
            if not m:
                continue
            inode = int(m.group(1))
            filepath = m.group(2).strip()
            ext = Path(filepath).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue
            is_deleted = "*" in line.split(":")[0]
            entry = {"inode": inode, "path": filepath, "filename": Path(filepath).name}
            if is_deleted:
                self.deleted_files.append(entry)
            else:
                self.active_files.append(entry)

        total = len(self.active_files) + len(self.deleted_files)
        ptprint(f"  ✓ {total} image files  (active={len(self.active_files)}, deleted={len(self.deleted_files)})",
                "OK", condition=self._out())
        self._add_node("filesystemScan", True,
                       activeFiles=len(self.active_files), deletedFiles=len(self.deleted_files),
                       totalImageFiles=total)
        return True

    def extract_files(self) -> None:
        ptprint("\n[3/3] Extracting files", "TITLE", condition=self._out())

        if not self.dry_run:
            try:
                self.active_dir.mkdir(parents=True, exist_ok=True)
                self.deleted_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                ptprint(f"Permission denied: {self.output_dir} - try running with sudo", "ERROR", condition=True)
                return

        all_entries = [(e, self.active_dir, "active") for e in self.active_files] + \
                      [(e, self.deleted_dir, "deleted") for e in self.deleted_files]

        if not all_entries:
            ptprint("  No image files to extract.", "WARNING", condition=self._out())
            return

        for idx, (entry, out_base, label) in enumerate(all_entries, 1):
            self._progress(idx, len(all_entries), entry["filename"][:40])

            dest = out_base / entry["path"].lstrip("/")
            if not self.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with open(dest, "wb") as fh:
                        proc = subprocess.run(
                            ["icat", "-o", str(self.offset), str(self.image_path), str(entry["inode"])],
                            stdout=fh, stderr=subprocess.PIPE, timeout=ICAT_TIMEOUT, check=False)
                    if proc.returncode != 0 or not dest.exists():
                        if dest.exists():
                            dest.unlink()
                        continue
                except Exception:
                    if dest.exists():
                        dest.unlink()
                    continue

            status, vinfo = self._validate_image_file(dest if not self.dry_run else self.image_path)
            if status not in ("valid", "corrupted"):
                if not self.dry_run and dest.exists():
                    dest.unlink()
                continue

            if status == "valid":
                self.valid += 1
                ext = Path(entry["filename"]).suffix.lower().lstrip(".")
                group = FORMAT_GROUP_MAP.get(ext, "other")
                self.by_format[group] = self.by_format.get(group, 0) + 1
                _, has_exif = self._extract_exif_metadata(dest if not self.dry_run else self.image_path)
                if has_exif:
                    self.with_exif += 1
            else:
                self.corrupted += 1

        if self._out():
            print()
        ptprint(f"✓ Extracted: valid={self.valid}  corrupted={self.corrupted}  withExif={self.with_exif}",
                "OK", condition=self._out())

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"FILESYSTEM RECOVERY v{__version__} | Case: {self.case_id}", "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.image_path.exists() and not self.dry_run:
            ptprint(f"Image not found: {self.image_path}", "ERROR", condition=True)
            self.ptjsonlib.set_status("finished")
            return

        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return
        if not self.scan_files():
            self.ptjsonlib.set_status("finished")
            return

        self.extract_files()

        total = len(self.active_files) + len(self.deleted_files)
        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "method": "filesystem_scan",
            "imageFilesFound": total,
            "activeImages": len(self.active_files),
            "deletedImages": len(self.deleted_files),
            "validImages": self.valid,
            "corruptedImages": self.corrupted,
            "withExif": self.with_exif,
            "byFormat": self.by_format,
            "outputDir": str(self.output_dir),
            "successRate": round(self.valid / total * 100, 1) if total else None,
        })
        self._add_node("recoverySummary", True,
                       imageFilesFound=total, validImages=self.valid,
                       corruptedImages=self.corrupted, withExif=self.with_exif)
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": f"Filesystem recovery complete - {self.valid} valid files recovered",
                "result": "SUCCESS" if self.valid > 0 else "NO_FILES",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))

        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint("RECOVERY COMPLETE", "OK", condition=self._out())
        ptprint(f"Found: {total}  Valid: {self.valid}  Corrupted: {self.corrupted}  EXIF: {self.with_exif}",
                "INFO", condition=self._out())
        ptprint(f"Output: {self.output_dir}", "INFO", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())
        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        if not self.args.json_out:
            return None
        raw = self.ptjsonlib.get_result_json()
        Path(self.args.json_out).write_text(raw, encoding="utf-8")
        ptprint(f"\n✓ JSON report saved: {self.args.json_out}", "OK", condition=True)
        return self.args.json_out


def get_help() -> List[Dict]:
    return [
        {"description": [
            "Forensic filesystem-based photo recovery - ptlibs compliant",
            "Recovers image files via fls + icat, preserving filenames and paths",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
        {"usage": ["ptfilesystemrecovery <case-id> <image> [options]"]},
        {"usage_example": [
            "ptfilesystemrecovery CASE-001 /var/forensics/images/CASE-001.dd",
            "ptfilesystemrecovery CASE-001 /path/to/image.dd --offset 2048 --analyst 'Jane'",
            "ptfilesystemrecovery CASE-001 /path/to/image.dd --dry-run",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["image", "", "Path to forensic image (.dd) - REQUIRED"],
            ["-s", "--offset", "<n>", "Partition offset in sectors (default: 0)"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without running external commands"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "Requires: fls, icat (sleuthkit) + identify (imagemagick) + exiftool",
            "Output: {case_id}_recovered/active/  and  {case_id}_recovered/deleted/",
            "Exit 0 = files recovered | Exit 1 = no files | Exit 99 = error | Exit 130 = Ctrl+C",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("image")
    parser.add_argument("-s", "--offset", type=int, default=0)
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-a", "--analyst", default="Analyst")
    parser.add_argument("-j", "--json-out", default=None)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--version", action="version", version=f"{SCRIPTNAME} {__version__}")

    if len(sys.argv) == 1 or {"-h", "--help"} & set(sys.argv):
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    args.json = bool(args.json_out)
    ptprinthelper.print_banner(SCRIPTNAME, __version__, False)
    return args


def main() -> int:
    try:
        args = parse_args()
        tool = PtFilesystemRecovery(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if props.get("validImages", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())