#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptmediareadability - Forensic media readability diagnostic tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import sys
import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

# Skript je vždy spúšťaný ako nainštalovaný balíček cez Penterep platformu,
# relatívny import _version.py je preto vždy validný.
from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR  = "/var/forensics/reports"
DEFAULT_LOG_DIR     = "/var/log/forensics"
TIMEOUT_FAST        = 30    # lsblk, blockdev, first sector check
TIMEOUT_SLOW        = 60    # sequential / random dd reads
TIMEOUT_LONG        = 120   # 10 MB speed measurement
RETRY_FAST          = 3     # diagnostic commands – cheap to retry
RETRY_SLOW          = 1     # long dd operations – avoid stalling on bad media
SPEED_CRITICAL_MBS  = 5.0
SPEED_WARNING_MBS   = 20.0
SECTOR_SIZE         = 512

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtMediaReadability:
    """
    Forensic media readability diagnostic – ptlibs compliant.

    5-stage READ-ONLY protocol:
      1. OS Detection      (lsblk)
      2. First Sector Read (dd, 512 B)
      3. Sequential Read   (dd, 1 MB)
      4. Random Read       (dd, 3 positions)
      5. Speed Measurement (dd, 10 MB) – skipped when test 3 fails;
         a PARTIAL medium cannot sustain 10 MB sequential I/O reliably.

    Outputs structured JSON for Chain of Custody documentation.
    Compliant with NIST SP 800-86 and ISO/IEC 27037:2012.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.device     = args.device
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.output_dir = Path(args.output_dir)

        if not self.device.startswith("/dev/"):
            self.ptjsonlib.end_error(f"Invalid device path: {self.device}", args.json)
            sys.exit(99)
        if not self.dry_run and not os.path.exists(self.device):
            self.ptjsonlib.end_error(f"Device not found: {self.device}", args.json)
            sys.exit(99)

        self.logger = self._setup_logger()
        self.ptjsonlib.add_properties({
            "caseId": self.case_id, "device": self.device,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__, "deviceSizeBytes": None,
            "mediaStatus": "UNKNOWN", "recommendedTool": None,
            "nextStep": None, "dryRun": self.dry_run,
        })

    # --- setup --------------------------------------------------------------

    def _setup_logger(self) -> logging.Logger:
        log_dir = Path(DEFAULT_LOG_DIR)
        if not self.dry_run:
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                log_dir = Path("/tmp/forensics")
                log_dir.mkdir(parents=True, exist_ok=True)

        # Unique name per instance prevents shared state and duplicate handlers
        # if multiple tool instances are created in the same process.
        logger = logging.getLogger(f"media_readability.{id(self)}")
        logger.setLevel(logging.DEBUG)
        if not self.dry_run:
            fh = logging.FileHandler(log_dir / f"media_readability_{datetime.now().strftime('%Y%m%d')}.log")
            fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            logger.addHandler(fh)
        if self.args.verbose and not self.args.json:
            logger.addHandler(logging.StreamHandler())
        return logger

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def confirm_write_blocker() -> bool:
        """Interactive write-blocker safety check. Must run before any device I/O."""
        ptprint("CRITICAL: Hardware write-blocker must be connected.", "WARNING", condition=True, colortext=True)
        ptprint("Verify: write-blocker powered, LED shows PROTECTED, device connected through it.", "INFO", condition=True)
        confirmed = input("\nConfirm write-blocker is active [yes/NO]: ").strip().lower() in ("yes", "y")
        ptprint("Write-blocker confirmed – proceeding." if confirmed
                else "Write-blocker NOT confirmed – test ABORTED.", "OK" if confirmed else "ERROR", condition=True)
        return confirmed

    def _check_command(self, cmd: str) -> bool:
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def _run_command(self, cmd: List[str], timeout: int = TIMEOUT_FAST,
                     retries: int = RETRY_FAST) -> Dict[str, Any]:
        """Run a shell command with timeout and retry. Use RETRY_SLOW for long dd ops."""
        base = {"success": False, "stdout": "", "stderr": "", "returncode": -1, "duration": 0.0}
        if self.dry_run:
            return {**base, "success": True, "stdout": "[DRY-RUN]"}

        self.logger.debug(f"Executing: {' '.join(cmd)}")
        for attempt in range(retries):
            try:
                t0   = datetime.now()
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
                base.update({"success": proc.returncode == 0, "stdout": proc.stdout.strip(),
                              "stderr": proc.stderr.strip(), "returncode": proc.returncode,
                              "duration": (datetime.now() - t0).total_seconds()})
                if base["success"] or any(e in proc.stderr for e in ("Permission denied", "not found")):
                    break
                self.logger.warning(f"Attempt {attempt + 1}/{retries} failed")
            except subprocess.TimeoutExpired:
                base["stderr"] = f"Timeout after {timeout}s"; self.logger.error(base["stderr"])
            except Exception as exc:
                base["stderr"] = str(exc); self.logger.error(exc)
        return base

    def _add_test_node(self, test_id: int, name: str, success: bool, **kwargs) -> None:
        """Append a diagnosticTest result node to the JSON output."""
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "diagnosticTest",
            properties={"testId": test_id, "testName": name, "success": success, **kwargs},
        ))

    def _get_device_size(self) -> Optional[int]:
        for cmd in (["blockdev", "--getsize64", self.device],
                    ["lsblk", "-b", "-d", "-n", "-o", "SIZE", self.device]):
            r = self._run_command(cmd)
            if r["success"] and r["stdout"].isdigit():
                return int(r["stdout"])
        return None

    # --- tests --------------------------------------------------------------

    def test_1_os_detection(self) -> bool:
        ptprint("\nTest 1/5: OS Detection (lsblk)", "TITLE", condition=not self.args.json)
        if not self._check_command("lsblk"):
            self._add_test_node(1, "OS Detection", False, error="lsblk not found – install util-linux")
            return False

        cmd = ["lsblk", "-d", "-n", "-o", "NAME,SIZE,TYPE,MODEL", self.device]
        r   = self._run_command(cmd, TIMEOUT_FAST, RETRY_FAST)
        self._add_test_node(1, "OS Detection", r["success"], command=" ".join(cmd),
                            output=r["stdout"] or r["stderr"], durationSeconds=r["duration"],
                            returnCode=r["returncode"])

        if r["success"]:
            ptprint(f"Device detected: {r['stdout']}", "OK", condition=not self.args.json)
            if size := self._get_device_size():
                self.ptjsonlib.add_properties({"deviceSizeBytes": size})
        else:
            ptprint(f"Device NOT detected: {r['stderr']}", "ERROR", condition=not self.args.json)
        return r["success"]

    def test_2_first_sector(self) -> bool:
        ptprint("\nTest 2/5: First Sector Read (512 B)", "TITLE", condition=not self.args.json)
        if not self._check_command("dd"):
            self._add_test_node(2, "First Sector Read", False, error="dd not available")
            return False

        r = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null", f"bs={SECTOR_SIZE}", "count=1", "status=none"],
            TIMEOUT_FAST, RETRY_FAST)
        self._add_test_node(2, "First Sector Read", r["success"],
                            bytesRead=SECTOR_SIZE if r["success"] else 0, durationSeconds=r["duration"])
        ptprint(f"First sector {'readable' if r['success'] else 'FAILED'}",
                "OK" if r["success"] else "ERROR", condition=not self.args.json)
        return r["success"]

    def test_3_sequential_read(self) -> bool:
        ptprint("\nTest 3/5: Sequential Read (1 MB)", "TITLE", condition=not self.args.json)
        block_count = (1024 * 1024) // SECTOR_SIZE
        r = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null", f"bs={SECTOR_SIZE}", f"count={block_count}", "status=none"],
            TIMEOUT_SLOW, RETRY_SLOW)
        self._add_test_node(3, "Sequential Read", r["success"],
                            bytesRead=1024 * 1024 if r["success"] else 0, durationSeconds=r["duration"])
        ptprint(f"Sequential read {'OK' if r['success'] else 'FAILED'}",
                "OK" if r["success"] else "ERROR", condition=not self.args.json)
        return r["success"]

    def test_4_random_read(self) -> bool:
        ptprint("\nTest 4/5: Random Read (3 positions)", "TITLE", condition=not self.args.json)
        size      = self._get_device_size()
        positions = (
            [("start", 1024 * 1024), ("middle", size // 2), ("late", size - 10 * 1024 * 1024)]
            if size and size > 100 * 1024 * 1024
            else [("start", 512), ("middle", 1024 * 1024), ("late", 10 * 1024 * 1024)]
        )
        results, all_ok = [], True
        for label, offset in positions:
            r = self._run_command(
                ["dd", f"if={self.device}", "of=/dev/null", f"bs={SECTOR_SIZE}",
                 "count=1", f"skip={offset // SECTOR_SIZE}", "status=none"],
                TIMEOUT_SLOW, RETRY_SLOW)
            results.append({"position": label, "offsetBytes": offset, "success": r["success"]})
            ptprint(f"  {label.capitalize()} {'OK' if r['success'] else 'FAILED'}",
                    "OK" if r["success"] else "ERROR", condition=not self.args.json)
            if not r["success"]:
                all_ok = False

        self._add_test_node(4, "Random Read", all_ok, positions=results,
                            successfulReads=sum(1 for p in results if p["success"]),
                            totalReads=len(results))
        return all_ok

    def test_5_speed_measurement(self) -> Tuple[bool, float]:
        ptprint("\nTest 5/5: Read Speed (10 MB)", "TITLE", condition=not self.args.json)
        block_count = (10 * 1024 * 1024) // SECTOR_SIZE
        r     = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null", f"bs={SECTOR_SIZE}", f"count={block_count}", "status=none"],
            TIMEOUT_LONG, RETRY_SLOW)
        speed = (10 / r["duration"]) if r["success"] and r["duration"] > 0 else 0.0
        tag   = "OK" if speed >= SPEED_WARNING_MBS else ("WARNING" if speed >= SPEED_CRITICAL_MBS else "CRITICAL")

        self._add_test_node(5, "Speed Measurement", r["success"],
                            speedMBps=round(speed, 2), speedStatus=tag)
        if r["success"]:
            ptprint(f"Speed: {speed:.2f} MB/s ({tag})",
                    "OK" if tag == "OK" else tag, condition=not self.args.json)
        return speed >= SPEED_CRITICAL_MBS, speed

    # --- classification -----------------------------------------------------

    def determine_final_status(self) -> str:
        """
        READABLE  → all tests pass          → recommend dc3dd
        PARTIAL   → test 3 passes, not all  → recommend ddrescue
        UNREADABLE → test 1 or 2 fails      → physical repair required
        """
        res = {n["properties"]["testId"]: n["properties"]["success"]
               for n in self.ptjsonlib.json_data["result"]["nodes"]
               if n["type"] == "diagnosticTest"}

        if not res.get(1) or not res.get(2):
            status, tool, step = "UNREADABLE", "Physical repair required", 4
        elif all(res.values()):
            status, tool, step = "READABLE", "dc3dd", 5
        elif res.get(3):
            status, tool, step = "PARTIAL", "ddrescue", 5
        else:
            status, tool, step = "UNREADABLE", "Physical repair required", 4

        self.ptjsonlib.add_properties({"mediaStatus": status, "recommendedTool": tool, "nextStep": step})
        return status

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"MEDIA READABILITY TEST v{__version__} | Case: {self.case_id} | {self.device}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.test_1_os_detection() or not self.test_2_first_sector():
            self.determine_final_status()
            self.ptjsonlib.set_status("finished")
            return

        seq_ok = self.test_3_sequential_read()
        self.test_4_random_read()

        if seq_ok:
            self.test_5_speed_measurement()
        else:
            ptprint("Test 5/5: Speed – SKIPPED (sequential read failed, medium is PARTIAL)",
                    "WARNING", condition=not self.args.json)

        status = self.determine_final_status()
        props  = self.ptjsonlib.json_data["result"]["properties"]
        level  = {"READABLE": "OK", "PARTIAL": "WARNING", "UNREADABLE": "ERROR"}.get(status, "INFO")

        ptprint(f"\nResult: {status} | Tool: {props['recommendedTool']} | Next step: {props['nextStep']}",
                level, condition=not self.args.json)
        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe    = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.case_id)
        outfile = self.output_dir / f"{safe}_readability_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        outfile.write_text(self.ptjsonlib.get_result_json(), encoding="utf-8")
        ptprint(f"Report saved: {outfile}", "OK", condition=not self.args.json)
        return str(outfile)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SCRIPTNAME = "ptmediareadability"


def get_help() -> List[Dict]:
    return [
        {"description": ["Forensic media readability diagnostic – ptlibs compliant",
                         "5-stage READ-ONLY protocol per NIST SP 800-86 and ISO/IEC 27037:2012"]},
        {"usage": ["ptmediareadability <device> <case-id> [options]"]},
        {"usage_example": ["ptmediareadability /dev/sdb PHOTO-2025-001",
                           "ptmediareadability /dev/sdc CASE-042 --json",
                           "ptmediareadability /dev/sdd TEST-001 --dry-run"]},
        {"options": [
            ["device",            "",       "Block device path, e.g. /dev/sdb – REQUIRED"],
            ["case-id",           "",       "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir","<dir>",  f"Report directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",   "",       "Verbose logging"],
            ["--dry-run",         "",       "Simulate without touching the device"],
            ["--skip-wb-check",   "",       "Skip write-blocker confirmation prompt"],
            ["-j", "--json",      "",       "JSON output for Penterep platform"],
            ["-h", "--help",      "",       "Show help"],
            ["--version",         "",       "Show version"],
        ]},
        {"forensic_notes": ["ALWAYS use a hardware write-blocker",
                            "All I/O is READ-ONLY",
                            "Complies with NIST SP 800-86 and ISO/IEC 27037:2012"]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("device")
    parser.add_argument("case_id")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-v", "--verbose",    action="store_true")
    parser.add_argument("-q", "--quiet",      action="store_true")
    parser.add_argument("--dry-run",          action="store_true")
    parser.add_argument("--skip-wb-check",    action="store_true")
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

        if not args.dry_run and not args.json and not args.skip_wb_check:
            if not PtMediaReadability.confirm_write_blocker():
                ptprint("Test ABORTED – write-blocker required.", "ERROR", condition=True, colortext=True)
                return 99

        tool = PtMediaReadability(args)
        tool.run()
        tool.save_report()

        status = tool.ptjsonlib.json_data["result"]["properties"]["mediaStatus"]
        return {"READABLE": 0, "PARTIAL": 1, "UNREADABLE": 2}.get(status, 99)

    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())