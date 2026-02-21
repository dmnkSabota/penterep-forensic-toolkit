#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptintegrityvalidation - Forensic photo integrity validation tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image, UnidentifiedImageError
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SCRIPTNAME         = "ptintegrityvalidation"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"
VALIDATE_TIMEOUT   = 30
FILE_TIMEOUT       = 10

MAGIC_BYTES: Dict[str, List[bytes]] = {
    "JPEG": [b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1",
             b"\xff\xd8\xff\xe2", b"\xff\xd8\xff\xe8", b"\xff\xd8\xff"],
    "PNG":  [b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"],
    "GIF":  [b"GIF87a", b"GIF89a"],
    "TIFF": [b"\x49\x49\x2a\x00", b"\x4d\x4d\x00\x2a"],
    "BMP":  [b"BM"],
    "WEBP": [b"RIFF"],
}

EXT_TO_MAGIC: Dict[str, str] = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "GIF",
    "tif": "TIFF", "tiff": "TIFF", "bmp": "BMP", "webp": "WEBP",
}

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

EXPECTED_INTEGRITY = {"fs_based": ">95 %", "carved": "70–85 %"}

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtIntegrityValidation:
    """
    Forensic photo integrity validation – ptlibs compliant.

    Pipeline: load master_catalog.json → check tools → per-file multi-tool
              validation (magic → file → identify → PIL → jpeginfo/pngcheck)
              → organise → JSON + text report.

    Decision: all pass → valid | ≥1 pass → corrupted | all fail → unrecoverable.
    READ-ONLY on source files (shutil.copy2 only).
    Compliant with ISO/IEC 10918-1, PNG ISO/IEC 15948:2004, NIST SP 800-86.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.consolidated_dir  = self.output_dir / f"{self.case_id}_consolidated"
        self.validation_base   = self.output_dir / f"{self.case_id}_validation"
        self.valid_dir         = self.validation_base / "valid"
        self.corrupted_dir     = self.validation_base / "corrupted"
        self.unrecoverable_dir = self.validation_base / "unrecoverable"

        self.catalog: Optional[Dict] = None
        self._tools:  Dict[str, bool] = {}

        self._results:     List[Dict] = []
        self._need_repair: List[Dict] = []

        self._s: Dict[str, Any] = {
            "total": 0, "valid": 0, "corrupted": 0, "unrecoverable": 0,
            "by_format": {}, "by_source": {}, "corruption_types": {},
        }

        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "totalFiles": 0, "validFiles": 0, "corruptedFiles": 0,
            "unrecoverableFiles": 0, "integrityScore": 0.0,
            "filesNeedingRepair": 0, "byFormat": {}, "bySource": {},
            "corruptionTypes": {}, "dryRun": self.dry_run,
        })
        ptprint(f"Initialized: case={self.case_id}", "INFO", condition=not self.args.json)

    # --- helpers ------------------------------------------------------------

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type, properties={"success": success, **kwargs}
        ))

    def _fail(self, node_type: str, msg: str) -> bool:
        ptprint(msg, "ERROR", condition=not self.args.json)
        self._add_node(node_type, False, error=msg)
        return False

    def _run_command(self, cmd: List[str], timeout: int = 30) -> Dict[str, Any]:
        if self.dry_run:
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

    def _fp(self, relative: str) -> Path:
        return self.consolidated_dir / relative

    # --- phases -------------------------------------------------------------

    def load_catalog(self) -> bool:
        """Load master_catalog.json from the consolidated directory."""
        ptprint("\n[1/4] Loading Master Catalog", "TITLE", condition=not self.args.json)

        f = self.consolidated_dir / "master_catalog.json"
        if not f.exists():
            return self._fail("catalogLoad", f"{f.name} not found – run consolidation first.")
        try:
            self.catalog = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            return self._fail("catalogLoad", f"Cannot read catalog: {exc}")

        s = self.catalog.get("summary", {})
        self._s["total"] = s.get("totalFiles") or s.get("total_files") or len(self.catalog.get("files", []))
        ptprint(f"Loaded: {f.name} | files={self._s['total']}", "OK", condition=not self.args.json)
        self.ptjsonlib.add_properties({"totalFiles": self._s["total"]})
        self._add_node("catalogLoad", True, totalFiles=self._s["total"], sourceFile=str(f))
        return True

    def check_tools(self) -> bool:
        """Verify PIL (required) and optional tools (identify, file, jpeginfo, pngcheck)."""
        ptprint("\n[2/4] Checking Validation Tools", "TITLE", condition=not self.args.json)

        self._tools["pil"] = PIL_AVAILABLE or self.dry_run
        ptprint(f"  {'✓' if self._tools['pil'] else '✗'} PIL/Pillow"
                + ("" if self._tools["pil"] else " – pip install Pillow --break-system-packages"),
                "OK" if self._tools["pil"] else "ERROR", condition=not self.args.json)

        for tool, desc in (("identify", "ImageMagick"), ("file", "MIME detection"),
                            ("jpeginfo", "JPEG validation"), ("pngcheck", "PNG validation")):
            found = self._run_command(["which", tool], timeout=5)["success"]
            self._tools[tool] = found
            ptprint(f"  {'✓' if found else '⚠'} {tool}: {desc}",
                    "OK" if found else "WARNING", condition=not self.args.json)

        self._add_node("toolsCheck", self._tools["pil"], tools=self._tools)
        return self._tools["pil"]

    # --- validation helpers -------------------------------------------------

    def _check_magic(self, filepath: Path, ext: str) -> bool:
        magic_key = EXT_TO_MAGIC.get(ext.lower())
        if not magic_key:
            return True
        try:
            header = filepath.read_bytes()[:16]
            return any(header.startswith(sig) for sig in MAGIC_BYTES[magic_key])
        except Exception:
            return False

    def _validate_file_cmd(self, fp: Path) -> Optional[Dict]:
        if not self._tools.get("file"):
            return None
        r = self._run_command(["file", "-b", "--mime-type", str(fp)], timeout=FILE_TIMEOUT)
        if not r["success"]:
            return None
        ok = r["stdout"].startswith("image/")
        return {"success": ok, "tool": "file", "mimeType": r["stdout"],
                "error": None if ok else f"Not image MIME: {r['stdout']}"}

    def _validate_imagemagick(self, fp: Path) -> Optional[Dict]:
        if not self._tools.get("identify"):
            return None
        r = self._run_command(["identify", str(fp)], timeout=VALIDATE_TIMEOUT)
        return {"success": r["success"], "tool": "imagemagick",
                "error": r["stderr"][:200] if not r["success"] else None}

    def _validate_pil(self, fp: Path) -> Dict:
        if self.dry_run:
            return {"success": True, "tool": "pil", "width": 1920, "height": 1080, "mode": "RGB"}
        try:
            img = Image.open(fp)
            img.verify()
            img = Image.open(fp)   # verify() closes file
            img.load()
            w, h = img.size
            if w == 0 or h == 0:
                return {"success": False, "tool": "pil", "error": "0×0 dimensions",
                        "corruptionType": "corrupt_data"}
            return {"success": True, "tool": "pil", "width": w, "height": h, "mode": img.mode}
        except Exception as exc:
            e = str(exc).lower()
            ctype = ("truncated"        if "truncated" in e or "premature end" in e else
                     "invalid_header"   if "cannot identify" in e or "cannot decode" in e else
                     "corrupt_segments" if "corrupt" in e or "broken" in e else
                     "corrupt_data")
            return {"success": False, "tool": "pil", "error": str(exc)[:200], "corruptionType": ctype}

    def _validate_format_specific(self, fp: Path, ext: str) -> Optional[Dict]:
        """Run jpeginfo for JPEG or pngcheck for PNG."""
        if ext in ("jpg", "jpeg") and self._tools.get("jpeginfo"):
            r = self._run_command(["jpeginfo", "-c", str(fp)], timeout=VALIDATE_TIMEOUT)
            if r["success"]:
                return {"success": True, "tool": "jpeginfo"}
            detail = (r["stdout"] + " " + r["stderr"]).strip()[:200]
            return {"success": False, "tool": "jpeginfo", "error": detail,
                    "corruptionType": "truncated" if "truncated" in detail.lower() else "corrupt_segments"}
        if ext == "png" and self._tools.get("pngcheck"):
            r = self._run_command(["pngcheck", "-v", str(fp)], timeout=VALIDATE_TIMEOUT)
            if r["success"]:
                return {"success": True, "tool": "pngcheck"}
            detail = (r["stdout"] + " " + r["stderr"]).strip()[:200]
            return {"success": False, "tool": "pngcheck", "error": detail,
                    "corruptionType": "truncated" if "truncated" in detail.lower() else "corrupt_segments"}
        return None

    def _validate_single(self, fi: Dict) -> Dict:
        """Full multi-tool pipeline for one file. Returns status + details."""
        path_rel = fi.get("path") or fi.get("consolidated_path", "")
        fp       = self._fp(path_rel)
        ext      = (fi.get("format") or fi.get("extension") or
                    Path(fi.get("filename", "")).suffix.lstrip(".")).lower()

        try:
            size = fp.stat().st_size if not self.dry_run else 1024
        except OSError:
            return {"status": "unrecoverable", "error": "File not found",
                    "magicValid": False, "toolsPassed": 0, "toolsTotal": 0}

        if size == 0:
            return {"status": "unrecoverable", "error": "Empty file",
                    "magicValid": False, "toolsPassed": 0, "toolsTotal": 0}

        magic_ok = self._check_magic(fp, ext) if not self.dry_run else True

        tool_results = [r for r in (
            self._validate_file_cmd(fp),
            self._validate_imagemagick(fp),
            self._validate_pil(fp),
            self._validate_format_specific(fp, ext),
        ) if r is not None]

        passed = sum(1 for r in tool_results if r.get("success"))
        total  = len(tool_results)
        base   = {"fileSize": size, "magicValid": magic_ok,
                  "toolsPassed": passed, "toolsTotal": total, "toolResults": tool_results}

        if passed == total and magic_ok:
            pil = next((r for r in tool_results if r.get("tool") == "pil"), {})
            return {**base, "status": "valid",
                    "width": pil.get("width"), "height": pil.get("height"), "mode": pil.get("mode")}

        if passed > 0:
            ctype = "invalid_header" if not magic_ok else "unknown"
            for r in tool_results:
                if not r.get("success") and r.get("corruptionType"):
                    ctype = r["corruptionType"]; break
            return {**base, "status": "corrupted", "corruptionType": ctype,
                    "errors": [r["error"] for r in tool_results if not r.get("success") and r.get("error")]}

        return {**base, "status": "unrecoverable", "corruptionType": "false_positive",
                "errors": [r["error"] for r in tool_results if r.get("error")]}

    def validate_all_files(self) -> None:
        """Iterate catalog and validate every file."""
        ptprint("\n[3/4] Validating Files", "TITLE", condition=not self.args.json)

        files = self.catalog.get("files", [])
        total = len(files)

        for idx, fi in enumerate(files, 1):
            if idx % 50 == 0 or idx == total:
                ptprint(f"  {idx}/{total} ({idx*100//total}%)",
                        "INFO", condition=not self.args.json)

            v      = self._validate_single(fi)
            fmt    = (fi.get("format") or fi.get("extension") or "unknown").lower()
            source = fi.get("recoveryMethod") or fi.get("recovery_method") or "unknown"
            status = v["status"]

            entry: Dict[str, Any] = {
                "fileId": fi.get("id"), "filename": fi.get("filename"),
                "path": fi.get("path"), "format": fmt,
                "recoveryMethod": source, "status": status,
                "fileSize": v.get("fileSize"), "magicValid": v.get("magicValid"),
                "toolsPassed": v.get("toolsPassed"), "toolsTotal": v.get("toolsTotal"),
            }

            if status == "valid":
                self._s["valid"] += 1
                entry.update({"width": v.get("width"), "height": v.get("height"), "mode": v.get("mode")})
            elif status == "corrupted":
                self._s["corrupted"] += 1
                ctype = v.get("corruptionType", "unknown")
                info  = CORRUPTION_TYPES.get(ctype, CORRUPTION_TYPES["unknown"])
                entry.update({"corruptionType": ctype, "errors": v.get("errors", []),
                              "repairInfo": {"level": info["level"], "repairable": info["repairable"],
                                            "technique": info["technique"]}})
                if info["repairable"] is not False:
                    self._need_repair.append({"fileId": fi.get("id"), "filename": fi.get("filename"),
                                              "corruptionType": ctype, **info})
                self._s["corruption_types"][ctype] = self._s["corruption_types"].get(ctype, 0) + 1
            else:
                self._s["unrecoverable"] += 1
                ct = v.get("corruptionType", "false_positive")
                self._s["corruption_types"][ct] = self._s["corruption_types"].get(ct, 0) + 1
                entry["errors"] = v.get("errors", [])

            for bucket, key in ((self._s["by_format"], fmt), (self._s["by_source"], source)):
                if key not in bucket:
                    bucket[key] = {"total": 0, "valid": 0, "corrupted": 0, "unrecoverable": 0}
                bucket[key]["total"] += 1
                bucket[key][status]  += 1

            self._results.append(entry)

        integrity = round(self._s["valid"] / max(total, 1) * 100, 2)
        ptprint(f"Valid: {self._s['valid']} | Corrupted: {self._s['corrupted']} | "
                f"Unrecoverable: {self._s['unrecoverable']} | Score: {integrity}%",
                "OK", condition=not self.args.json)
        self._add_node("fileValidation", True,
                       validFiles=self._s["valid"], corruptedFiles=self._s["corrupted"],
                       unrecoverableFiles=self._s["unrecoverable"],
                       integrityScore=integrity, filesNeedingRepair=len(self._need_repair),
                       corruptionTypes=self._s["corruption_types"])

    def organise_files(self) -> None:
        """Copy files into valid / corrupted / unrecoverable directories."""
        ptprint("\n[4/4] Organising Files", "TITLE", condition=not self.args.json)

        dest_map = {"valid": self.valid_dir, "corrupted": self.corrupted_dir,
                    "unrecoverable": self.unrecoverable_dir}

        for entry in self._results:
            src = self._fp(entry.get("path", ""))
            if not src.exists() and not self.dry_run:
                continue
            dst = dest_map.get(entry["status"], self.unrecoverable_dir) / entry["filename"]
            if not self.dry_run and dst.exists():
                stem, sfx, n = dst.stem, dst.suffix, 1
                while dst.exists():
                    dst = dst.parent / f"{stem}_{n}{sfx}"; n += 1
            if not self.dry_run:
                try:
                    shutil.copy2(src, dst)
                except Exception as exc:
                    ptprint(f"  Copy failed {entry['filename']}: {exc}",
                            "WARNING", condition=not self.args.json)

        ptprint("Files organised.", "OK", condition=not self.args.json)
        self._add_node("filesOrganised", True, validDir=str(self.valid_dir),
                       corruptedDir=str(self.corrupted_dir),
                       unrecoverableDir=str(self.unrecoverable_dir))

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full validation pipeline."""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"PHOTO INTEGRITY VALIDATION v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_catalog():
            self.ptjsonlib.set_status("finished"); return
        if not self.check_tools():
            self.ptjsonlib.set_status("finished"); return

        # Create directory tree inline
        if not self.dry_run:
            for d in (self.valid_dir, self.corrupted_dir, self.unrecoverable_dir):
                d.mkdir(parents=True, exist_ok=True)

        self.validate_all_files()
        self.organise_files()

        s = self._s
        integrity = round(s["valid"] / max(s["total"], 1) * 100, 2)
        self.ptjsonlib.add_properties({
            "validFiles": s["valid"], "corruptedFiles": s["corrupted"],
            "unrecoverableFiles": s["unrecoverable"], "integrityScore": integrity,
            "filesNeedingRepair": len(self._need_repair),
            "byFormat": s["by_format"], "bySource": s["by_source"],
            "corruptionTypes": s["corruption_types"],
        })

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("VALIDATION COMPLETED", "OK", condition=not self.args.json)
        ptprint(f"Score: {integrity}% | Valid: {s['valid']} | "
                f"Corrupted: {s['corrupted']} | Unrecoverable: {s['unrecoverable']} | "
                f"For repair: {len(self._need_repair)}",
                "INFO", condition=not self.args.json)
        ptprint("Next: Photo repair (corrupted files) or final report delivery.",
                "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        self.ptjsonlib.set_status("finished")

    def _write_text_report(self, props: Dict) -> Path:
        """Write VALIDATION_REPORT.txt to validation_base."""
        integrity = props.get("integrityScore", 0.0)
        quality = ("EXCELLENT – ready for delivery"   if integrity >= 95 else
                   "GOOD – most photos usable"         if integrity >= 85 else
                   "FAIR – repair recommended"         if integrity >= 70 else
                   "POOR – source media badly damaged")
        sep = "=" * 70
        lines = [sep, "PHOTO INTEGRITY VALIDATION REPORT", sep, "",
                 f"Case ID:   {self.case_id}",
                 f"Timestamp: {props.get('timestamp','')}", "",
                 "SUMMARY:",
                 f"  Total files:          {props.get('totalFiles',0)}",
                 f"  Valid:                {props.get('validFiles',0)} ({integrity}%)",
                 f"  Corrupted:            {props.get('corruptedFiles',0)}",
                 f"  Unrecoverable:        {props.get('unrecoverableFiles',0)}",
                 f"  Files needing repair: {props.get('filesNeedingRepair',0)}",
                 f"\nINTEGRITY SCORE: {quality}", "", "BY FORMAT:"]
        for fmt, d in sorted(self._s["by_format"].items()):
            pct = d["valid"] / d["total"] * 100 if d["total"] else 0
            lines.append(f"  {fmt:8s}: {d['valid']}/{d['total']} valid ({pct:.1f}%)")
        lines += ["", "BY SOURCE:"]
        for src, d in sorted(self._s["by_source"].items()):
            pct = d["valid"] / d["total"] * 100 if d["total"] else 0
            exp = EXPECTED_INTEGRITY.get(src, "?")
            lines.append(f"  {src}: {d['valid']}/{d['total']} valid ({pct:.1f}%)  expected {exp}")
        if self._s["corruption_types"]:
            lines += ["", "CORRUPTION TYPES:"]
            for ct, cnt in sorted(self._s["corruption_types"].items(), key=lambda x: -x[1]):
                info = CORRUPTION_TYPES.get(ct, {})
                lines.append(f"  {ct}: {cnt}  (L{info.get('level','?')}, repairable={info.get('repairable','?')})")
        if self._need_repair:
            lines += ["", f"FILES FOR REPAIR (first 30 of {len(self._need_repair)}):"]
            lines += [f"  [{r['corruptionType']}] {r['filename']}: {r['technique']}"
                      for r in self._need_repair[:30]]
        txt = self.validation_base / "VALIDATION_REPORT.txt"
        self.validation_base.mkdir(parents=True, exist_ok=True)
        txt.write_text("\n".join(lines), encoding="utf-8")
        return txt

    def save_report(self) -> Optional[str]:
        """Save validation_report.json and VALIDATION_REPORT.txt."""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        json_file = self.output_dir / f"{self.case_id}_validation_report.json"
        report = {"result": json.loads(self.ptjsonlib.get_result_json()),
                  "validationResults": self._results,
                  "filesNeedingRepair": self._need_repair}
        if not self.dry_run:
            json_file.write_text(json.dumps(report, indent=2,
                                            ensure_ascii=False, default=str), encoding="utf-8")
        ptprint(f"JSON report: {json_file.name}", "OK", condition=not self.args.json)

        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        if not self.dry_run:
            txt = self._write_text_report(props)
            ptprint(f"Text report: {txt.name}", "OK", condition=not self.args.json)
        return str(json_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_help() -> List:
    return [
        {"description": [
            "Forensic photo integrity validation – ptlibs compliant",
            "Multi-tool: magic bytes → file → ImageMagick → PIL → jpeginfo/pngcheck",
            "Classifies files as valid / corrupted / unrecoverable",
        ]},
        {"usage": ["ptintegrityvalidation <case-id> [options]"]},
        {"usage_example": [
            "ptintegrityvalidation PHOTO-2025-001",
            "ptintegrityvalidation CASE-042 --json",
            "ptintegrityvalidation TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate without reading files"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"notes": [
            "PIL/Pillow required; identify/file/jpeginfo/pngcheck optional",
            "Decision: all pass → valid | ≥1 pass → corrupted | all fail → unrecoverable",
            "L1 truncated | L2 invalid_header/corrupt_segments | L3 corrupt_data | L4 fragmented | L5 false_positive",
            "Expected: fs_based >95% | carved 70–85%",
            "READ-ONLY on source files (copy2 only)",
            "Compliant with ISO/IEC 10918-1, PNG ISO/IEC 15948:2004, NIST SP 800-86",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-v", "--verbose",    action="store_true")
    parser.add_argument("-q", "--quiet",      action="store_true")
    parser.add_argument("--dry-run",          action="store_true")
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
        tool = PtIntegrityValidation(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("integrityScore", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())