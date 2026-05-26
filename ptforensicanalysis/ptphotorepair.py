#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptphotorepair - Forensic photo repair tool
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import DEFAULT_OUTPUT_DIR, VALIDATE_TIMEOUT
except ImportError:
    from _constants import DEFAULT_OUTPUT_DIR, VALIDATE_TIMEOUT

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptphotorepair"

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
JPEG_SOS = b"\xff\xda"
JPEG_DQT = b"\xff\xdb"

try:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class PtPhotoRepair(ForensicToolBase):
    """Forensic photo repair - JPEG byte-level + PNG PIL resave, NIST SP 800-86, ISO/IEC 27037:2012."""

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

        self.decisions_file = Path(args.decisions_file)
        self.repaired_dir = self.output_dir / f"{self.case_id}_repaired"
        self.failed_dir = self.output_dir / f"{self.case_id}_repair_failed"

        self.total = 0
        self.repaired = 0
        self.failed = 0
        self.skipped = 0
        self.by_method: Dict[str, int] = {}
        self._results: List[Dict] = []

        self._init_properties(__version__)

    def _fix_footer(self, path: Path) -> Tuple[bool, str]:
        try:
            data = path.read_bytes()
            if not data.startswith(JPEG_SOI):
                return False, "Missing SOI"
            if data.endswith(JPEG_EOI):
                return True, "EOI already present"
            path.write_bytes(data + JPEG_EOI)
            return True, f"EOI appended ({len(data)} bytes)"
        except Exception as exc:
            return False, str(exc)

    def _fix_header(self, path: Path) -> Tuple[bool, str]:
        try:
            data = path.read_bytes()
            pos = data.find(JPEG_SOS)
            if pos == -1:
                pos = data.find(JPEG_DQT)
            if pos == -1:
                return False, "No SOS or DQT marker found"
            app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            rebuilt = JPEG_SOI + app0 + data[pos:]
            if not rebuilt.endswith(JPEG_EOI):
                rebuilt += JPEG_EOI
            path.write_bytes(rebuilt)
            if PIL_AVAILABLE:
                img = Image.open(str(path))
                img.load()
                return True, f"Header rebuilt: {img.width}x{img.height} px"
            return True, f"Header rebuilt ({len(rebuilt)} bytes)"
        except Exception as exc:
            return False, str(exc)

    def _fix_segments(self, path: Path) -> Tuple[bool, str]:
        try:
            data = path.read_bytes()
            if not data.startswith(JPEG_SOI):
                return False, "Missing SOI"
            kept = [JPEG_SOI]
            pos = 2
            while pos < len(data) - 1:
                if data[pos] != 0xFF:
                    pos += 1
                    continue
                marker = data[pos:pos + 2]
                if marker == JPEG_SOS:
                    kept.append(data[pos:])
                    break
                if marker == JPEG_EOI:
                    kept.append(JPEG_EOI)
                    break
                if pos + 4 <= len(data):
                    seg_len = int.from_bytes(data[pos + 2:pos + 4], "big")
                    if 2 <= seg_len <= len(data) - pos - 2:
                        if 0x01 <= data[pos + 1] <= 0xFE:
                            kept.append(data[pos:pos + 2 + seg_len])
                        pos += 2 + seg_len
                        continue
                pos += 2
            rebuilt = b"".join(kept)
            if not rebuilt.endswith(JPEG_EOI):
                rebuilt += JPEG_EOI
            path.write_bytes(rebuilt)
            if PIL_AVAILABLE:
                img = Image.open(str(path))
                img.load()
                return True, f"Segments stripped: {img.width}x{img.height} px"
            return True, f"Segments stripped ({len(rebuilt)} bytes)"
        except Exception as exc:
            return False, str(exc)

    def _fix_truncated(self, path: Path) -> Tuple[bool, str]:
        if not PIL_AVAILABLE:
            return self._fix_footer(path)
        tmp = path.with_name(path.stem + "_tmp" + path.suffix)
        try:
            img = Image.open(str(path))
            img.load()
            if img.width == 0 or img.height == 0:
                return False, "Zero dimensions"
            img.save(tmp, quality=95)
            shutil.move(str(tmp), str(path))
            return True, f"Truncated recovered: {img.width}x{img.height} px"
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            return False, str(exc)

    def _fix_png(self, path: Path) -> Tuple[bool, str]:
        if not PIL_AVAILABLE:
            return False, "PIL/Pillow not available"
        tmp = path.with_name(path.stem + "_tmp.png")
        try:
            img = Image.open(str(path))
            img.load()
            if img.width == 0 or img.height == 0:
                return False, "Zero dimensions"
            img.save(tmp, optimize=True)
            shutil.move(str(tmp), str(path))
            return True, f"PNG resaved: {img.width}x{img.height} px"
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            return False, str(exc)

    def _apply_strategy(self, path: Path, ctype: str) -> Tuple[bool, str, str]:
        ext = path.suffix.lower()

        if ext == ".png":
            ok, msg = self._fix_png(path)
            return ok, "png_resave", msg

        if ext not in (".jpg", ".jpeg"):
            return False, "not_supported", f"Format not supported: {ext}"

        if ctype == "missing_footer":
            ok, msg = self._fix_footer(path)
            if ok:
                return True, "eoi_append", msg

        if ctype == "invalid_header":
            ok, msg = self._fix_header(path)
            if ok:
                return True, "header_reconstruct", msg

        if ctype in ("corrupt_segments", "corrupt_segment", "invalid_segment"):
            ok, msg = self._fix_segments(path)
            if ok:
                return True, "segment_strip", msg

        ok, msg = self._fix_truncated(path)
        return ok, "pil_reopen", msg

    def _repair_single(self, decision: Dict) -> Dict:
        path_s = decision.get("path")
        ctype = decision.get("corruptionType", "unknown")
        result: Dict = {
            "filename": decision.get("filename", "unknown"),
            "corruptionType": ctype,
            "success": False,
            "method": "skipped",
            "repairedPath": None,
        }

        src = Path(path_s) if path_s else None
        if not src or (not self.dry_run and not src.exists()):
            result["message"] = "source not found"
            self.skipped += 1
            return result

        if self.dry_run:
            result.update({"success": True, "method": "dry_run",
                           "message": "[DRY-RUN] simulated"})
            return result

        dest = self.repaired_dir / src.name
        if dest.exists():
            dest = self.repaired_dir / f"{src.stem}_{src.stat().st_size}{src.suffix}"
        shutil.copy2(str(src), str(dest))

        success, method, msg = self._apply_strategy(dest, ctype)
        result.update({"success": success, "method": method, "message": msg})

        if success:
            result["repairedPath"] = str(dest)
        else:
            dest.unlink(missing_ok=True)
            if src.exists():
                shutil.copy2(str(src), str(self.failed_dir / src.name))

        return result

    def load_decisions(self) -> Optional[List[Dict]]:
        ptprint("\n[1/2] Loading repair decisions", "TITLE", condition=self._out())

        if not self.decisions_file.exists() and not self.dry_run:
            self._fail("decisionsLoad", f"{self.decisions_file.name} not found")
            return None

        if self.dry_run:
            ptprint("  [DRY-RUN] Empty decisions list.", "INFO", condition=self._out())
            self._add_node("decisionsLoad", True, dryRun=True)
            return []

        try:
            data = json.loads(self.decisions_file.read_text(encoding="utf-8"))
            nodes = data.get("results", {}).get("nodes", [])
            rd = next((n for n in nodes if n.get("type") == "repairDecision"), None)
            decisions = rd["properties"].get("decisions", []) if rd else []
        except Exception as exc:
            self._fail("decisionsLoad", f"Cannot read file: {exc}")
            return None

        to_repair = [d for d in decisions if d.get("decision") == "ATTEMPT_REPAIR"]
        ptprint(f"  Loaded {len(decisions)} decisions  |  ATTEMPT_REPAIR: {len(to_repair)}",
                "OK", condition=self._out())
        self._add_node("decisionsLoad", True,
                       totalDecisions=len(decisions),
                       toRepair=len(to_repair))
        return to_repair

    def repair_all(self, decisions: List[Dict]) -> None:
        ptprint(f"\n[2/2] Repairing {len(decisions)} file(s)",
                "TITLE", condition=self._out())

        if not decisions:
            ptprint("  Nothing to repair.", "WARNING", condition=self._out())
            self._add_node("repairResults", True, total=0, repaired=0, failed=0, skipped=0, byMethod={}, repairResults=[])
            return

        if not self.dry_run:
            self.repaired_dir.mkdir(parents=True, exist_ok=True)
            self.failed_dir.mkdir(parents=True, exist_ok=True)

        for idx, decision in enumerate(decisions, 1):
            ptprint(f"  [{idx}/{len(decisions)}] {decision.get('filename', '?')} ({decision.get('corruptionType', '?')})",
                    "INFO", condition=self._out())

            result = self._repair_single(decision)
            self._results.append(result)

            if result["method"] != "skipped":
                self.total += 1
                if result["success"]:
                    self.repaired += 1
                else:
                    self.failed += 1
                self.by_method[result["method"]] = self.by_method.get(result["method"], 0) + 1

            ptprint(f"    {'✓' if result['success'] else '✗'} {result['method']}: {result.get('message', '')}",
                    "OK" if result["success"] else "ERROR", condition=self._out())

        ptprint(f"\n  Repaired: {self.repaired}  |  Failed: {self.failed}  |  Skipped: {self.skipped}",
                "OK", condition=self._out())
        self._add_node("repairResults", True,
                       total=self.total,
                       repaired=self.repaired,
                       failed=self.failed,
                       skipped=self.skipped,
                       byMethod=self.by_method,
                       repairResults=self._results)

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"PHOTO REPAIR v{__version__}  |  Case: {self.case_id}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint("\nJPEG: byte-level repair  |  PNG: PIL resave  |  TIFF/RAW: not supported",
                "INFO", condition=self._out())

        decisions = self.load_decisions()
        if decisions is None:
            self.ptjsonlib.set_status("finished")
            return

        self.repair_all(decisions)

        success_rate = round(self.repaired / self.total * 100, 1) if self.total else None

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "totalAttempted": self.total,
            "repaired": self.repaired,
            "failed": self.failed,
            "skipped": self.skipped,
            "successRate": success_rate,
            "byMethod": self.by_method,
            "repairedDir": str(self.repaired_dir),
            "failedDir": str(self.failed_dir),
            "supportedFormats": ["JPEG (byte-level)", "PNG (PIL resave)"],
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": f"Photo repair complete - {self.repaired} repaired",
                "result": "SUCCESS" if self.repaired > 0 else "NO_REPAIRS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "Originals preserved; repairs applied to copies only",
            }
        ))

        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint("REPAIR COMPLETE", "OK", condition=self._out())
        ptprint(f"Repaired: {self.repaired}  |  Failed: {self.failed}  |  Skipped: {self.skipped}",
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
            "Forensic photo repair tool - ptlibs compliant",
            "Reads ATTEMPT_REPAIR decisions from ptrepairdecision output",
            "JPEG: byte-level repair (footer, header, segments, truncated)",
            "PNG: PIL resave  |  TIFF/RAW: not supported",
            "Originals never modified - copies written to <case_id>_repaired/",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
        {"usage": ["ptphotorepair <case-id> <decisions-file> [options]"]},
        {"usage_example": [
            "ptphotorepair CASE-001 /var/forensics/images/CASE-001_repair_decisions.json",
            "ptphotorepair CASE-001 /path/to/decisions.json --analyst 'Jane'",
            "ptphotorepair CASE-001 /path/to/decisions.json --dry-run",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["decisions-file", "", "Path to repair_decisions.json - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without modifying files"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "JPEG strategies: eoi_append | header_reconstruct | segment_strip | pil_reopen",
            "Failed repairs preserved in <case_id>_repair_failed/ for manual review",
            "Optional: pip install Pillow (required for truncated JPEG and PNG repair)",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("decisions_file")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-a", "--analyst",    default="Analyst")
    parser.add_argument("-j", "--json-out",   default=None)
    parser.add_argument("-q", "--quiet",      action="store_true")
    parser.add_argument("--dry-run",          action="store_true")
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
        tool = PtPhotoRepair(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if props.get("repaired", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())