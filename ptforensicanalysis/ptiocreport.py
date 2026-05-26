#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptiocreport - Indicators of Compromise consolidation report
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import DEFAULT_ANALYSIS_OUTPUT_DIR
except ImportError:
    from _constants import DEFAULT_ANALYSIS_OUTPUT_DIR

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptiocreport"


class PtIocReport(ForensicToolBase):

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.artefacts_file = Path(args.artefacts_file)
        self.hashes_file = Path(args.hashes_file) if args.hashes_file else None
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.file_hashes: List[Dict] = []
        self.ips: List[str] = []
        self.urls: List[str] = []
        self.domains: List[str] = []
        self.emails: List[str] = []
        self.reg_keys: List[Dict] = []

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({"artefactsFile": str(self.artefacts_file)})

    def _load_json(self, path: Path) -> Dict:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw.get("results", raw.get("result", raw))
        except Exception:
            return {}

    def load_network_artefacts(self) -> bool:
        self._print_header("STEP 1: Loading Network Artefacts")

        if not self.artefacts_file.exists() and not self.dry_run:
            return self._fail("networkArtefactsLoad", f"Artefacts file not found: {self.artefacts_file}")

        if self.dry_run:
            self._add_node("networkArtefactsLoad", True, dryRun=True)
            return True

        data = self._load_json(self.artefacts_file)
        props = data.get("properties", data)
        net = props.get("networkIndicators", {})

        self.ips = net.get("ipAddresses", [])
        self.urls = net.get("urls", [])
        self.domains = net.get("domains", [])
        self.emails = net.get("emails", [])
        self.reg_keys = props.get("registryPersistence", [])

        ptprint(f"  ✓ IPs:      {len(self.ips)}", "OK", condition=self._out())
        ptprint(f"  ✓ URLs:     {len(self.urls)}", "OK", condition=self._out())
        ptprint(f"  ✓ Domains:  {len(self.domains)}", "OK", condition=self._out())
        ptprint(f"  ✓ RegKeys:  {len(self.reg_keys)}", "OK", condition=self._out())

        self._add_node("networkArtefactsLoad", True, source=self.artefacts_file.name)
        return True

    def load_file_hashes(self) -> bool:
        self._print_header("STEP 2: Loading File Hashes")

        if not self.hashes_file:
            ptprint("  No hashes file provided - skipping", "TEXT", condition=self._out())
            return True

        if not self.hashes_file.exists() and not self.dry_run:
            ptprint(f"  ⚠ Hashes file not found: {self.hashes_file}", "WARNING", condition=self._out())
            return True

        if self.dry_run:
            self._add_node("fileHashesLoad", True, dryRun=True)
            return True

        for line in self.hashes_file.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and len(parts[0]) == 64:
                self.file_hashes.append({
                    "filename": Path(parts[1]).name,
                    "path": parts[1],
                    "sha256": parts[0],
                })

        ptprint(f"  ✓ File hashes loaded: {len(self.file_hashes)}", "OK", condition=self._out())
        for fh in self.file_hashes[:5]:
            ptprint(f"  • {fh['filename']}  |  {fh['sha256'][:16]}...", "TEXT", condition=self._out())

        self._add_node("fileHashesLoad", True,
            hashesLoaded=len(self.file_hashes),
            source=self.hashes_file.name)
        return True

    def run(self) -> bool:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"IOC REPORT v{__version__} | Case: {self.case_id}", "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.load_network_artefacts():
            self.ptjsonlib.set_status("finished")
            return False
        if not self.load_file_hashes():
            self.ptjsonlib.set_status("finished")
            return False

        total = (len(self.file_hashes) + len(self.ips) +
                 len(self.urls) + len(self.domains) + len(self.reg_keys))

        self._print_header("SUMMARY")
        ptprint(f"  File hashes:   {len(self.file_hashes)}", "TEXT", condition=self._out())
        ptprint(f"  IPs:           {len(self.ips)}", "TEXT", condition=self._out())
        ptprint(f"  URLs:          {len(self.urls)}", "TEXT", condition=self._out())
        ptprint(f"  Domains:       {len(self.domains)}", "TEXT", condition=self._out())
        ptprint(f"  Registry keys: {len(self.reg_keys)}", "TEXT", condition=self._out())
        ptprint(f"  TOTAL IoC:     {total}", "OK", condition=self._out())
        ptprint("\n  ⚠ YARA rule creation is manual - see step description.", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        ioc_report = {
            "caseId": self.case_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ioc": {
                "fileHashes": self.file_hashes,
                "networkIndicators": {
                    "ipAddresses": self.ips,
                    "urls": self.urls,
                    "domains": self.domains,
                    "emails": self.emails,
                },
                "hostIndicators": {
                    "registryPersistence": self.reg_keys,
                },
            },
            "totals": {
                "fileHashes": len(self.file_hashes),
                "ips": len(self.ips), "urls": len(self.urls),
                "domains": len(self.domains), "regKeys": len(self.reg_keys),
                "total": total,
            },
            "yaraRules": "MANUAL - create based on unique strings from static analysis",
        }

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-61", "MITRE ATT&CK"],
            "iocReport": ioc_report,
            "totalIoc": total,
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": f"IoC report generated - {total} indicators consolidated",
                "result": "SUCCESS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))
        self.ptjsonlib.set_status("finished")
        return True

    def save_report(self) -> Optional[str]:
        out = Path(self.args.json_out) if self.args.json_out \
            else self.output_dir / f"{self.case_id}_ioc.json"
        raw = self.ptjsonlib.get_result_json()
        out.write_text(raw, encoding="utf-8")
        ptprint(f"\n✓ IoC report saved: {out}", "OK", condition=True)
        return str(out)


def get_help() -> List[Dict]:
    return [
        {"description": [
            "IoC consolidation report - ptlibs compliant",
            "Loads artefacts from ptartefactextractor and optional hashes from ptstaticanalysis",
            "Consolidates file hashes, IPs, URLs, domains and registry keys into IoC JSON",
            "Output is ready for ptthreatintel and SIEM/IDS import",
            "YARA rule creation remains manual",
        ]},
        {"usage": ["ptiocreport <case-id> <artefacts-file> [options]"]},
        {"usage_example": [
            "ptiocreport MALWARE-2025-01-26-001 /var/forensics/analysis/MALWARE-2025-01-26-001_artefacts.json",
            "ptiocreport MALWARE-2025-01-26-001 artefacts.json --hashes-file hashes.txt",
            "ptiocreport MALWARE-2025-01-26-001 artefacts.json --json-out ioc.json",
        ]},
        {"options": [
            ["case-id", "", "Case identifier - REQUIRED"],
            ["artefacts-file", "", "Artefacts JSON from ptartefactextractor - REQUIRED"],
            ["-f", "--hashes-file", "<f>", "Hashes TXT from ptstaticanalysis (optional)"],
            ["-o", "--output-dir", "<d>", f"Output directory (default: {DEFAULT_ANALYSIS_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save IoC report to file (default: <output-dir>/<case-id>_ioc.json)"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without loading files"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "Exit 0 = success | Exit 99 = error | Exit 130 = Ctrl+C",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("artefacts_file")
    parser.add_argument("-f", "--hashes-file", default=None)
    parser.add_argument("-o", "--output-dir", default=DEFAULT_ANALYSIS_OUTPUT_DIR)
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
        tool = PtIocReport(args)
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