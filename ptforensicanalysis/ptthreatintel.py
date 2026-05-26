#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptthreatintel - Threat Intelligence lookup (VirusTotal + AlienVault OTX)
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import (
        DEFAULT_ANALYSIS_OUTPUT_DIR,
        VT_REQUEST_DELAY, VT_MAX_HASHES, VT_MAX_IPS,
    )
except ImportError:
    from _constants import (
        DEFAULT_ANALYSIS_OUTPUT_DIR,
        VT_REQUEST_DELAY, VT_MAX_HASHES, VT_MAX_IPS,
    )

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptthreatintel"
VT_BASE = "https://www.virustotal.com/api/v3"
OTX_BASE = "https://otx.alienvault.com/api/v1"


class PtThreatIntel(ForensicToolBase):

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.ioc_file = Path(args.ioc_file)
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.vt_key: Optional[str] = args.vt_key or os.environ.get("VT_API_KEY")
        self.otx_key: Optional[str] = args.otx_key or os.environ.get("OTX_API_KEY")

        self.ioc_data: Dict = {}
        self.vt_results: List[Dict] = []
        self.otx_results: List[Dict] = []
        self.findings: List[str] = []

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({
            "iocFile": str(self.ioc_file),
            "vtAvailable": bool(self.vt_key),
            "otxAvailable": bool(self.otx_key),
        })

    def _http_get(self, url: str, headers: Dict) -> Optional[Dict]:
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            ptprint(f"  HTTP {e.code}: {url[:60]}", "WARNING", condition=self._out())
            return None
        except (URLError, Exception) as e:
            ptprint(f"  Request failed: {e}", "WARNING", condition=self._out())
            return None

    def load_ioc(self) -> bool:
        self._print_header("STEP 1: Loading IoC Report")

        if not self.ioc_file.exists() and not self.dry_run:
            return self._fail("iocLoad", f"IoC file not found: {self.ioc_file}")

        if self.dry_run:
            self._add_node("iocLoad", True, dryRun=True)
            return True

        try:
            raw = json.loads(self.ioc_file.read_text(encoding="utf-8"))
            data = raw.get("results", raw.get("result", raw))
            props = data.get("properties", data)
            self.ioc_data = props.get("iocReport", props).get("ioc", {})
        except Exception as e:
            return self._fail("iocLoad", f"Failed to parse IoC JSON: {e}")

        hashes = self.ioc_data.get("fileHashes", [])
        ips = self.ioc_data.get("networkIndicators", {}).get("ipAddresses", [])

        ptprint(f"  ✓ File hashes: {len(hashes)}", "OK", condition=self._out())
        ptprint(f"  ✓ IPs:         {len(ips)}", "OK", condition=self._out())

        if not self.vt_key and not self.otx_key:
            ptprint(
                "\n  ⚠ No API keys found - set VT_API_KEY / OTX_API_KEY or use --vt-key / --otx-key\n"
                "    Continuing in offline mode (no lookups).",
                "WARNING", condition=self._out())

        self._add_node("iocLoad", True, hashesLoaded=len(hashes), ipsLoaded=len(ips))
        return True

    def lookup_virustotal(self) -> bool:
        self._print_header("STEP 2: VirusTotal Lookup")

        if not self.vt_key:
            ptprint("  ⚠ VT_API_KEY not set - skipping VirusTotal", "WARNING", condition=self._out())
            self._add_node("virusTotalLookup", True, skipped=True)
            return True

        headers = {"x-apikey": self.vt_key, "Accept": "application/json"}
        hashes = self.ioc_data.get("fileHashes", [])
        ips = self.ioc_data.get("networkIndicators", {}).get("ipAddresses", [])[:VT_MAX_IPS]

        for entry in hashes[:VT_MAX_HASHES]:
            sha256 = entry.get("sha256", "")
            if not sha256:
                continue
            if self.dry_run:
                self.vt_results.append({"sha256": sha256, "source": "VirusTotal", "malicious": 0})
                continue
            ptprint(f"  Looking up: {sha256[:16]}...  (waiting {VT_REQUEST_DELAY}s)", "TEXT", condition=self._out())
            data = self._http_get(f"{VT_BASE}/files/{sha256}", headers)
            time.sleep(VT_REQUEST_DELAY)
            if data:
                attrs = data.get("data", {}).get("attributes", {})
                stats = attrs.get("last_analysis_stats", {})
                malicious = stats.get("malicious", 0)
                family = attrs.get("popular_threat_classification", {}).get("suggested_threat_label", "")
                result = {
                    "sha256": sha256, "filename": entry.get("filename", ""),
                    "source": "VirusTotal", "malicious": malicious,
                    "total": sum(stats.values()), "family": family,
                    "tags": attrs.get("tags", []),
                }
                self.vt_results.append(result)
                lv = "ERROR" if malicious else "OK"
                ptprint(f"  {'⚠' if malicious else '✓'} {entry.get('filename', '?')}: "
                        f"{'MALICIOUS (' + str(malicious) + ')' if malicious else 'CLEAN'}  |  {family}",
                        lv, condition=self._out())
                if malicious:
                    self.findings.append(f"VT: {entry.get('filename', '?')} - {malicious} engines - {family}")

        for ip in ips:
            if self.dry_run:
                break
            ptprint(f"  Looking up IP: {ip}", "TEXT", condition=self._out())
            data = self._http_get(f"{VT_BASE}/ip_addresses/{ip}", headers)
            time.sleep(VT_REQUEST_DELAY)
            if data:
                attrs = data.get("data", {}).get("attributes", {})
                stats = attrs.get("last_analysis_stats", {})
                malicious = stats.get("malicious", 0)
                result = {
                    "ip": ip, "source": "VirusTotal",
                    "malicious": malicious,
                    "country": attrs.get("country", ""),
                    "asOwner": attrs.get("as_owner", ""),
                }
                self.vt_results.append(result)
                if malicious:
                    self.findings.append(f"VT: IP {ip} - {malicious} engines - {result['country']}")
                    ptprint(f"  ⚠ {ip}: MALICIOUS ({malicious}) - {result['country']}", "ERROR", condition=self._out())

        ptprint(f"\n  ✓ VT lookups complete: {len(self.vt_results)}", "OK", condition=self._out())
        self._add_node("virusTotalLookup", True, resultsCount=len(self.vt_results))
        return True

    def lookup_otx(self) -> bool:
        self._print_header("STEP 3: AlienVault OTX Lookup")

        if not self.otx_key:
            ptprint("  ⚠ OTX_API_KEY not set - skipping OTX", "WARNING", condition=self._out())
            self._add_node("otxLookup", True, skipped=True)
            return True

        headers = {"X-OTX-API-KEY": self.otx_key, "Accept": "application/json"}
        ips = self.ioc_data.get("networkIndicators", {}).get("ipAddresses", [])[:VT_MAX_IPS]

        for ip in ips:
            if self.dry_run:
                break
            ptprint(f"  OTX lookup: {ip}", "TEXT", condition=self._out())
            data = self._http_get(f"{OTX_BASE}/indicators/IPv4/{ip}/general", headers)
            time.sleep(2)
            if data:
                pulse_count = data.get("pulse_info", {}).get("count", 0)
                result = {
                    "ip": ip, "source": "OTX",
                    "pulseCount": pulse_count,
                    "reputation": data.get("reputation", 0),
                    "country": data.get("country_name", ""),
                }
                self.otx_results.append(result)
                if pulse_count > 0:
                    self.findings.append(f"OTX: IP {ip} - {pulse_count} threat pulses")
                    ptprint(f"  ⚠ {ip}: {pulse_count} threat pulses", "WARNING", condition=self._out())
                else:
                    ptprint(f"  ✓ {ip}: no known threats", "OK", condition=self._out())

        ptprint(f"\n  ✓ OTX lookups complete: {len(self.otx_results)}", "OK", condition=self._out())
        self._add_node("otxLookup", True, resultsCount=len(self.otx_results))
        return True

    def run(self) -> bool:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"THREAT INTEL v{__version__} | Case: {self.case_id}", "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.load_ioc():
            self.ptjsonlib.set_status("finished")
            return False
        if not self.lookup_virustotal():
            self.ptjsonlib.set_status("finished")
            return False
        if not self.lookup_otx():
            self.ptjsonlib.set_status("finished")
            return False

        self._print_header("SUMMARY")
        ptprint(f"  VT results:  {len(self.vt_results)}", "TEXT", condition=self._out())
        ptprint(f"  OTX results: {len(self.otx_results)}", "TEXT", condition=self._out())
        if self.findings:
            ptprint(f"\n  ⚠ KEY FINDINGS ({len(self.findings)}):", "WARNING", condition=self._out(), colortext=True)
            for f in self.findings:
                ptprint(f"  • {f}", "WARNING", condition=self._out())
        else:
            ptprint("  ✓ No known threats identified", "OK", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-61", "NIST SP 800-150", "MITRE ATT&CK"],
            "vtResults": self.vt_results,
            "otxResults": self.otx_results,
            "keyFindings": self.findings,
            "totalLookups": len(self.vt_results) + len(self.otx_results),
            "threatsFound": len(self.findings),
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": (
                    f"Threat Intelligence complete - "
                    f"{len(self.findings)} findings, "
                    f"{len(self.vt_results) + len(self.otx_results)} lookups"
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
            else self.output_dir / f"{self.case_id}_threat_intel.json"
        raw = self.ptjsonlib.get_result_json()
        out.write_text(raw, encoding="utf-8")
        ptprint(f"\n✓ Threat Intel report saved: {out}", "OK", condition=True)
        return str(out)


def get_help() -> List[Dict]:
    return [
        {"description": [
            "Threat Intelligence lookup - ptlibs compliant",
            "Looks up file hashes and IPs against VirusTotal and AlienVault OTX",
            "Requires API keys: set VT_API_KEY and/or OTX_API_KEY env variables",
            f"VirusTotal free tier: 4 req/min - {VT_REQUEST_DELAY}s delay enforced",
            "Without API keys: runs in offline mode, report structure still generated",
        ]},
        {"usage": ["ptthreatintel <case-id> <ioc-file> [options]"]},
        {"usage_example": [
            "ptthreatintel MALWARE-2025-01-26-001 /var/forensics/analysis/MALWARE-2025-01-26-001_ioc.json",
            "ptthreatintel MALWARE-2025-01-26-001 ioc.json --vt-key YOUR_KEY",
            "ptthreatintel MALWARE-2025-01-26-001 ioc.json --json-out threat_intel.json",
            "export VT_API_KEY=your_key && ptthreatintel MALWARE-2025-01-26-001 ioc.json",
        ]},
        {"options": [
            ["case-id", "", "Case identifier - REQUIRED"],
            ["ioc-file", "", "IoC JSON from ptiocreport - REQUIRED"],
            ["--vt-key", "<k>", "VirusTotal API key (or set VT_API_KEY env var)"],
            ["--otx-key", "<k>", "AlienVault OTX API key (or set OTX_API_KEY env var)"],
            ["-o", "--output-dir", "<d>", f"Output directory (default: {DEFAULT_ANALYSIS_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save report to file (default: <output-dir>/<case-id>_threat_intel.json)"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without API calls"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            f"Caps: max {VT_MAX_HASHES} hashes + {VT_MAX_IPS} IPs per run (free tier)",
            "Exit 0 = success | Exit 99 = error | Exit 130 = Ctrl+C",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("ioc_file")
    parser.add_argument("--vt-key", default=None)
    parser.add_argument("--otx-key", default=None)
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
        tool = PtThreatIntel(args)
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