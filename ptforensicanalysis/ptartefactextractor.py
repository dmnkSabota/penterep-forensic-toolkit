#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptartefactextractor - Forensic artefact extraction (IoC consolidation)
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import (
        DEFAULT_ANALYSIS_OUTPUT_DIR,
        PRIVATE_IP_PREFIXES, WIN_AUTOSTART_PATHS,
        PCAP_TIMEOUT, REGISTRY_TIMEOUT,
    )
except ImportError:
    from _constants import (
        DEFAULT_ANALYSIS_OUTPUT_DIR,
        PRIVATE_IP_PREFIXES, WIN_AUTOSTART_PATHS,
        PCAP_TIMEOUT, REGISTRY_TIMEOUT,
    )

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptartefactextractor"

RE_IP = re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b')
RE_URL = re.compile(r'https?://[^\s"\'<>]+', re.IGNORECASE)
RE_DOMAIN = re.compile(
    r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)'
    r'+(?:com|net|org|io|ru|cn|de|uk|info|biz|xyz|top|site)\b',
    re.IGNORECASE)
RE_EMAIL = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


class PtArtefactExtractor(ForensicToolBase):

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.strings_file = Path(args.strings_file)
        self.pcap_file = Path(args.pcap) if args.pcap else None
        self.mount_path = Path(args.mount_path) if args.mount_path else None
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.ips: List[str] = []
        self.urls: List[str] = []
        self.domains: List[str] = []
        self.emails: List[str] = []
        self.reg_keys: List[Dict] = []

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({"stringsFile": str(self.strings_file)})

    def _is_public_ip(self, ip: str) -> bool:
        return not any(ip.startswith(p) for p in PRIVATE_IP_PREFIXES)

    def extract_from_strings(self) -> bool:
        self._print_header("STEP 1: Network Indicators from Strings")

        if not self.strings_file.exists() and not self.dry_run:
            return self._fail("stringsExtraction", f"Strings file not found: {self.strings_file}")

        if self.dry_run:
            self._add_node("stringsExtraction", True, dryRun=True)
            return True

        content = self.strings_file.read_text(encoding="utf-8", errors="replace")

        self.ips = sorted(ip for ip in set(RE_IP.findall(content)) if self._is_public_ip(ip))
        self.urls = sorted(set(RE_URL.findall(content)))

        url_hosts: Set[str] = {u.split("/")[2] for u in self.urls if "/" in u}
        self.domains = sorted(d for d in set(RE_DOMAIN.findall(content)) if d not in url_hosts)
        self.emails = sorted(set(RE_EMAIL.findall(content)))

        ptprint(f"  ✓ IPs:     {len(self.ips)}", "OK", condition=self._out())
        ptprint(f"  ✓ URLs:    {len(self.urls)}", "OK", condition=self._out())
        ptprint(f"  ✓ Domains: {len(self.domains)}", "OK", condition=self._out())
        ptprint(f"  ✓ Emails:  {len(self.emails)}", "OK", condition=self._out())
        if self.ips:
            ptprint(f"\n  Sample IPs: {', '.join(self.ips[:5])}", "TEXT", condition=self._out())

        self._add_node("stringsExtraction", True,
            ipsFound=len(self.ips), urlsFound=len(self.urls), domainsFound=len(self.domains))
        return True

    def extract_from_pcap(self) -> bool:
        self._print_header("STEP 2: Network Indicators from PCAP")

        if not self.pcap_file:
            ptprint("  No PCAP provided - skipping", "TEXT", condition=self._out())
            return True

        if not self.pcap_file.exists() and not self.dry_run:
            ptprint(f"  ⚠ PCAP not found: {self.pcap_file}", "WARNING", condition=self._out())
            return True

        if not self._check_command("tshark"):
            ptprint("  ⚠ tshark not available - install: apt-get install tshark", "WARNING", condition=self._out())
            return True

        if self.dry_run:
            self._add_node("pcapExtraction", True, dryRun=True)
            return True

        r = self._run_command(
            ["tshark", "-r", str(self.pcap_file), "-T", "fields", "-e", "ip.dst", "-Y", "ip"],
            timeout=PCAP_TIMEOUT)
        if r["success"] and r["stdout"]:
            pcap_ips = [ip for ip in set(r["stdout"].splitlines()) if ip and self._is_public_ip(ip)]
            self.ips = sorted(set(self.ips + pcap_ips))
            ptprint(f"  ✓ PCAP IPs added: {len(pcap_ips)}", "OK", condition=self._out())

        r = self._run_command(
            ["tshark", "-r", str(self.pcap_file), "-T", "fields", "-e", "dns.qry.name",
             "-Y", "dns.flags.response == 0"],
            timeout=PCAP_TIMEOUT)
        if r["success"] and r["stdout"]:
            pcap_domains = [d for d in set(r["stdout"].splitlines()) if d]
            self.domains = sorted(set(self.domains + pcap_domains))
            ptprint(f"  ✓ PCAP DNS queries added: {len(pcap_domains)}", "OK", condition=self._out())

        self._add_node("pcapExtraction", True)
        return True

    def extract_registry(self) -> bool:
        self._print_header("STEP 3: Registry Persistence Keys")

        if not self.mount_path:
            ptprint("  No mount path provided - skipping", "TEXT", condition=self._out())
            return True

        if not self._check_command("reglookup"):
            ptprint("  ⚠ reglookup not available - install: apt-get install libregf-tools", "WARNING", condition=self._out())
            return True

        if self.dry_run:
            self._add_node("registryExtraction", True, dryRun=True)
            return True

        hive = self.mount_path / "Windows/System32/config/SOFTWARE"
        if not hive.exists():
            ptprint(f"  ⚠ SOFTWARE hive not found at {hive}", "WARNING", condition=self._out())
            return True

        for reg_path in WIN_AUTOSTART_PATHS:
            r = self._run_command(["reglookup", "-p", reg_path, str(hive)], timeout=REGISTRY_TIMEOUT)
            if r["success"] and r["stdout"]:
                for line in r["stdout"].splitlines():
                    if line.strip() and not line.startswith("PATH"):
                        self.reg_keys.append({"registryPath": reg_path, "value": line.strip()})

        ptprint(f"  ✓ Registry keys found: {len(self.reg_keys)}", "OK", condition=self._out())
        for k in self.reg_keys[:5]:
            ptprint(f"  • {k['registryPath']}: {k['value'][:60]}", "TEXT", condition=self._out())

        self._add_node("registryExtraction", True, keysFound=len(self.reg_keys))
        return True

    def run(self) -> bool:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"ARTEFACT EXTRACTOR v{__version__} | Case: {self.case_id}", "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.extract_from_strings():
            self.ptjsonlib.set_status("finished")
            return False
        if not self.extract_from_pcap():
            self.ptjsonlib.set_status("finished")
            return False
        if not self.extract_registry():
            self.ptjsonlib.set_status("finished")
            return False

        self._print_header("SUMMARY")
        ptprint(f"  IPs:           {len(self.ips)}", "TEXT", condition=self._out())
        ptprint(f"  URLs:          {len(self.urls)}", "TEXT", condition=self._out())
        ptprint(f"  Domains:       {len(self.domains)}", "TEXT", condition=self._out())
        ptprint(f"  Emails:        {len(self.emails)}", "TEXT", condition=self._out())
        ptprint(f"  Registry keys: {len(self.reg_keys)}", "TEXT", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "NIST SP 800-83"],
            "networkIndicators": {
                "ipAddresses": self.ips,
                "urls": self.urls,
                "domains": self.domains,
                "emails": self.emails,
            },
            "registryPersistence": self.reg_keys,
            "totals": {
                "ips": len(self.ips), "urls": len(self.urls),
                "domains": len(self.domains), "regKeys": len(self.reg_keys),
            },
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": (
                    f"Artefact extraction complete - "
                    f"{len(self.ips)} IPs, {len(self.urls)} URLs, {len(self.reg_keys)} registry keys"
                ),
                "result": "SUCCESS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))
        self.ptjsonlib.set_status("finished")
        return True

    def save_report(self) -> Optional[str]:
        out = Path(self.args.json_out) if self.args.json_out \
            else self.output_dir / f"{self.case_id}_artefacts.json"
        raw = self.ptjsonlib.get_result_json()
        out.write_text(raw, encoding="utf-8")
        ptprint(f"\n✓ Artefacts saved: {out}", "OK", condition=True)
        return str(out)


def get_help() -> List[Dict]:
    return [
        {"description": [
            "Forensic artefact extractor - ptlibs compliant",
            "Extracts IPs, URLs, domains from strings file and optionally PCAP",
            "Extracts Windows registry persistence keys from mounted image",
            "Consolidates all IoC into structured JSON for the Intelligence phase",
        ]},
        {"usage": ["ptartefactextractor <case-id> <strings-file> [options]"]},
        {"usage_example": [
            "ptartefactextractor MALWARE-2025-01-26-001 /var/forensics/analysis/MALWARE-2025-01-26-001_strings.txt",
            "ptartefactextractor MALWARE-2025-01-26-001 strings.txt --pcap network.pcap",
            "ptartefactextractor MALWARE-2025-01-26-001 strings.txt --mount-path /mnt/forensic/MALWARE-2025-01-26-001",
            "ptartefactextractor MALWARE-2025-01-26-001 strings.txt --json-out artefacts.json",
        ]},
        {"options": [
            ["case-id", "", "Case identifier - REQUIRED"],
            ["strings-file", "", "Strings file from ptstaticanalysis - REQUIRED"],
            ["-p", "--pcap", "<f>", "PCAP file from dynamic analysis (optional)"],
            ["-m", "--mount-path", "<d>", "Mounted forensic image path for registry analysis (optional)"],
            ["-o", "--output-dir", "<d>", f"Output directory (default: {DEFAULT_ANALYSIS_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file (default: <output-dir>/<case-id>_artefacts.json)"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without processing files"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "Private/loopback IPs are filtered automatically",
            "reglookup required for registry analysis: apt-get install libregf-tools",
            "tshark required for PCAP analysis: apt-get install tshark",
            "Exit 0 = success | Exit 99 = error | Exit 130 = Ctrl+C",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("strings_file")
    parser.add_argument("-p", "--pcap", default=None)
    parser.add_argument("-m", "--mount-path", default=None)
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
        tool = PtArtefactExtractor(args)
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