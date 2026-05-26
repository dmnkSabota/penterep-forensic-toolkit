#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptintegrityvalidation - Forensic file integrity validation
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import IMAGE_EXTENSIONS, DEFAULT_OUTPUT_DIR, VALIDATE_TIMEOUT
except ImportError:
    from _constants import IMAGE_EXTENSIONS, DEFAULT_OUTPUT_DIR, VALIDATE_TIMEOUT

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptintegrityvalidation"

CORRUPTION_TYPES: Dict[str, str] = {
    "missing_footer": "Missing end marker (EOI/EOF)",
    "invalid_header": "Invalid or corrupt file header",
    "corrupt_segments": "Damaged internal segments",
    "truncated": "File appears truncated",
    "corrupt_data": "Image data region is damaged",
    "unknown": "Unclassified corruption",
}


class PtIntegrityValidation(ForensicToolBase):
    """Forensic integrity validation - file + identify + format tools, NIST SP 800-86, ISO/IEC 27037:2012."""

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

        self.consolidated_dir = Path(args.consolidated_dir)

        self.total = 0
        self.valid = 0
        self.repairable = 0
        self.corrupted = 0
        self.by_format: Dict[str, int] = {}
        self.corruption_types: Dict[str, int] = {}
        self._results: List[Dict] = []

        self._init_properties(__version__)

    def _validate_jpeg_pil(self, path: Path) -> Tuple[str, str]:
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            img = Image.open(str(path))
            img.verify()
            return "valid", "none"
        except ImportError:
            pass
        except Exception as exc:
            exc_s = str(exc).lower()
            if "truncat" in exc_s:
                return "repairable", "truncated"
            if "header" in exc_s or "magic" in exc_s:
                return "repairable", "invalid_header"
            return "repairable", "corrupt_data"

        try:
            from PIL import Image, ImageFile
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            img = Image.open(str(path))
            img.load()
            return "repairable", "truncated"
        except Exception:
            pass

        return "corrupted", "unknown"

    def _validate_jpeg_detail(self, path: Path) -> Tuple[str, str]:
        try:
            tail = path.read_bytes()[-2:]
            if tail != bytes([0xFF, 0xD9]):
                return "repairable", "missing_footer"
        except Exception:
            pass

        r = self._run_command(["jpeginfo", "-c", str(path)], timeout=VALIDATE_TIMEOUT)
        if r["success"]:
            out = r["stdout"].lower()
            if "ok" in out and "error" not in out:
                return "valid", "none"
            if "unexpected end" in out or "premature end" in out:
                return "repairable", "truncated"
            if "missing eoi" in out or "extraneous bytes" in out:
                return "repairable", "missing_footer"
            if "invalid marker" in out or "corrupt" in out:
                return "repairable", "corrupt_segments"
        return self._validate_jpeg_pil(path)

    def _validate_png_detail(self, path: Path) -> Tuple[str, str]:
        r = self._run_command(["pngcheck", "-v", str(path)], timeout=VALIDATE_TIMEOUT)
        if r["success"]:
            out = r["stdout"].lower()
            if "ok" in out and "error" not in out:
                return "valid", "none"
        if r["stderr"]:
            err = r["stderr"].lower()
            if "crc error" in err or "invalid chunk" in err:
                return "repairable", "corrupt_segments"
            if "premature end" in err or "truncat" in err:
                return "repairable", "truncated"
            return "corrupted", "unknown"
        return "corrupted", "unknown"

    def _validate_tiff_detail(self, path: Path) -> Tuple[str, str]:
        r = self._run_command(["tiffinfo", str(path)], timeout=VALIDATE_TIMEOUT)
        if r["success"]:
            return "valid", "none"
        err = (r["stderr"] + r["stdout"]).lower()
        if "bad value" in err or "corrupt" in err:
            return "repairable", "corrupt_segments"
        if "unrecognized" in err or "not a tiff" in err:
            return "corrupted", "invalid_header"
        return "corrupted", "unknown"

    def _validate_generic_detail(self, path: Path) -> Tuple[str, str]:
        try:
            from PIL import Image
            img = Image.open(str(path))
            img.verify()
            return "valid", "none"
        except ImportError:
            pass
        except Exception:
            return "repairable", "corrupt_data"
        return "corrupted", "unknown"

    def _detect_detail(self, path: Path, base_status: str,
                       ext: str) -> Tuple[str, str]:
        if base_status != "valid":
            return "repairable", "corrupt_data"
        if ext in (".jpg", ".jpeg"):
            return self._validate_jpeg_detail(path)
        if ext == ".png":
            return self._validate_png_detail(path)
        if ext in (".tif", ".tiff"):
            return self._validate_tiff_detail(path)
        return self._validate_generic_detail(path)

    def _validate_full(self, path: Path) -> Dict:
        ext = path.suffix.lower()
        base_status, vinfo = self._validate_image_file(path)

        if base_status == "invalid":
            return {
                "path": str(path),
                "filename": path.name,
                "status": "corrupted",
                "corruptionType": "invalid_header",
                "sizeBytes": vinfo.get("size", 0),
                "imageFormat": None,
                "dimensions": None,
            }

        det_status, ctype = self._detect_detail(path, base_status, ext)

        if det_status == "valid":
            final_status, ctype = "valid", "none"
        elif det_status == "repairable":
            final_status = "repairable"
        else:
            final_status = "corrupted"
            if ctype == "none":
                ctype = "unknown"

        return {
            "path": str(path),
            "filename": path.name,
            "status": final_status,
            "corruptionType": ctype,
            "sizeBytes": vinfo.get("size", 0),
            "imageFormat": vinfo.get("imageFormat"),
            "dimensions": vinfo.get("dimensions"),
        }

    def check_tools(self) -> bool:
        ptprint("\n[1/2] Checking validation tools", "TITLE", condition=self._out())
        tools = {
            "identify": "ImageMagick (required)",
            "file": "file type detection (required)",
            "jpeginfo": "JPEG validation (optional)",
            "pngcheck": "PNG validation (optional)",
            "tiffinfo": "TIFF validation (optional)",
        }
        missing_required = []
        for t, desc in tools.items():
            found = self._check_command(t)
            ptprint(f"  [{'OK' if found else 'WARN'}] {t}: {desc}",
                    "OK" if found else "WARNING", condition=self._out())
            if not found and "required" in desc:
                missing_required.append(t)

        if missing_required:
            ptprint(f"  Missing required: {', '.join(missing_required)}",
                    "ERROR", condition=self._out())
            self._add_node("toolsCheck", False, missingRequired=missing_required)
            return False

        ptprint("  Optional tools fall back to PIL/Pillow if unavailable.",
                "INFO", condition=self._out())
        self._add_node("toolsCheck", True, tools=list(tools))
        return True

    def _update_counts(self, result: Dict) -> None:
        status = result["status"]
        fmt = Path(result["path"]).suffix.lower().lstrip(".")
        self.total += 1
        if status == "valid":
            self.valid += 1
        elif status == "repairable":
            self.repairable += 1
        else:
            self.corrupted += 1
        self.by_format[fmt] = self.by_format.get(fmt, 0) + 1
        if status in ("repairable", "corrupted"):
            ctype = result["corruptionType"]
            self.corruption_types[ctype] = self.corruption_types.get(ctype, 0) + 1

    def _print_validation_summary(self) -> None:
        ptprint(f"\n  Validated: {self.total}  |  Valid: {self.valid}  |  Repairable: {self.repairable}  |  Corrupted: {self.corrupted}",
                "OK", condition=self._out())
        if self.corruption_types:
            ptprint("  Corruption types:", "INFO", condition=self._out())
            for ctype, count in sorted(self.corruption_types.items()):
                ptprint(f"    {count}x {CORRUPTION_TYPES.get(ctype, ctype)}", "INFO", condition=self._out())

    def validate_all(self) -> bool:
        ptprint("\n[2/2] Validating files (in-place - no copies created)",
                "TITLE", condition=self._out())

        if not self.consolidated_dir.exists() and not self.dry_run:
            return self._fail("integrityValidation",
                              f"Directory not found: {self.consolidated_dir}")

        candidates = [] if self.dry_run else [
            f for f in self.consolidated_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        ]

        ptprint(f"  Files to validate: {len(candidates)}", "INFO", condition=self._out())

        if not candidates:
            if not self.dry_run:
                ptprint("  No image files found.", "WARNING", condition=self._out())
            self._add_node("integrityValidation", True, dryRun=self.dry_run, totalFiles=0)
            return True

        for idx, fp in enumerate(candidates, 1):
            self._progress(idx, len(candidates), fp.name[:35])
            result = self._validate_full(fp)
            self._results.append(result)
            self._update_counts(result)

        if self._out():
            print()

        self._print_validation_summary()

        self._add_node("integrityValidation", True,
                       totalFiles=self.total,
                       validFiles=self.valid,
                       repairableFiles=self.repairable,
                       corruptedFiles=self.corrupted,
                       corruptionTypes=self.corruption_types,
                       byFormat=self.by_format,
                       fileResults=self._results)
        return True



    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"INTEGRITY VALIDATION v{__version__}  |  Case: {self.case_id}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return
        self.validate_all()

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "method": "in_place_validation",
            "totalFiles": self.total,
            "validFiles": self.valid,
            "repairableFiles": self.repairable,
            "corruptedFiles": self.corrupted,
            "corruptionTypes": self.corruption_types,
            "byFormat": self.by_format,
            "consolidatedDir": str(self.consolidated_dir),
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": f"Integrity validation complete - {self.valid} valid, {self.repairable} repairable, {self.corrupted} corrupted",
                "result": "SUCCESS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))

        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint("VALIDATION COMPLETE", "OK", condition=self._out())
        ptprint(f"Total: {self.total}  |  Valid: {self.valid}  |  Repairable: {self.repairable}  |  Corrupted: {self.corrupted}",
                "INFO", condition=self._out())
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
            "Forensic file integrity validation - ptlibs compliant",
            "Two-stage validation: file(1) + ImageMagick + format-specific tools",
            "Validates files IN-PLACE (no copies created) - no extra disk space needed",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
        {"usage": ["ptintegrityvalidation <case-id> <consolidated-dir> [options]"]},
        {"usage_example": [
            "ptintegrityvalidation CASE-001 /var/forensics/images/CASE-001_consolidated",
            "ptintegrityvalidation CASE-001 /path/to/consolidated --dry-run",
            "ptintegrityvalidation CASE-001 /path/to/consolidated --json-out step10.json",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["consolidated-dir", "", "Path to consolidated directory - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Report output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without reading files"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "Required: file(1) + ImageMagick identify",
            "Optional: jpeginfo | pngcheck | tiffinfo | PIL fallback",
            "Output: case_id_integrity_validation.json with per-file classification",
            "Files are NOT moved or copied - referenced by path only",
            "Install optional tools: sudo apt install jpeginfo pngcheck libtiff-tools",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("consolidated_dir")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-a", "--analyst", default="Analyst")
    parser.add_argument("-j", "--json-out", default=None)
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
        tool = PtIntegrityValidation(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if props.get("totalFiles", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())