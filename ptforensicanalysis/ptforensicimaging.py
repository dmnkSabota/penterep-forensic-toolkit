#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptforensicimaging - Forensic media imaging tool
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import os
import re
import subprocess
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
    from ._constants import DEFAULT_OUTPUT_DIR
except ImportError:
    from _constants import DEFAULT_OUTPUT_DIR

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptforensicimaging"


class PtForensicImaging(ForensicToolBase):
    """Forensic media imaging - dc3dd (READABLE) or ddrescue (PARTIAL), NIST SP 800-86, ISO/IEC 27037:2012."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.device = args.device
        self.tool = args.tool
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.media_status: str = "READABLE" if self.tool == "dc3dd" else "PARTIAL"
        self.source_size: Optional[int] = None
        self.image_path: Optional[Path] = None
        self.source_hash: Optional[str] = None
        self.duration: Optional[float] = None
        self.avg_speed: Optional[float] = None
        self.error_sectors: int = 0
        self.mapfile: Optional[Path] = None
        self.log_file: Optional[Path] = None

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({"devicePath": self.device, "imagingTool": self.tool})

    def _tool_version(self) -> str:
        r = self._run_command([self.tool, "--version"], timeout=5)
        if r["success"] and r["stdout"]:
            m = re.search(r"\d+\.\d+(?:\.\d+)?", r["stdout"])
            if m:
                return m.group(0)
        return "unknown"

    def check_prerequisites(self) -> bool:
        self._print_header("STEP 1: Prerequisites")
        if not self._check_tool():
            return False
        if not self._check_device():
            return False
        if not self._check_storage():
            return False
        self._add_node("prerequisitesCheck", True, tool=self.tool, device=self.device)
        return True

    def _check_tool(self) -> bool:
        ptprint(f"\n[1a] Checking {self.tool}", "SUBTITLE", condition=self._out())
        if not self._check_command(self.tool):
            return self._fail("prerequisitesCheck", f"{self.tool} not installed")
        ptprint(f"✓ {self.tool} available", "OK", condition=self._out())
        if self.tool == "ddrescue" and not self._check_command("sha256sum"):
            return self._fail("prerequisitesCheck", "sha256sum not installed")
        if self.tool == "ddrescue":
            ptprint("✓ sha256sum available", "OK", condition=self._out())
        return True

    def _check_device(self) -> bool:
        ptprint("\n[1b] Checking source device", "SUBTITLE", condition=self._out())
        if not os.path.exists(self.device) and not self.dry_run:
            return self._fail("prerequisitesCheck", f"Device not found: {self.device}")
        ptprint(f"✓ Device accessible: {self.device}", "OK", condition=self._out())
        return True

    def _check_storage(self) -> bool:
        ptprint("\n[1c] Checking target storage", "SUBTITLE", condition=self._out())
        try:
            stat = os.statvfs(self.output_dir)
            free = stat.f_bavail * stat.f_frsize
            if self.source_size:
                need = int(self.source_size * 1.1)
                ptprint(f"Required: {need:,} B ({need / (1024**3):.2f} GB)", "TEXT", condition=self._out())
                ptprint(f"Available: {free:,} B ({free / (1024**3):.2f} GB)", "TEXT", condition=self._out())
                if free < need and not self.dry_run:
                    return self._fail("prerequisitesCheck", "Insufficient storage (need 110% of source size)")
                ptprint("✓ Sufficient storage", "OK", condition=self._out())
            else:
                ptprint(f"Available: {free / (1024**3):.2f} GB (source size unknown)", "TEXT", condition=self._out())
        except Exception as e:
            ptprint(f"⚠ Could not check storage: {e}", "WARNING", condition=self._out())
        return True

    def _get_source_size(self) -> None:
        size = self._get_device_size(self.device)
        if size:
            self.source_size = size
            ptprint(f"Size: {size:,} bytes ({size / (1024**3):.2f} GB)", "TEXT", condition=self._out())

    def _calculate_metrics(self, start: float) -> None:
        self.duration = time.time() - start
        if self.image_path and self.image_path.exists():
            sz = self.image_path.stat().st_size
            if not self.source_size:
                self.source_size = sz
            mb = sz / (1024 ** 2)
            self.avg_speed = mb / self.duration if self.duration else 0

    def _print_imaging_header(self, extra: str) -> None:
        ptprint(f"\nStarting {self.tool} ...", "SUBTITLE", condition=self._out())
        ptprint(f"Source: {self.device}", "TEXT", condition=self._out())
        ptprint(f"Target: {self.image_path}", "TEXT", condition=self._out())
        ptprint(extra, "TEXT", condition=self._out())
        self._get_source_size()


    def _parse_dc3dd_hash(self) -> None:
        if not self.log_file or not self.log_file.exists():
            ptprint("⚠ dc3dd log file not found", "WARNING", condition=self._out())
            return
        for line in self.log_file.read_text().splitlines():
            if "sha256" in line.lower():
                for part in line.split():
                    if len(part) == 64 and all(c in "0123456789abcdef" for c in part.lower()):
                        self.source_hash = part.lower()
                        ptprint(f"✓ SHA-256: {self.source_hash}", "OK", condition=self._out())
                        return
        ptprint("⚠ Could not extract SHA-256 from dc3dd log", "WARNING", condition=self._out())

    def _compute_hash(self) -> None:
        ptprint("\nCalculating SHA-256 ...", "SUBTITLE", condition=self._out())
        r = self._run_command(["sha256sum", str(self.image_path)], timeout=7200)
        if r["success"] and r["stdout"]:
            self.source_hash = r["stdout"].split()[0]
            ptprint(f"✓ SHA-256: {self.source_hash}", "OK", condition=self._out())
        else:
            ptprint(f"✗ Hash calculation failed: {r['stderr']}", "ERROR", condition=self._out())

    def _create_hash_sidecar(self) -> None:
        if not self.source_hash:
            return
        sidecar = Path(str(self.image_path) + ".sha256")
        sidecar.write_text(f"{self.source_hash}  {self.image_path.name}\n")
        ptprint(f"✓ Hash sidecar: {sidecar.name}", "OK", condition=self._out())


    def run_imaging(self) -> bool:
        self._print_header("STEP 2: Forensic Imaging")
        self.image_path = self.output_dir / f"{self.case_id}.dd"
        self.log_file = self.output_dir / f"{self.case_id}_imaging.log"
        return self.run_dc3dd() if self.tool == "dc3dd" else self.run_ddrescue()

    def run_dc3dd(self) -> bool:
        self._print_imaging_header("Hash: SHA-256 (integrated, single pass)")
        cmd = ["dc3dd", f"if={self.device}", f"of={self.image_path}", "hash=sha256", f"log={self.log_file}"]
        ptprint(f"\nCommand: {' '.join(cmd)}", "TEXT", condition=self._out())

        if self.dry_run:
            ptprint("[DRY-RUN] dc3dd skipped.", "INFO", condition=self._out())
            self._add_node("imagingResult", True, tool="dc3dd", dryRun=True)
            return True

        ptprint("\nImaging in progress ...", "TEXT", condition=self._out())
        t0 = time.time()
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            last_update = 0.0
            progress_done = False
            flush_start = None
            while proc.poll() is None:
                time.sleep(0.5)
                now = time.time()
                if not progress_done and now - last_update >= 1.0 and self.image_path.exists() and self.source_size:
                    current = self.image_path.stat().st_size
                    self._progress_bytes(current, self.source_size, now - t0)
                    last_update = now
                    if current >= self.source_size:
                        progress_done = True
                        flush_start = now
                elif progress_done and self._out() and now - last_update >= 2.0:
                    elapsed = int(now - flush_start)
                    print(f"\r  Flushing buffers and computing hash ... {elapsed}s", end="", flush=True)
                    last_update = now
            if progress_done and self._out():
                print()
            if proc.returncode != 0:
                return self._fail("imagingResult", f"dc3dd failed (rc={proc.returncode})")
        except KeyboardInterrupt:
            ptprint("\n✗ Imaging interrupted by user", "WARNING", condition=self._out())
            proc.terminate()
            proc.wait()
            raise

        self._calculate_metrics(t0)
        self._parse_dc3dd_hash()
        self._create_hash_sidecar()
        ptprint("✓ dc3dd imaging completed", "OK", condition=self._out())
        self._add_node("imagingResult", True, tool="dc3dd",
            durationSeconds=round(self.duration or 0, 2),
            averageSpeedMBps=round(self.avg_speed or 0, 2),
            sourceHash=self.source_hash)
        return True

    def run_ddrescue(self) -> bool:
        self._print_imaging_header("Mode: Damaged sector recovery")
        self.mapfile = self.output_dir / f"{self.case_id}.mapfile"
        cmd = ["ddrescue", "-f", "-v", self.device, str(self.image_path), str(self.mapfile)]
        ptprint(f"\nCommand: {' '.join(cmd)}", "TEXT", condition=self._out())

        if self.dry_run:
            ptprint("[DRY-RUN] ddrescue skipped.", "INFO", condition=self._out())
            self._add_node("imagingResult", True, tool="ddrescue", dryRun=True)
            return True

        ptprint("\nImaging in progress ...", "TEXT", condition=self._out())
        t0 = time.time()
        try:
            with open(self.log_file, "w") as lf:
                lf.write(f"ddrescue started {datetime.now()}\n")
                lf.write(f"Command: {' '.join(cmd)}\n{'=' * 70}\n\n")
                lf.flush()
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                last_update = 0.0
                progress_done = False
                try:
                    for line in proc.stdout:
                        lf.write(line)
                        lf.flush()
                        now = time.time()
                        if not progress_done and now - last_update >= 1.0 and self.source_size:
                            current = self.image_path.stat().st_size if self.image_path.exists() else 0
                            self._progress_bytes(current, self.source_size, now - t0)
                            last_update = now
                            if current >= self.source_size:
                                progress_done = True
                                if self._out():
                                    print()
                    proc.wait()
                except KeyboardInterrupt:
                    lf.write("\n[INTERRUPTED BY USER]\n")
                    lf.flush()
                    ptprint("\n✗ Imaging interrupted by user", "WARNING", condition=self._out())
                    proc.terminate()
                    proc.wait()
                    raise
                lf.write(f"\nExit code: {proc.returncode}\n")
            if proc.returncode not in (0, 1):
                return self._fail("imagingResult", f"ddrescue failed (rc={proc.returncode})")
        except Exception as e:
            return self._fail("imagingResult", f"ddrescue execution failed: {e}")

        self._calculate_metrics(t0)
        self._compute_hash()
        self._create_hash_sidecar()
        ptprint("✓ ddrescue imaging completed", "OK", condition=self._out())
        self._add_node("imagingResult", True, tool="ddrescue",
            durationSeconds=round(self.duration or 0, 2),
            averageSpeedMBps=round(self.avg_speed or 0, 2),
            sourceHash=self.source_hash,
            mapfile=str(self.mapfile))
        return True

    def _print_summary(self) -> None:
        self._print_header("SUMMARY")
        ptprint(f"Case: {self.case_id}", "TEXT", condition=self._out())
        ptprint(f"Source: {self.device}", "TEXT", condition=self._out())
        ptprint(f"Tool: {self.tool}", "TEXT", condition=self._out())
        if self.image_path and self.image_path.exists():
            sz = self.image_path.stat().st_size
            ptprint(f"Image: {self.image_path}", "TEXT", condition=self._out())
            ptprint(f"Size: {sz:,} bytes ({sz / (1024**3):.2f} GB)", "TEXT", condition=self._out())
        if self.duration:
            ptprint(f"Time: {self.duration:.1f}s ({self.duration / 60:.1f} min)", "TEXT", condition=self._out())
        if self.avg_speed:
            ptprint(f"Speed: {self.avg_speed:.2f} MB/s", "TEXT", condition=self._out())
        if self.error_sectors:
            ptprint(f"Bad sectors: {self.error_sectors}", "WARNING", condition=self._out())
        if self.source_hash:
            ptprint(f"SHA-256: {self.source_hash}", "TEXT", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"FORENSIC IMAGING v{__version__} | Case: {self.case_id}", "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.check_prerequisites():
            self.ptjsonlib.set_status("finished")
            return
        if not self.run_imaging():
            self.ptjsonlib.set_status("finished")
            return
        if not self.dry_run:
            self._print_summary()

        method = "single-pass with integrated hashing" if self.tool == "dc3dd" else "damaged sector recovery with separate hashing"
        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "mediaStatus": self.media_status,
            "outputDir": str(self.output_dir),
            "imagePath": str(self.image_path) if self.image_path else None,
            "imageFormat": "raw (.dd)",
            "imageSizeBytes": self.source_size,
            "acquisitionMethod": method,
            "toolVersion": self._tool_version(),
            "durationSeconds": round(self.duration or 0, 2),
            "averageSpeedMBps": round(self.avg_speed or 0, 2),
            "hashAlgorithm": "SHA-256",
            "sourceHash": self.source_hash,
            "hashVerified": bool(self.source_hash),
            "errorSectors": self.error_sectors,
            "writeBlockerConfirmed": not self.dry_run,
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": "Forensic imaging complete",
                "result": "SUCCESS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tool": self.tool,
                "sourceHash": self.source_hash,
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
            "Forensic media imaging tool - ptlibs compliant",
            "Supports dc3dd (READABLE media) and ddrescue (damaged media)",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
            "",
            "⚠ WRITE-BLOCKER IS ALWAYS REQUIRED - confirmed at every run",
        ]},
        {"usage": ["ptforensicimaging <case-id> <device> <tool> [options]"]},
        {"usage_example": [
            "ptforensicimaging PHOTORECOVERY-2025-01-26-001 /dev/sdb dc3dd",
            "ptforensicimaging CASE-001 /dev/sdb dc3dd --analyst 'John Doe'",
            "ptforensicimaging CASE-002 /dev/sdc ddrescue --json-out result.json",
        ]},
        {"options": [
            ["case-id", "", "Case identifier - REQUIRED"],
            ["device", "", "Device path (e.g., /dev/sdb) - REQUIRED"],
            ["tool", "", "Imaging tool: dc3dd or ddrescue - REQUIRED"],
            ["-o", "--output-dir", "<d>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without running the imaging tool"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "dc3dd: READABLE media - integrated SHA-256, fast single pass",
            "ddrescue: PARTIAL media - damaged sector recovery, SHA-256 computed separately",
            "Creates canonical <image>.sha256 sidecar on completion",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("device")
    parser.add_argument("tool", choices=["dc3dd", "ddrescue"])
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
        if not args.dry_run and not PtForensicImaging.confirm_write_blocker():
            ptprint("Imaging ABORTED - write-blocker is REQUIRED!", "ERROR", condition=True, colortext=True)
            return 99
        tool = PtForensicImaging(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if props.get("sourceHash") else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())