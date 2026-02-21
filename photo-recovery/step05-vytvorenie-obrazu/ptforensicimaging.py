#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptforensicimaging - Forensic media imaging tool with intelligent tool selection

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import sys
import os
import subprocess
import shutil
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Skript je vždy spúšťaný ako nainštalovaný balíček cez Penterep platformu,
# relatívny import _version.py je preto vždy validný.
from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SCRIPTNAME         = "ptforensicimaging"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"
DEFAULT_LOG_DIR    = "/var/log/forensics"
TIMEOUT_HASH       = 7200   # 2 hours max for SHA-256 on large media
BLOCK_SIZE_MB      = 1
SPACE_MARGIN       = 1.1    # Require 110% of source size

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtForensicImaging:
    """
    Forensic media imaging tool – ptlibs compliant.

    Intelligent tool selection based on Step 3 readability results:
      READABLE   → dc3dd    (fast, integrated SHA-256 hashing)
      PARTIAL    → ddrescue (damaged sector recovery with mapfile)
      UNREADABLE → ERROR    (physical repair required first)

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

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tool_selected:     Optional[str] = None
        self.media_status:      Optional[str] = None
        self.source_size_bytes: Optional[int] = None

        self.ptjsonlib.add_properties({
            "caseId":           self.case_id,
            "devicePath":       self.device,
            "outputDirectory":  str(self.output_dir),
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "scriptVersion":    __version__,
            "toolSelected":     None,
            "mediaStatus":      None,
            "imagePath":        None,
            "imageFormat":      None,
            "sourceSizeBytes":  None,
            "sourceHash":       None,
            "durationSeconds":  None,
            "averageSpeedMBps": None,
            "errorSectors":     0,
            "imagingLog":       None,
            "dryRun":           self.dry_run,
        })

        ptprint(f"Initialized: device={self.device}, case={self.case_id}",
                "INFO", condition=not self.args.json)

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def confirm_write_blocker() -> bool:
        """Interactive write-blocker safety check. Must run before any device I/O."""
        ptprint("CRITICAL: Hardware write-blocker must be connected before imaging.",
                "WARNING", condition=True, colortext=True)
        ptprint("Verify: write-blocker powered, LED shows PROTECTED, source connected through it.",
                "INFO", condition=True)
        confirmed = input("\nConfirm write-blocker is active [yes/NO]: ").strip().lower() in ("yes", "y")
        ptprint("Write-blocker confirmed – proceeding." if confirmed
                else "Write-blocker NOT confirmed – imaging ABORTED.",
                "OK" if confirmed else "ERROR", condition=True)
        return confirmed

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        """Append a result node to the JSON output."""
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type,
            properties={"success": success, **kwargs},
        ))

    def _run_command(self, cmd: List[str], timeout: Optional[int] = None,
                     realtime: bool = False) -> Dict[str, Any]:
        """
        Execute a shell command with optional real-time output.
        Use realtime=True for long imaging operations to stream progress.
        """
        base = {"success": False, "stdout": "", "stderr": "", "returncode": -1, "duration": 0.0}

        if self.dry_run:
            ptprint(f"[DRY-RUN] {' '.join(cmd)}", "INFO", condition=not self.args.json)
            return {**base, "success": True, "stdout": "[DRY-RUN]"}

        try:
            t0 = time.time()
            if realtime:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1)
                lines = []
                for line in proc.stdout:
                    if not self.args.json and not self.args.quiet:
                        print(line, end="")
                    lines.append(line)
                proc.wait()
                base.update({"success": proc.returncode == 0, "stdout": "".join(lines),
                              "returncode": proc.returncode, "duration": time.time() - t0})
            else:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=timeout, check=False)
                base.update({"success": proc.returncode == 0, "stdout": proc.stdout.strip(),
                              "stderr": proc.stderr.strip(), "returncode": proc.returncode,
                              "duration": time.time() - t0})
        except subprocess.TimeoutExpired:
            base["stderr"] = f"Timeout after {timeout}s"
        except Exception as exc:
            base["stderr"] = str(exc)

        return base

    def _sha256_via_pipe(self) -> Optional[str]:
        """
        Calculate SHA-256 of source device via safe Popen pipe.
        Avoids shell=True – dd and sha256sum are connected directly via stdout/stdin.
        Used for ddrescue imaging where integrated hashing is unavailable.
        """
        try:
            dd = subprocess.Popen(
                ["dd", f"if={self.device}", "bs=1M", "status=none"],
                stdout=subprocess.PIPE
            )
            sha = subprocess.Popen(
                ["sha256sum"],
                stdin=dd.stdout, stdout=subprocess.PIPE, text=True
            )
            dd.stdout.close()
            out, _ = sha.communicate(timeout=TIMEOUT_HASH)
            dd.wait()
            if sha.returncode == 0 and out:
                return out.strip().split()[0]
        except Exception as exc:
            ptprint(f"Hash calculation failed: {exc}", "WARNING", condition=not self.args.json)
        return None

    # --- steps --------------------------------------------------------------

    def load_readability_results(self) -> bool:
        """Step 1: Load Step 3 JSON report and select imaging tool."""
        ptprint("\n[1/3] Loading Readability Test Results", "TITLE", condition=not self.args.json)

        # Find newest readability report for this case
        candidates = sorted(
            self.output_dir.glob(f"{self.case_id}_readability_*.json"),
            reverse=True
        )
        if not candidates:
            ptprint(f"Readability results not found in {self.output_dir}.",
                    "ERROR", condition=not self.args.json)
            ptprint("Run Step 3 (ptmediareadability) first.", "ERROR", condition=not self.args.json)
            self._add_node("prerequisiteCheck", False,
                           checkName="ReadabilityResults", error="Missing Step 3 results")
            return False

        try:
            data = json.loads(candidates[0].read_text(encoding="utf-8"))
            self.media_status = (data.get("result", {})
                                     .get("properties", {})
                                     .get("mediaStatus", "UNKNOWN"))
        except Exception as exc:
            ptprint(f"Error reading readability results: {exc}", "ERROR", condition=not self.args.json)
            self._add_node("prerequisiteCheck", False,
                           checkName="ReadabilityResults", error=str(exc))
            return False

        if self.media_status == "READABLE":
            self.tool_selected = "dc3dd"
            ptprint("Media: READABLE → tool: dc3dd", "OK", condition=not self.args.json)
        elif self.media_status == "PARTIAL":
            self.tool_selected = "ddrescue"
            ptprint("Media: PARTIAL → tool: ddrescue", "WARNING", condition=not self.args.json)
        else:
            ptprint("Media is UNREADABLE – physical repair (Step 4) required first.",
                    "ERROR", condition=not self.args.json)
            self._add_node("prerequisiteCheck", False, checkName="MediaStatus",
                           mediaStatus=self.media_status, error="Media unreadable")
            return False

        self.ptjsonlib.add_properties({"toolSelected": self.tool_selected,
                                       "mediaStatus": self.media_status})
        self._add_node("prerequisiteCheck", True, checkName="ReadabilityResults",
                       mediaStatus=self.media_status, toolSelected=self.tool_selected,
                       resultsFile=str(candidates[0]))
        return True

    def check_storage_space(self) -> bool:
        """Step 2: Verify target has at least 110% of source device size."""
        ptprint("\n[2/3] Checking Target Storage Space", "TITLE", condition=not self.args.json)

        r = self._run_command(["blockdev", "--getsize64", self.device], timeout=10)
        if not r["success"] or not r["stdout"].isdigit():
            ptprint("Could not determine source size – skipping space check.",
                    "WARNING", condition=not self.args.json)
            self._add_node("storageSpaceCheck", True, skipped=True,
                           reason="Could not determine source size")
            return True

        self.source_size_bytes = int(r["stdout"])
        source_gb   = self.source_size_bytes / (1024 ** 3)
        required_gb = (self.source_size_bytes * SPACE_MARGIN) / (1024 ** 3)
        avail_gb    = shutil.disk_usage(self.output_dir).free / (1024 ** 3)

        ptprint(f"Source: {source_gb:.2f} GB | Required (110%): {required_gb:.2f} GB | "
                f"Available: {avail_gb:.2f} GB", "INFO", condition=not self.args.json)

        self.ptjsonlib.add_properties({"sourceSizeBytes": self.source_size_bytes})

        if avail_gb < required_gb:
            ptprint(f"Insufficient space – need {required_gb:.2f} GB, have {avail_gb:.2f} GB.",
                    "ERROR", condition=not self.args.json)
            self._add_node("storageSpaceCheck", False,
                           sourceSizeGB=round(source_gb, 2),
                           requiredSpaceGB=round(required_gb, 2),
                           availableSpaceGB=round(avail_gb, 2))
            return False

        ptprint(f"Space OK – {avail_gb - required_gb:.2f} GB margin.",
                "OK", condition=not self.args.json)
        self._add_node("storageSpaceCheck", True,
                       sourceSizeGB=round(source_gb, 2),
                       requiredSpaceGB=round(required_gb, 2),
                       availableSpaceGB=round(avail_gb, 2),
                       marginGB=round(avail_gb - required_gb, 2))
        return True

    def run_imaging_dc3dd(self) -> bool:
        """Step 3a: Create forensic image with dc3dd (READABLE media)."""
        ptprint("\n[3/3] Forensic Imaging – dc3dd", "TITLE", condition=not self.args.json)

        image_file = self.output_dir / f"{self.case_id}.dd"
        hash_file  = self.output_dir / f"{self.case_id}.dd.sha256"
        log_file   = self.output_dir / f"{self.case_id}_imaging.log"

        ptprint(f"Source: {self.device} → Target: {image_file}", "INFO", condition=not self.args.json)

        cmd = ["dc3dd", f"if={self.device}", f"of={image_file}",
               "hash=sha256", f"log={log_file}", f"bs={BLOCK_SIZE_MB}M", "progress=on"]
        ptprint(f"Command: {' '.join(cmd)}", "INFO", condition=not self.args.json)

        t0 = time.time()
        r  = self._run_command(cmd, realtime=True)
        duration = time.time() - t0

        if not r["success"]:
            ptprint(f"Imaging failed: {r.get('stderr', 'unknown error')}",
                    "ERROR", condition=not self.args.json)
            self._add_node("imagingProcess", False, tool="dc3dd",
                           error=r.get("stderr", ""), returnCode=r["returncode"])
            return False

        ptprint(f"Imaging completed in {duration:.0f}s ({duration/60:.1f} min).",
                "OK", condition=not self.args.json)

        # Extract hash from dc3dd log file
        source_hash = None
        if log_file.exists():
            for line in log_file.read_text().splitlines():
                if "sha256" in line.lower() and ":" in line:
                    source_hash = line.split(":")[-1].strip()
                    break

        if source_hash:
            ptprint(f"Source SHA-256: {source_hash}", "OK", condition=not self.args.json)
            hash_file.write_text(f"{source_hash}  {image_file.name}\n")
        else:
            ptprint("Could not extract hash from log – check log file manually.",
                    "WARNING", condition=not self.args.json)

        size_mb   = image_file.stat().st_size / (1024 ** 2) if image_file.exists() else 0
        avg_speed = size_mb / duration if duration > 0 else 0

        self.ptjsonlib.add_properties({
            "imagePath": str(image_file), "imageFormat": "raw (.dd)",
            "sourceHash": source_hash, "durationSeconds": round(duration, 2),
            "averageSpeedMBps": round(avg_speed, 2), "imagingLog": str(log_file),
        })
        self._add_node("imagingProcess", True, tool="dc3dd",
                       imagePath=str(image_file), sourceHash=source_hash,
                       durationSeconds=round(duration, 2),
                       averageSpeedMBps=round(avg_speed, 2),
                       command=" ".join(cmd), logFile=str(log_file))
        return True

    def run_imaging_ddrescue(self) -> bool:
        """Step 3b: Create forensic image with ddrescue (PARTIAL media)."""
        ptprint("\n[3/3] Forensic Imaging – ddrescue (damaged media recovery)",
                "TITLE", condition=not self.args.json)

        image_file = self.output_dir / f"{self.case_id}.dd"
        mapfile    = self.output_dir / f"{self.case_id}.mapfile"
        hash_file  = self.output_dir / f"{self.case_id}.dd.sha256"
        log_file   = self.output_dir / f"{self.case_id}_imaging.log"

        ptprint(f"Source: {self.device} → Target: {image_file}", "INFO", condition=not self.args.json)
        ptprint(f"Mapfile: {mapfile}", "INFO", condition=not self.args.json)

        cmd = ["ddrescue", "-f", "-v", self.device, str(image_file), str(mapfile)]
        ptprint(f"Command: {' '.join(cmd)}", "INFO", condition=not self.args.json)

        t0 = time.time()
        r  = self._run_command(cmd, realtime=True)
        duration = time.time() - t0

        if not r["success"] and not self.dry_run:
            ptprint(f"Imaging failed: {r.get('stderr', 'unknown error')}",
                    "ERROR", condition=not self.args.json)
            self._add_node("imagingProcess", False, tool="ddrescue",
                           error=r.get("stderr", ""), returnCode=r["returncode"])
            return False

        ptprint(f"Imaging completed in {duration:.0f}s ({duration/60:.1f} min).",
                "OK", condition=not self.args.json)

        # Count bad sectors from mapfile
        bad_sectors = 0
        if mapfile.exists():
            bad_sectors = mapfile.read_text().count("-")
            ptprint(f"{bad_sectors} bad sector(s) detected." if bad_sectors
                    else "All sectors read successfully.",
                    "WARNING" if bad_sectors else "OK", condition=not self.args.json)

        # SHA-256 via safe Popen pipe – no shell=True
        ptprint("Calculating SHA-256 hash of source...", "INFO", condition=not self.args.json)
        source_hash = self._sha256_via_pipe()
        if source_hash:
            ptprint(f"Source SHA-256: {source_hash}", "OK", condition=not self.args.json)
            hash_file.write_text(f"{source_hash}  {image_file.name}\n")
        else:
            ptprint("Hash calculation failed – manual verification required.",
                    "WARNING", condition=not self.args.json)

        size_mb   = image_file.stat().st_size / (1024 ** 2) if image_file.exists() else 0
        avg_speed = size_mb / duration if duration > 0 else 0

        log_file.write_text(
            f"=== DDRESCUE IMAGING LOG ===\n"
            f"Case ID:     {self.case_id}\n"
            f"Source:      {self.device}\n"
            f"Target:      {image_file}\n"
            f"Start:       {datetime.fromtimestamp(t0).isoformat()}\n"
            f"Duration:    {duration:.2f}s\n"
            f"Bad sectors: {bad_sectors}\n"
            f"Avg speed:   {avg_speed:.2f} MB/s\n"
            f"Source hash: {source_hash or 'N/A'}\n\n"
            f"=== DDRESCUE OUTPUT ===\n{r['stdout']}"
        )

        self.ptjsonlib.add_properties({
            "imagePath": str(image_file), "imageFormat": "raw (.dd)",
            "sourceHash": source_hash, "durationSeconds": round(duration, 2),
            "averageSpeedMBps": round(avg_speed, 2), "errorSectors": bad_sectors,
            "imagingLog": str(log_file),
        })
        self._add_node("imagingProcess", True, tool="ddrescue",
                       imagePath=str(image_file), sourceHash=source_hash,
                       durationSeconds=round(duration, 2),
                       averageSpeedMBps=round(avg_speed, 2), badSectors=bad_sectors,
                       mapfile=str(mapfile), command=" ".join(cmd), logFile=str(log_file))
        return True

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        """Execute the full imaging workflow."""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FORENSIC IMAGING v{__version__} | Case: {self.case_id} | {self.device}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_readability_results():
            self.ptjsonlib.set_status("finished"); return
        if not self.check_storage_space():
            self.ptjsonlib.set_status("finished"); return

        success = (self.run_imaging_dc3dd() if self.tool_selected == "dc3dd"
                   else self.run_imaging_ddrescue())

        props = self.ptjsonlib.json_data["result"]["properties"]
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        if success:
            ptprint("IMAGING COMPLETED SUCCESSFULLY", "OK", condition=not self.args.json)
            ptprint(f"Image:    {props['imagePath']}", "INFO", condition=not self.args.json)
            ptprint(f"Duration: {props['durationSeconds']:.0f}s "
                    f"({props['durationSeconds']/60:.1f} min)", "INFO", condition=not self.args.json)
            ptprint(f"Speed:    {props['averageSpeedMBps']:.2f} MB/s",
                    "INFO", condition=not self.args.json)
            if props["errorSectors"] > 0:
                ptprint(f"Bad sectors: {props['errorSectors']}", "WARNING",
                        condition=not self.args.json)
            ptprint(f"SHA-256:  {props['sourceHash']}", "INFO", condition=not self.args.json)
            ptprint("Next: Step 6 – Hash Verification", "INFO", condition=not self.args.json)
        else:
            ptprint("IMAGING FAILED", "ERROR", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        """Output JSON report to stdout (--json) or to file."""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        outfile = self.output_dir / f"{self.case_id}_imaging.json"
        outfile.write_text(self.ptjsonlib.get_result_json(), encoding="utf-8")
        ptprint(f"Report saved: {outfile}", "OK", condition=not self.args.json)
        return str(outfile)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_help() -> List[Dict]:
    return [
        {"description": ["Forensic media imaging tool – ptlibs compliant",
                         "Intelligent tool selection based on Step 3 readability results"]},
        {"usage": ["ptforensicimaging <device> <case-id> [options]"]},
        {"usage_example": ["ptforensicimaging /dev/sdb PHOTO-2025-001",
                           "ptforensicimaging /dev/sdc CASE-042 --json",
                           "ptforensicimaging /dev/sdd TEST-001 --dry-run"]},
        {"options": [
            ["device",             "",      "Block device path, e.g. /dev/sdb – REQUIRED"],
            ["case-id",            "",      "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate without touching the device"],
            ["--skip-wb-check",    "",      "Skip write-blocker confirmation prompt"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"tool_selection": [
            "READABLE  → dc3dd    (fast, integrated SHA-256 hashing)",
            "PARTIAL   → ddrescue (damaged sector recovery with mapfile)",
            "UNREADABLE → ERROR   (physical repair via Step 4 required)",
        ]},
        {"forensic_notes": [
            "ALWAYS use a hardware write-blocker",
            "Requires Step 3 (ptmediareadability) results",
            "110% free space required on target storage",
            "Complies with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
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
            if not PtForensicImaging.confirm_write_blocker():
                ptprint("Imaging ABORTED – write-blocker required.", "ERROR",
                        condition=True, colortext=True)
                return 99

        imager = PtForensicImaging(args)
        imager.run()
        imager.save_report()

        return 0 if imager.ptjsonlib.json_data["result"]["properties"].get("imagePath") else 1

    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())