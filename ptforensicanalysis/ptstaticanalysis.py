#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptstaticanalysis - Static malware analysis on forensic image
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import re
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
        DEFAULT_ANALYSIS_OUTPUT_DIR, DEFAULT_MOUNT_BASE,
        SUSPICIOUS_EXTENSIONS, SUSPICIOUS_SCAN_PATHS,
        PACKER_KEYWORDS, OBFUSCATION_KEYWORDS,
        STATIC_STRINGS_TIMEOUT, MAX_SUSPICIOUS_FILES,
    )
except ImportError:
    from _constants import (
        DEFAULT_ANALYSIS_OUTPUT_DIR, DEFAULT_MOUNT_BASE,
        SUSPICIOUS_EXTENSIONS, SUSPICIOUS_SCAN_PATHS,
        PACKER_KEYWORDS, OBFUSCATION_KEYWORDS,
        STATIC_STRINGS_TIMEOUT, MAX_SUSPICIOUS_FILES,
    )

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptstaticanalysis"


class PtStaticAnalysis(ForensicToolBase):

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.image_path = Path(args.image)
        self.output_dir = Path(args.output_dir)
        self.mount_dir = Path(args.mount_dir) / self.case_id
        self.offset_bytes = args.offset * 512
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.mounted: bool = False
        self.suspicious_files: List[Dict] = []
        self.strings_path: Optional[Path] = None
        self.hashes_path: Optional[Path] = None
        self.dynamic_needed: bool = False
        self.dynamic_reason: str = ""

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})

    def check_prerequisites(self) -> bool:
        self._print_header("STEP 1: Prerequisites")

        if not self.image_path.exists() and not self.dry_run:
            return self._fail("prerequisitesCheck", f"Image not found: {self.image_path}")

        for cmd in ("mount", "find", "strings", "file", "sha256sum"):
            if not self._check_command(cmd) and not self.dry_run:
                return self._fail("prerequisitesCheck", f"Required command not found: {cmd}")
            ptprint(f"  ✓ {cmd}", "OK", condition=self._out())

        for cmd in ("exiftool", "objdump"):
            available = self._check_command(cmd)
            ptprint(f"  {'✓' if available else '⚠ optional'} {cmd}",
                    "OK" if available else "WARNING", condition=self._out())

        self._add_node("prerequisitesCheck", True)
        return True

    def mount_image(self) -> bool:
        self._print_header("STEP 2: Mounting Image (read-only)")

        if self.dry_run:
            self.mounted = True
            self._add_node("mountImage", True, dryRun=True)
            return True

        self.mount_dir.mkdir(parents=True, exist_ok=True)
        mount_opts = f"ro,loop,offset={self.offset_bytes},noexec"
        r = self._run_command(
            ["mount", "-o", mount_opts, str(self.image_path), str(self.mount_dir)],
            timeout=30)
        if not r["success"]:
            return self._fail("mountImage", f"Mount failed: {r['stderr']}")

        self.mounted = True
        ptprint(f"  ✓ Mounted read-only at {self.mount_dir}", "OK", condition=self._out())
        self._add_node("mountImage", True, mountPoint=str(self.mount_dir))
        return True

    def find_suspicious_files(self) -> bool:
        self._print_header("STEP 3: Finding Suspicious Executables")

        if self.dry_run:
            self._add_node("fileScan", True, dryRun=True)
            return True

        found: List[str] = []

        for sp in SUSPICIOUS_SCAN_PATHS:
            scan_root = self.mount_dir / sp
            if not scan_root.exists():
                continue
            for ext in SUSPICIOUS_EXTENSIONS:
                r = self._run_command(
                    ["find", str(scan_root), "-type", "f", "-iname", ext, "-not", "-size", "0"],
                    timeout=60)
                if r["success"] and r["stdout"]:
                    found.extend(r["stdout"].splitlines())

        r = self._run_command(
            ["find", str(self.mount_dir), "-type", "f", "-executable",
             "-not", "-path", "*/proc/*", "-not", "-path", "*/sys/*"],
            timeout=120)
        if r["success"] and r["stdout"]:
            found.extend(r["stdout"].splitlines())

        found = list(set(found))
        ptprint(f"\n  Found {len(found)} candidate files", "TEXT", condition=self._out())

        for fp in found[:MAX_SUSPICIOUS_FILES]:
            p = Path(fp)
            r1 = self._run_command(["file", "-b", fp], timeout=10)
            r2 = self._run_command(["sha256sum", fp], timeout=30)
            ftype = r1["stdout"] if r1["success"] else "unknown"
            fhash = r2["stdout"].split()[0] if r2["success"] else ""
            fsize = p.stat().st_size if p.exists() else 0
            self.suspicious_files.append({
                "path": fp, "name": p.name,
                "type": ftype, "sha256": fhash, "size": fsize,
            })
            ptprint(f"  • {p.name}  |  {ftype[:60]}", "TEXT", condition=self._out())

        self._add_node("fileScan", True, filesFound=len(self.suspicious_files))
        return True

    def extract_strings(self) -> bool:
        self._print_header("STEP 4: String Extraction")
        self.strings_path = self.output_dir / f"{self.case_id}_strings.txt"
        self.hashes_path = self.output_dir / f"{self.case_id}_suspicious_hashes.txt"

        if self.dry_run:
            self._add_node("stringsExtraction", True, dryRun=True)
            return True

        with open(self.strings_path, "w", encoding="utf-8", errors="replace") as sf, \
             open(self.hashes_path, "w", encoding="utf-8") as hf:
            for entry in self.suspicious_files:
                fp = entry["path"]
                sf.write(f"\n{'=' * 60}\n{fp}\n{'=' * 60}\n")
                r = self._run_command(["strings", "-a", "-n", "8", fp], timeout=STATIC_STRINGS_TIMEOUT)
                if r["success"]:
                    sf.write(r["stdout"] + "\n")
                r = self._run_command(["strings", "-a", "-n", "8", "-e", "l", fp], timeout=STATIC_STRINGS_TIMEOUT)
                if r["success"] and r["stdout"]:
                    sf.write("[UNICODE]\n" + r["stdout"] + "\n")
                if entry["sha256"]:
                    hf.write(f"{entry['sha256']}  {fp}\n")

        ptprint(f"  ✓ Strings: {self.strings_path.name}", "OK", condition=self._out())
        ptprint(f"  ✓ Hashes:  {self.hashes_path.name}", "OK", condition=self._out())
        self._add_node("stringsExtraction", True,
            stringsFile=str(self.strings_path),
            hashesFile=str(self.hashes_path))
        return True

    def recommend_dynamic(self) -> None:
        self._print_header("STEP 5: Dynamic Analysis Recommendation")

        if self.dry_run or not self.strings_path or not self.strings_path.exists():
            ptprint("  [DRY-RUN] Recommendation skipped.", "INFO", condition=self._out())
            return

        content = self.strings_path.read_text(encoding="utf-8", errors="replace").lower()
        lines = [l for l in content.splitlines() if len(l) > 8]
        ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', content)
        urls = re.findall(r'https?://\S+', content)

        has_packer = any(kw in content for kw in PACKER_KEYWORDS)
        has_obfus = any(kw in content for kw in OBFUSCATION_KEYWORDS)
        low_strings = len(lines) < 50
        has_ioc = bool(ips or urls)

        if has_packer:
            self.dynamic_needed = True
            self.dynamic_reason = "Packer detected - static analysis insufficient"
        elif low_strings:
            self.dynamic_needed = True
            self.dynamic_reason = "Low readable string count - likely obfuscated"
        elif has_obfus:
            self.dynamic_needed = True
            self.dynamic_reason = "Obfuscation indicators detected (Base64/XOR)"
        elif has_ioc:
            self.dynamic_needed = False
            self.dynamic_reason = f"Clear IoC in static analysis ({len(ips)} IPs, {len(urls)} URLs)"
        else:
            self.dynamic_needed = True
            self.dynamic_reason = "Insufficient static artefacts - dynamic analysis recommended"

        sym = "⚠ DYNAMIC ANALYSIS RECOMMENDED" if self.dynamic_needed else "✓ STATIC ANALYSIS SUFFICIENT"
        lv = "WARNING" if self.dynamic_needed else "OK"
        ptprint(f"\n  {sym}", lv, condition=self._out(), colortext=True)
        ptprint(f"  Reason: {self.dynamic_reason}", lv, condition=self._out())

        self._add_node("dynamicRecommendation", True,
            dynamicNeeded=self.dynamic_needed,
            reason=self.dynamic_reason,
            ipsFound=len(ips),
            urlsFound=len(urls))

    def unmount_image(self) -> None:
        if not self.mounted or self.dry_run:
            return
        r = self._run_command(["umount", str(self.mount_dir)], timeout=30)
        if r["success"]:
            ptprint("\n  ✓ Image unmounted", "OK", condition=self._out())
        else:
            ptprint(f"\n  ⚠ Unmount failed: {r['stderr']}", "WARNING", condition=self._out())

    def run(self) -> bool:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"STATIC ANALYSIS v{__version__} | Case: {self.case_id}", "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        try:
            if not self.check_prerequisites():
                return False
            if not self.mount_image():
                return False
            if not self.find_suspicious_files():
                return False
            if not self.extract_strings():
                return False
            self.recommend_dynamic()
            return True
        finally:
            self.unmount_image()
            self.ptjsonlib.add_properties({
                "compliance": ["NIST SP 800-86", "NIST SP 800-83"],
                "suspiciousFiles": self.suspicious_files,
                "stringsFile": str(self.strings_path) if self.strings_path else None,
                "hashesFile": str(self.hashes_path) if self.hashes_path else None,
                "dynamicNeeded": self.dynamic_needed,
                "dynamicReason": self.dynamic_reason,
                "totalFilesAnalyzed": len(self.suspicious_files),
            })
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "chainOfCustodyEntry",
                properties={
                    "action": (
                        f"Static analysis complete - {len(self.suspicious_files)} suspicious files, "
                        f"dynamic analysis: {'YES' if self.dynamic_needed else 'NO'}"
                    ),
                    "result": "SUCCESS",
                    "analyst": self.analyst,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ))
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
            "Static malware analysis on forensic image - ptlibs compliant",
            "Mounts image read-only, finds suspicious executables, extracts strings,",
            "computes SHA-256 and recommends whether dynamic analysis is needed.",
            "All operations are READ-ONLY on the forensic image.",
            "Compliant with NIST SP 800-86 and NIST SP 800-83 Rev. 1.",
        ]},
        {"usage": ["ptstaticanalysis <case-id> <image> [options]"]},
        {"usage_example": [
            "ptstaticanalysis MALWARE-2025-01-26-001 /var/forensics/images/MALWARE-2025-01-26-001.dd",
            "ptstaticanalysis MALWARE-2025-01-26-001 /path/to/image.dd --analyst 'Jan Novak'",
            "ptstaticanalysis MALWARE-2025-01-26-001 /path/to/image.dd --json-out static.json",
            "ptstaticanalysis MALWARE-2025-01-26-001 /path/to/image.dd --dry-run",
        ]},
        {"options": [
            ["case-id", "", "Case identifier - REQUIRED"],
            ["image", "", "Path to forensic image (.dd/.raw) - REQUIRED"],
            ["--offset", "<n>", "Partition offset in sectors (default: 0)"],
            ["-o", "--output-dir", "<d>", f"Output directory (default: {DEFAULT_ANALYSIS_OUTPUT_DIR})"],
            ["-m", "--mount-dir", "<d>", f"Mount base directory (default: {DEFAULT_MOUNT_BASE})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without accessing the image"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "Image mounted read-only with noexec flag - no code is executed",
            "Image automatically unmounted after analysis",
            "Outputs: strings file, hashes file, JSON report with dynamic recommendation",
            "Exit 0 = success | Exit 99 = error | Exit 130 = Ctrl+C",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("image")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("-o", "--output-dir", default=DEFAULT_ANALYSIS_OUTPUT_DIR)
    parser.add_argument("-m", "--mount-dir", default=DEFAULT_MOUNT_BASE)
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
        tool = PtStaticAnalysis(args)
        ok = tool.run()
        tool.save_report()
        return 0 if ok else 99
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())