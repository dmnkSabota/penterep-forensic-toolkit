#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptfilecarving - Forensic file carving tool (PhotoRec)
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import os
import pexpect
import shutil
import stat
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
        IMAGE_EXTENSIONS, FORMAT_GROUP_MAP,
        DEFAULT_OUTPUT_DIR, PHOTOREC_TIMEOUT,
    )
except ImportError:
    from _constants import (
        IMAGE_EXTENSIONS, FORMAT_GROUP_MAP,
        DEFAULT_OUTPUT_DIR, PHOTOREC_TIMEOUT,
    )

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptfilecarving"

SUPPORTED_FORMATS = frozenset({".dd", ".raw", ".img", ".001", ".e01"})
EWF_FAMILY = frozenset({".e01", ".s01", ".l01", ".ex01"})
EWFEXPORT_TIMEOUT = 14400


class PtFileCarving(ForensicToolBase):
    """File carving (PhotoRec) - NIST SP 800-86, ISO/IEC 27037:2012."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.output_dir = Path(args.output_dir)
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise PermissionError(f"Permission denied: {self.output_dir} - try running with sudo")

        self.image_path: Optional[Path] = None
        self.image_format: Optional[str] = None
        self.carving_target: Optional[Path] = None
        self.converted_temp: Optional[Path] = None
        self.keep_converted = bool(getattr(args, "keep_converted", False))

        self.photorec_work = self.output_dir / f"{self.case_id}_photorec"
        self.carved_out = self.output_dir / f"{self.case_id}_carved"
        self.carved_valid = self.carved_out / "valid"
        self.carved_corrupt = self.carved_out / "corrupted"
        self.carved_dupes = self.carved_out / "duplicates"

        self.carved = 0
        self.image_files = 0
        self.valid = 0
        self.corrupted = 0
        self.duplicates = 0
        self.invalid = 0
        self.by_format: Dict[str, int] = {}
        self._valid_files: List[Dict] = []

        self._init_properties(__version__)

    def load_image(self) -> bool:
        ptprint("\n[1/5] Locating forensic image", "TITLE", condition=self._out())

        self.image_path = Path(self.args.image)

        if self.dry_run:
            self.image_format = self.image_path.suffix.lower() or ".dd"
            self.carving_target = self.image_path
            ptprint(f"  Image: {self.image_path}  |  Format: {self.image_format}",
                    "OK", condition=self._out())
            self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})
            self._add_node("imageLookup", True,
                           imagePath=str(self.image_path),
                           imageFormat=self.image_format)
            return True

        if not self.image_path.exists():
            return self._fail("imageLookup", f"Image not found: {self.image_path}")

        if not self._is_regular_file(self.image_path):
            return self._fail("imageLookup",
                              f"Path is not a regular file (block/character devices not "
                              f"supported): {self.image_path}. Acquire an image first via "
                              f"ptforensicimaging.")

        suffix = self.image_path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            return self._fail("imageLookup",
                              f"Unsupported image format: {suffix}. "
                              f"Supported: .dd, .raw, .img, .001, .e01.")

        self.image_format = suffix
        size_gb = self.image_path.stat().st_size / (1024 ** 3)
        ptprint(f"  ✓ {self.image_path.name}  |  Format: {self.image_format}  |  "
                f"Size: {size_gb:.2f} GB", "OK", condition=self._out())
        self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})
        self._add_node("imageLookup", True,
                       imagePath=str(self.image_path),
                       imageFormat=self.image_format,
                       imageSizeBytes=self.image_path.stat().st_size)
        return True

    @staticmethod
    def _is_regular_file(path: Path) -> bool:
        try:
            mode = path.stat().st_mode
        except OSError:
            return False
        if stat.S_ISBLK(mode) or stat.S_ISCHR(mode):
            return False
        if str(path).startswith("/dev/"):
            return False
        return path.is_file()

    def check_tools(self) -> bool:
        ptprint("\n[2/5] Checking required tools", "TITLE", condition=self._out())
        tools = {
            "photorec": "file carving engine",
            "file": "file type detection",
            "identify": "ImageMagick validation",
        }
        if self.image_format in EWF_FAMILY:
            tools["ewfexport"] = "libewf .e01 conversion"

        missing = []
        for t, desc in tools.items():
            found = self._check_command(t)
            ptprint(f"  [{'OK' if found else 'ERROR'}] {t}: {desc}",
                    "OK" if found else "ERROR", condition=self._out())
            if not found:
                missing.append(t)

        if "photorec" in missing:
            ptprint("  Install: sudo apt install testdisk", "ERROR", condition=self._out())
        if {"file", "identify"} & set(missing):
            ptprint("  Install: sudo apt install file imagemagick",
                    "ERROR", condition=self._out())
        if "ewfexport" in missing:
            ptprint("  Install: sudo apt install libewf-tools", "ERROR", condition=self._out())
        if missing:
            self._add_node("toolsCheck", False, missingTools=missing)
            return False

        self._add_node("toolsCheck", True, toolsChecked=list(tools))
        return True

    def prepare_carving_target(self) -> bool:
        ptprint("\n[3/5] Preparing carving target", "TITLE", condition=self._out())

        if self.dry_run:
            self.carving_target = self.image_path
            ptprint("  [DRY-RUN] Conversion skipped.", "INFO", condition=self._out())
            self._add_node("prepareTarget", True, dryRun=True,
                           carvingTarget=str(self.image_path),
                           conversionPerformed=False)
            return True

        if self.image_format not in EWF_FAMILY:
            self.carving_target = self.image_path
            ptprint(f"  ✓ Direct carving on RAW image: {self.image_path.name}",
                    "OK", condition=self._out())
            self._add_node("prepareTarget", True,
                           carvingTarget=str(self.image_path),
                           conversionPerformed=False)
            return True

        raw_prefix = self.output_dir / f"{self.case_id}_ewfexport"
        raw_path = raw_prefix.with_suffix(".raw")

        if raw_path.exists():
            ptprint(f"  ✓ Reusing existing raw conversion: {raw_path.name}",
                    "OK", condition=self._out())
            self.carving_target = raw_path
            self._add_node("prepareTarget", True,
                           carvingTarget=str(raw_path),
                           conversionPerformed=False,
                           reusedConversion=True)
            return True

        ptprint(f"  Converting {self.image_path.name} -> {raw_path.name} via ewfexport",
                "INFO", condition=self._out())
        ptprint("  This may take a while depending on image size ...",
                "INFO", condition=self._out())

        r = self._run_command(
            ["ewfexport", "-t", str(raw_prefix), "-f", "raw", "-u", str(self.image_path)],
            timeout=EWFEXPORT_TIMEOUT,
        )
        if not r["success"] or not raw_path.exists():
            return self._fail("prepareTarget",
                              f"ewfexport conversion failed: {r['stderr'] or 'no output file'}")

        self.carving_target = raw_path
        self.converted_temp = raw_path
        size_gb = raw_path.stat().st_size / (1024 ** 3)
        ptprint(f"  ✓ Conversion complete: {raw_path.name} ({size_gb:.2f} GB)",
                "OK", condition=self._out())
        self._add_node("prepareTarget", True,
                       carvingTarget=str(raw_path),
                       conversionPerformed=True,
                       sourceFormat=self.image_format,
                       convertedSizeBytes=raw_path.stat().st_size)
        return True

    def run_photorec(self) -> bool:
        ptprint("\n[4/5] Running PhotoRec", "TITLE", condition=self._out())

        if self.dry_run:
            ptprint("  [DRY-RUN] PhotoRec skipped.", "INFO", condition=self._out())
            self._add_node("photorecRun", True, dryRun=True)
            return True

        existing_dir = self._find_photorec_output()
        if existing_dir:
            existing = sum(1 for f in existing_dir.rglob("*") if f.is_file())
            if existing > 0:
                self.photorec_work = existing_dir
                ptprint(f"  Existing PhotoRec output reused: {existing} files.",
                        "OK", condition=self._out())
                self.carved = existing
                self._add_node("photorecRun", True, filesRecovered=existing,
                               skippedReason="existing_output_reused")
                return True

        for d in self.output_dir.glob(f"{self.case_id}_photorec*"):
            shutil.rmtree(str(d), ignore_errors=True)
        log_file = self.output_dir / f"{self.case_id}_photorec.log"
        ptprint(f"  photorec /log /d {self.photorec_work} {self.carving_target}",
                "INFO", condition=self._out())
        ptprint("  Running PhotoRec ...", "INFO", condition=self._out())

        try:
            child = pexpect.spawn(
                "photorec",
                ["/log", "/d", str(self.photorec_work), str(self.carving_target)],
                encoding="utf-8", timeout=PHOTOREC_TIMEOUT, dimensions=(40, 120),
                cwd=str(self.output_dir),
            )
            with open(log_file, "w") as lf:
                child.logfile = lf
                child.expect(r"Select a media", timeout=30)
                child.send("\r")
                child.expect(r"P NTFS|P exFAT|P FAT|P ext|Partition", timeout=30)
                child.send("\r")
                child.expect(r"Other", timeout=30)
                child.send("\r")
                child.expect(r"Free", timeout=30)
                child.send("\r")
                child.expect(r"Search|directory", timeout=30)
                child.send("c")
                while True:
                    try:
                        child.expect(r"\[ Quit", timeout=10)
                        break
                    except pexpect.TIMEOUT:
                        count = sum(
                            1 for d in self.output_dir.glob(f"{self.case_id}_photorec*")
                            if d.is_dir() for f in d.rglob("*") if f.is_file()
                        )
                        if self._out():
                            print(f"\r  Recovering... {count} files", end="", flush=True)
                    except pexpect.EOF:
                        break
                if self._out():
                    print()
                child.send("\r")
                child.close()
        except KeyboardInterrupt:
            child.terminate()
            ptprint("\n  Interrupted by user.", "WARNING", condition=self._out())
            raise
        except Exception as exc:
            return self._fail("photorecRun", f"PhotoRec failed: {exc}")

        actual = self._find_photorec_output()
        if actual:
            self.photorec_work = actual
        total = sum(1 for f in self.photorec_work.rglob("*") if f.is_file())
        ptprint(f"  PhotoRec done. {total} file(s) recovered.", "OK", condition=self._out())
        self.carved = total
        self._add_node("photorecRun", True, filesRecovered=total, logFile=str(log_file))
        return True

    def _find_photorec_output(self) -> Optional[Path]:
        dirs = sorted(
            (p for p in self.output_dir.glob(f"{self.case_id}_photorec*") if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
        )
        return dirs[-1] if dirs else None

    def _process_candidate(self, fp: Path, seen_hashes: set) -> None:
        try:
            sha = self._file_sha256(fp) or ""
            is_dup = sha in seen_hashes
        except Exception:
            sha = ""
            is_dup = False

        if is_dup:
            self.duplicates += 1
            shutil.move(str(fp), str(self.carved_dupes / fp.name))
            return
        if sha:
            seen_hashes.add(sha)

        status, vinfo = self._validate_image_file(fp)
        ext = fp.suffix.lower().lstrip(".")
        group = FORMAT_GROUP_MAP.get(ext, "other")

        if status == "valid":
            self.valid += 1
            self.by_format[group] = self.by_format.get(group, 0) + 1
            dest = self.carved_valid / group
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(fp), str(dest / fp.name))
            self._valid_files.append({
                "filename": fp.name,
                "sha256": sha,
                "sizeBytes": vinfo["size"],
                "format": vinfo.get("imageFormat"),
                "dimensions": vinfo.get("dimensions"),
                "group": group,
            })
        elif status == "corrupted":
            self.corrupted += 1
            shutil.move(str(fp), str(self.carved_corrupt / fp.name))
        else:
            self.invalid += 1
            if fp.exists():
                fp.unlink()

    def validate_and_deduplicate(self) -> bool:
        ptprint("\n[5/5] Validating and deduplicating", "TITLE", condition=self._out())

        if not self.photorec_work.exists() or self.dry_run:
            ptprint("  [DRY-RUN] Skipping file collection.", "INFO", condition=self._out())
            self._add_node("validationDedup", True, dryRun=True)
            return True

        for d in (self.carved_valid, self.carved_corrupt, self.carved_dupes):
            d.mkdir(parents=True, exist_ok=True)

        candidates: List[Path] = [
            f for f in self.photorec_work.rglob("*")
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        ]

        ptprint(f"  Candidate image files: {len(candidates)}", "INFO", condition=self._out())
        self.image_files = len(candidates)

        seen_hashes: set = set()
        for idx, fp in enumerate(candidates, 1):
            self._progress(idx, len(candidates), fp.name[:35])
            self._process_candidate(fp, seen_hashes)

        if self._out():
            print()

        ptprint(f"  Candidates: {self.image_files}  |  Valid: {self.valid}  |  Corrupted: {self.corrupted}  |  Duplicates: {self.duplicates}  |  Invalid: {self.invalid}",
                "OK", condition=self._out())
        for group, count in sorted(self.by_format.items()):
            ptprint(f"    {group.upper()}: {count}", "INFO", condition=self._out())

        self._add_node("validationDedup", True,
                       imageCandidates=self.image_files,
                       validImages=self.valid,
                       corruptedImages=self.corrupted,
                       duplicates=self.duplicates,
                       invalidFiles=self.invalid,
                       byFormat=self.by_format,
                       validFiles=self._valid_files,
                       directories={
                           "valid": str(self.carved_valid),
                           "corrupted": str(self.carved_corrupt),
                           "duplicates": str(self.carved_dupes),
                       })
        return True

    def cleanup_converted(self) -> None:
        if self.converted_temp and self.converted_temp.exists() and not self.keep_converted:
            try:
                self.converted_temp.unlink()
                ptprint(f"\n  ✓ Removed converted file: {self.converted_temp.name}",
                        "OK", condition=self._out())
            except OSError:
                pass

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"FILE CARVING (PHOTOREC) v{__version__}  |  Case: {self.case_id}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.load_image():
            self.ptjsonlib.set_status("finished")
            return
        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return
        if not self.prepare_carving_target():
            self.ptjsonlib.set_status("finished")
            return
        if not self.run_photorec():
            self.cleanup_converted()
            self.ptjsonlib.set_status("finished")
            return
        self.validate_and_deduplicate()
        self.cleanup_converted()

        success_rate = round(self.valid / self.image_files * 100, 1) if self.image_files else None
        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "method": "file_carving",
            "carvingTool": "photorec",
            "sourceFormat": self.image_format,
            "carvingTarget": str(self.carving_target) if self.carving_target else "",
            "conversionPerformed": self.converted_temp is not None,
            "totalCarvedFiles": self.carved,
            "imageCandidates": self.image_files,
            "validImages": self.valid,
            "corruptedImages": self.corrupted,
            "duplicates": self.duplicates,
            "invalidFiles": self.invalid,
            "byFormat": self.by_format,
            "successRate": success_rate,
            "outputDir": str(self.carved_out),
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": f"File carving complete - {self.valid} valid images "
                          f"(source format: {self.image_format})",
                "result": "SUCCESS" if self.valid > 0 else "NO_FILES",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tool": "photorec",
            }
        ))

        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint("FILE CARVING COMPLETE", "OK", condition=self._out())
        ptprint(f"Source format: {self.image_format}  |  "
                f"Carved: {self.carved}  |  Valid images: {self.valid}  |  "
                f"Corrupted: {self.corrupted}  |  Duplicates: {self.duplicates}",
                "INFO", condition=self._out())
        if success_rate is not None:
            ptprint(f"Success rate: {success_rate}%", "OK", condition=self._out())
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
            "Forensic file carving tool - ptlibs compliant",
            "Recovers image files using PhotoRec (testdisk package)",
            "Supported input formats: .dd, .raw, .img, .001, .e01 (auto-converted)",
            "Carving runs on forensic image files only (block devices rejected)",
            "Post-carving: extension filter + ImageMagick validation + SHA-256 dedup",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
        {"usage": ["ptfilecarving <case-id> <image> [options]"]},
        {"usage_example": [
            "ptfilecarving PHOTORECOVERY-2025-01-26-001 /var/forensics/images/CASE.dd",
            "ptfilecarving CASE-001 /path/to/image.raw --analyst 'Jane'",
            "ptfilecarving CASE-001 /path/to/image.E01 --json-out coc.json",
            "ptfilecarving CASE-001 /path/to/image.E01 --keep-converted --dry-run",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["image", "", "Path to forensic image (.dd/.raw/.img/.001/.e01) - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["", "--keep-converted", "", "Keep ewfexport raw conversion after carving"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["", "--dry-run", "", "Simulate without running PhotoRec"],
            ["-h", "--help", "", "Show help"],
            ["", "--version", "", "Show version"],
        ]},
        {"notes": [
            "Requires: photorec (sudo apt install testdisk)",
            "Requires: identify (sudo apt install imagemagick)",
            "Requires: pexpect (pip install pexpect) - drives PhotoRec UI automatically",
            "Optional: ewfexport (sudo apt install libewf-tools) - required for .e01 input",
            ".e01 inputs are converted to .raw via ewfexport before carving (auto-cleanup)",
            "Block/character devices and /dev/* paths are rejected - acquire image first",
            "Output: carved/valid/<format>/ | carved/corrupted/ | carved/duplicates/",
            "PhotoRec output logged to case_id_photorec.log",
            "Original filenames are not preserved by PhotoRec",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("image")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-a", "--analyst", default="Analyst")
    parser.add_argument("-j", "--json-out", default=None)
    parser.add_argument("--keep-converted", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--version", action="version",
                        version=f"{SCRIPTNAME} {__version__}")

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
        tool = PtFileCarving(args)
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