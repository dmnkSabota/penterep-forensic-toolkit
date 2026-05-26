#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptvolatilecollector - Volatile data collection (RAM dump + process list)
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import DEFAULT_VOLATILE_OUTPUT_DIR, RAM_TIMEOUT
except ImportError:
    from _constants import DEFAULT_VOLATILE_OUTPUT_DIR, RAM_TIMEOUT

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptvolatilecollector"


class PtVolatileCollector(ForensicToolBase):

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.ram_method: str = "devmem"
        self.ram_path: Optional[Path] = None
        self.ram_hash: Optional[str] = None
        self.ram_size: int = 0
        self.processes_path: Optional[Path] = None
        self.processes_hash: Optional[str] = None
        self.network_path: Optional[Path] = None
        self.network_hash: Optional[str] = None
        self.artefacts: List[Dict] = []

        self._init_properties(__version__)

    def _write_sidecar(self, path: Path, sha256: str) -> None:
        Path(str(path) + ".sha256").write_text(f"{sha256}  {path.name}\n")

    def _record_artefact(self, name: str, path: Path, sha256: str) -> None:
        self.artefacts.append({
            "name": name,
            "path": str(path),
            "sha256": sha256,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def check_prerequisites(self) -> bool:
        self._print_header("STEP 1: Prerequisites")
        ptprint("\n⚠ Run from EXTERNAL MEDIA - never install on the compromised system", "WARNING", condition=self._out())

        for cmd in ("ps", "sha256sum"):
            if not self._check_command(cmd):
                return self._fail("prerequisitesCheck", f"Required command not found: {cmd}")
            ptprint(f"  ✓ {cmd}", "OK", condition=self._out())

        if self._check_command("insmod") and not self.dry_run:
            lime_search_paths = [
                Path("/lib/modules"),
                Path("/usr/lib/modules"),
                Path("/opt"),
            ]
            lime_modules = [
                m for base in lime_search_paths if base.exists()
                for m in base.rglob("lime*.ko")
            ]
            if lime_modules:
                self.ram_method = "lime"
                ptprint(f"  ✓ LiME module: {lime_modules[0]}", "OK", condition=self._out())
            else:
                ptprint("  ⚠ LiME not found - /dev/mem fallback", "WARNING", condition=self._out())
        elif self.dry_run:
            self.ram_method = "lime"
        else:
            ptprint("  ⚠ insmod unavailable - /dev/mem fallback", "WARNING", condition=self._out())

        for cmd in ("ss", "netstat"):
            available = self._check_command(cmd)
            ptprint(f"  {'✓' if available else '⚠ optional'} {cmd}",
                    "OK" if available else "WARNING", condition=self._out())

        self._add_node("prerequisitesCheck", True, ramMethod=self.ram_method)
        return True

    def collect_ram(self) -> bool:
        self._print_header("STEP 2: RAM Dump")
        self.ram_path = self.output_dir / f"{self.case_id}_ram.lime"
        ptprint(f"\nOutput: {self.ram_path}", "TEXT", condition=self._out())

        if self.dry_run:
            self.ram_hash = "dry-run-no-hash"
            self._add_node("ramDump", True, dryRun=True)
            return True

        t0 = time.time()

        if self.ram_method == "lime":
            lime_search_paths = [
                Path("/lib/modules"),
                Path("/usr/lib/modules"),
                Path("/opt"),
            ]
            lime_modules = [
                m for base in lime_search_paths if base.exists()
                for m in base.rglob("lime*.ko")
            ]
            r = self._run_command(
                ["insmod", str(lime_modules[0]), f"path={self.ram_path}", "format=lime"],
                timeout=RAM_TIMEOUT)
            if not r["success"]:
                ptprint(f"  ⚠ LiME failed: {r['stderr']} - falling back to /dev/mem", "WARNING", condition=self._out())
                self.ram_method = "devmem"

        if self.ram_method == "devmem":
            if not os.path.exists("/dev/mem"):
                return self._fail("ramDump", "/dev/mem not accessible - run as root")
            r = self._run_command(
                ["dd", "if=/dev/mem", f"of={self.ram_path}", "bs=1M", "conv=noerror,sync"],
                timeout=RAM_TIMEOUT)
            if not r["success"]:
                return self._fail("ramDump", f"RAM dump failed: {r['stderr']}")

        dur = time.time() - t0
        if self.ram_path.exists():
            self.ram_size = self.ram_path.stat().st_size
            self.ram_hash = self._file_sha256(self.ram_path) or ""
            self._write_sidecar(self.ram_path, self.ram_hash)
            ptprint(f"  ✓ RAM: {self.ram_size / (1024**3):.2f} GB  |  {dur:.0f}s  |  {self.ram_hash[:16]}...",
                    "OK", condition=self._out())
            self._record_artefact("RAM dump", self.ram_path, self.ram_hash)
        else:
            ptprint("  ⚠ RAM dump file not created - continuing without it", "WARNING", condition=self._out())

        self._add_node("ramDump", bool(self.ram_hash),
            method=self.ram_method,
            sizeMB=round(self.ram_size / (1024**2), 1),
            sha256=self.ram_hash)
        return True

    def collect_process_list(self) -> bool:
        self._print_header("STEP 3: Process List & Network State")
        self.processes_path = self.output_dir / f"{self.case_id}_processes.txt"
        self.network_path = self.output_dir / f"{self.case_id}_network.txt"

        if self.dry_run:
            self._add_node("processCollection", True, dryRun=True)
            return True

        ptprint("\n[3a] Running processes", "SUBTITLE", condition=self._out())
        lines = [f"=== PROCESS LIST - {datetime.now()} ===\n"]
        for cmd in (["ps", "auxf"], ["ps", "-eo", "pid,ppid,user,args,etimes", "--sort=-etimes"]):
            r = self._run_command(cmd, timeout=30)
            if r["success"]:
                lines.append(f"\n--- {' '.join(cmd)} ---\n{r['stdout']}\n")
                break

        self.processes_path.write_text("\n".join(lines), encoding="utf-8")
        self.processes_hash = self._file_sha256(self.processes_path) or ""
        self._write_sidecar(self.processes_path, self.processes_hash)
        ptprint(f"  ✓ Processes: {self.processes_hash[:16]}...", "OK", condition=self._out())
        self._record_artefact("Process list", self.processes_path, self.processes_hash)

        ptprint("\n[3b] Network connections", "SUBTITLE", condition=self._out())
        net_lines = [f"=== NETWORK STATE - {datetime.now()} ===\n"]
        for cmd, label in ((["ss", "-tulnp"], "ss"), (["netstat", "-antp"], "netstat")):
            if self._check_command(cmd[0]):
                r = self._run_command(cmd, timeout=30)
                if r["success"]:
                    net_lines.append(f"\n--- {label} ---\n{r['stdout']}\n")

        self.network_path.write_text("\n".join(net_lines), encoding="utf-8")
        self.network_hash = self._file_sha256(self.network_path) or ""
        self._write_sidecar(self.network_path, self.network_hash)
        ptprint(f"  ✓ Network: {self.network_hash[:16]}...", "OK", condition=self._out())
        self._record_artefact("Network state", self.network_path, self.network_hash)

        self._add_node("processCollection", True,
            processesHash=self.processes_hash,
            networkHash=self.network_hash)
        return True

    def run(self) -> bool:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"VOLATILE COLLECTOR v{__version__} | Case: {self.case_id}", "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.check_prerequisites():
            self.ptjsonlib.set_status("finished")
            return False
        if not self.collect_ram():
            self.ptjsonlib.set_status("finished")
            return False
        if not self.collect_process_list():
            self.ptjsonlib.set_status("finished")
            return False

        self._print_header("SUMMARY")
        for a in self.artefacts:
            ptprint(f"  ✓ {a['name']}: {a['sha256'][:32]}...", "OK", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "RFC 3227"],
            "outputDir": str(self.output_dir),
            "ramMethod": self.ram_method,
            "ramSizeBytes": self.ram_size,
            "ramHash": self.ram_hash,
            "artefacts": self.artefacts,
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": "Volatile data collection complete",
                "result": "SUCCESS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "artefactsCount": len(self.artefacts),
            }
        ))
        self.ptjsonlib.set_status("finished")
        return True

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
            "Volatile data collector for live forensics - ptlibs compliant",
            "Captures RAM dump (LiME preferred, /dev/mem fallback), process list and network state",
            "Computes SHA-256 sidecar for every captured artefact",
            "Compliant with NIST SP 800-86 (order of volatility) and RFC 3227",
            "",
            "⚠ Run from EXTERNAL MEDIA - never install on the compromised system",
            "⚠ Must be run as ROOT for RAM dump access",
        ]},
        {"usage": ["ptvolatilecollector <case-id> [options]"]},
        {"usage_example": [
            "ptvolatilecollector MALWARE-2025-01-26-001",
            "ptvolatilecollector MALWARE-2025-01-26-001 --analyst 'Jan Novak'",
            "ptvolatilecollector MALWARE-2025-01-26-001 --json-out volatile.json",
            "ptvolatilecollector MALWARE-2025-01-26-001 --dry-run",
        ]},
        {"options": [
            ["case-id", "", "Case identifier - REQUIRED"],
            ["-o", "--output-dir", "<d>", f"Output directory (default: {DEFAULT_VOLATILE_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without accessing memory"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "LiME preferred for RAM dump - install: apt-get install lime-forensics-dkms",
            "Creates .sha256 sidecar for every captured artefact",
            "Exit 0 = success | Exit 99 = error | Exit 130 = Ctrl+C",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_VOLATILE_OUTPUT_DIR)
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
        tool = PtVolatileCollector(args)
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