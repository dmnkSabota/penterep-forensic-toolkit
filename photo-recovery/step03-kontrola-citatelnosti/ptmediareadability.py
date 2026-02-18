#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno
    
    ptmediareadability - Forensic media readability diagnostic tool
    
    ptmediareadability is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    ptmediareadability is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with ptmediareadability.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/reports"
DEFAULT_LOG_DIR = "/var/log/forensics"
TIMEOUT_SHORT = 30
TIMEOUT_MEDIUM = 60
TIMEOUT_LONG = 120
SPEED_CRITICAL_MBS = 5.0
SPEED_WARNING_MBS = 20.0
SECTOR_SIZE = 512
RETRY_COUNT = 3


# ============================================================================
# MODULE-LEVEL UTILITY FUNCTIONS
# ============================================================================

def confirm_write_blocker() -> bool:
    """
    Confirm write-blocker is connected (interactive mode only)
    CRITICAL SAFETY CHECK for forensic integrity
    
    Returns:
        bool: True if write-blocker confirmed, False otherwise
    """
    ptprint("\n" + "!" * 70, "WARNING", condition=True, colortext=True)
    ptprint("CRITICAL SAFETY CHECK", "WARNING", condition=True, colortext=True)
    ptprint("!" * 70, "WARNING", condition=True, colortext=True)
    ptprint("", "TEXT", condition=True)
    ptprint("A HARDWARE WRITE-BLOCKER is MANDATORY for forensic examination!", 
           "WARNING", condition=True, colortext=True)
    ptprint("This tool performs READ-ONLY operations, but hardware protection", 
           "INFO", condition=True)
    ptprint("is required to maintain chain of custody and evidence integrity.", 
           "INFO", condition=True)
    ptprint("", "TEXT", condition=True)
    ptprint("Write-blocker requirements:", "INFO", condition=True)
    ptprint("  • Hardware write-blocker connected and powered", "TEXT", condition=True)
    ptprint("  • Write protection LED indicator shows PROTECTED", "TEXT", condition=True)
    ptprint("  • Device connected through write-blocker interface", "TEXT", condition=True)
    ptprint("", "TEXT", condition=True)
    
    response = input("Confirm write-blocker is connected and active [yes/NO]: ").strip().lower()
    
    if response in ['yes', 'y']:
        ptprint("✓ Write-blocker confirmed - proceeding with test", 
               "OK", condition=True)
        return True
    else:
        ptprint("✗ Write-blocker NOT confirmed - test ABORTED", 
               "ERROR", condition=True, colortext=True)
        ptprint("DO NOT proceed without proper write protection!", 
               "WARNING", condition=True, colortext=True)
        return False


# ============================================================================
# MAIN FORENSIC TOOL CLASS
# ============================================================================

class PtMediaReadability:
    """
    Forensic media readability diagnostic tool - ptlibs compliant
    
    Performs 5-stage diagnostic protocol to assess storage media condition:
    1. OS Detection (lsblk)
    2. First Sector Read (512 bytes)
    3. Sequential Read (1 MB)
    4. Random Read (3 positions)
    5. Speed Measurement (10 MB)
    
    Generates structured JSON reports for chain of custody documentation.
    Complies with NIST SP 800-86 and ISO/IEC 27037 standards.
    """
    
    def __init__(self, args):
        """Initialize forensic readability test with ptlibs integration"""
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        
        # Validate device path
        if not self.args.device.startswith('/dev/'):
            self.ptjsonlib.end_error(
                f"Invalid device path: {self.args.device}. Must start with /dev/",
                self.args.json
            )
            sys.exit(99)
        
        # Check device exists (skip in dry-run mode)
        if not self.args.dry_run and not os.path.exists(self.args.device):
            self.ptjsonlib.end_error(
                f"Device not found: {self.args.device}. Verify with 'lsblk'",
                self.args.json
            )
            sys.exit(99)
        
        self.device = self.args.device
        self.case_id = self.args.case_id.strip()
        self.dry_run = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        
        # Setup logging
        self.logger = self._setup_logger()
        
        # Add forensic metadata as properties
        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "device": self.device,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "deviceSizeBytes": None,
            "mediaStatus": "UNKNOWN",
            "recommendedTool": None,
            "nextStep": None,
            "dryRun": self.dry_run
        })
        
        ptprint(f"Initialized: device={self.device}, case={self.case_id}", 
               "INFO", condition=not self.args.json)
    
    def _setup_logger(self) -> logging.Logger:
        """Setup forensic logging system"""
        log_dir = Path(DEFAULT_LOG_DIR)
        
        if not self.dry_run:
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                ptprint(f"WARNING: Cannot create log directory {log_dir}, using /tmp",
                       "WARNING", condition=not self.args.json)
                log_dir = Path("/tmp/forensics")
                log_dir.mkdir(parents=True, exist_ok=True)
        
        logger = logging.getLogger("media_readability")
        logger.setLevel(logging.DEBUG)
        
        if not self.dry_run:
            timestamp = datetime.now().strftime("%Y%m%d")
            log_file = log_dir / f"media_readability_{timestamp}.log"
            fh = logging.FileHandler(log_file)
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        
        if self.args.verbose and not self.args.json:
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            logger.addHandler(ch)
        
        return logger
    
    def _check_command_exists(self, command: str) -> bool:
        """Check if command is available"""
        try:
            subprocess.run(
                ["which", command],
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
    
    def _run_command(self, cmd: List[str], timeout: int = TIMEOUT_SHORT) -> Dict[str, Any]:
        """Execute command with timeout, retry logic, and error handling"""
        result = {
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "duration": 0.0
        }
        
        if self.dry_run:
            ptprint(f"[DRY-RUN] Would execute: {' '.join(cmd)}", 
                   "INFO", condition=not self.args.json)
            result["success"] = True
            result["stdout"] = f"[DRY-RUN] Simulated success"
            return result
        
        cmd_str = ' '.join(cmd)
        self.logger.debug(f"Executing: {cmd_str}")
        
        for attempt in range(RETRY_COUNT):
            try:
                start_time = datetime.now()
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
                duration = (datetime.now() - start_time).total_seconds()
                
                result.update({
                    "success": proc.returncode == 0,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                    "returncode": proc.returncode,
                    "duration": duration
                })
                
                if result["success"]:
                    self.logger.debug(f"Command succeeded in {duration:.2f}s")
                    break
                else:
                    self.logger.warning(f"Failed (attempt {attempt + 1}/{RETRY_COUNT})")
                    if "Permission denied" in proc.stderr or "not found" in proc.stderr:
                        break
            except subprocess.TimeoutExpired:
                self.logger.error(f"Timeout after {timeout}s")
                result["stderr"] = f"Timeout after {timeout}s"
            except Exception as e:
                self.logger.error(f"Exception: {e}")
                result["stderr"] = str(e)
        
        return result
    
    def _get_device_size(self) -> Optional[int]:
        """Get device size in bytes"""
        result = self._run_command(["blockdev", "--getsize64", self.device])
        if result["success"] and result["stdout"].isdigit():
            return int(result["stdout"])
        
        result = self._run_command(["lsblk", "-b", "-d", "-n", "-o", "SIZE", self.device])
        if result["success"] and result["stdout"].isdigit():
            return int(result["stdout"])
        
        return None
    
    def test_1_os_detection(self) -> bool:
        """Test 1/5: OS Detection using lsblk"""
        ptprint("\nTest 1/5: OS Detection (lsblk)", "TITLE", condition=not self.args.json)
        
        if not self._check_command_exists("lsblk"):
            error_msg = "lsblk not found. Install: apt-get install util-linux"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            self.logger.error(error_msg)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "diagnosticTest",
                properties={"testId": 1, "testName": "OS Detection", "success": False, "error": "Command not available"}
            ))
            return False
        
        result = self._run_command(["lsblk", "-d", "-n", "-o", "NAME,SIZE,TYPE,MODEL", self.device], TIMEOUT_SHORT)
        
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "diagnosticTest",
            properties={
                "testId": 1,
                "testName": "OS Detection",
                "command": f"lsblk -d -n -o NAME,SIZE,TYPE,MODEL {self.device}",
                "success": result["success"],
                "output": result["stdout"] if result["success"] else result["stderr"],
                "durationSeconds": result["duration"],
                "returnCode": result["returncode"]
            }
        ))
        
        if result["success"]:
            ptprint(f"✓ Device detected: {result['stdout']}", "OK", condition=not self.args.json)
            device_size = self._get_device_size()
            if device_size:
                self.ptjsonlib.add_properties({"deviceSizeBytes": device_size})
        else:
            ptprint(f"✗ Device NOT detected: {result['stderr']}", "ERROR", condition=not self.args.json)
        
        return result["success"]
    
    def test_2_first_sector(self) -> bool:
        """Test 2/5: First Sector Read"""
        ptprint("\nTest 2/5: First Sector Read (512 bytes)", "TITLE", condition=not self.args.json)
        
        if not self._check_command_exists("dd"):
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "diagnosticTest",
                properties={"testId": 2, "testName": "First Sector Read", "success": False}
            ))
            return False
        
        result = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null", f"bs={SECTOR_SIZE}", "count=1", "status=none"],
            TIMEOUT_SHORT
        )
        
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "diagnosticTest",
            properties={
                "testId": 2,
                "testName": "First Sector Read",
                "success": result["success"],
                "bytesRead": SECTOR_SIZE if result["success"] else 0,
                "durationSeconds": result["duration"]
            }
        ))
        
        if result["success"]:
            ptprint(f"✓ First sector readable", "OK", condition=not self.args.json)
        else:
            ptprint(f"✗ First sector FAILED", "ERROR", condition=not self.args.json)
        
        return result["success"]
    
    def test_3_sequential_read(self) -> bool:
        """Test 3/5: Sequential Read (1 MB)"""
        ptprint("\nTest 3/5: Sequential Read (1 MB)", "TITLE", condition=not self.args.json)
        
        block_count = (1 * 1024 * 1024) // SECTOR_SIZE
        result = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null", f"bs={SECTOR_SIZE}", f"count={block_count}", "status=none"],
            TIMEOUT_MEDIUM
        )
        
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "diagnosticTest",
            properties={
                "testId": 3,
                "testName": "Sequential Read",
                "success": result["success"],
                "bytesRead": 1024 * 1024 if result["success"] else 0,
                "durationSeconds": result["duration"]
            }
        ))
        
        if result["success"]:
            ptprint(f"✓ Sequential read OK", "OK", condition=not self.args.json)
        else:
            ptprint(f"✗ Sequential read FAILED", "ERROR", condition=not self.args.json)
        
        return result["success"]
    
    def test_4_random_read(self) -> bool:
        """Test 4/5: Random Read (3 positions)"""
        ptprint("\nTest 4/5: Random Read (3 positions)", "TITLE", condition=not self.args.json)
        
        device_size = self._get_device_size()
        
        if device_size and device_size > 100 * 1024 * 1024:
            positions = [
                ("start", 1024 * 1024),
                ("middle", device_size // 2),
                ("late", device_size - 10 * 1024 * 1024)
            ]
        else:
            positions = [("start", 512), ("middle", 1024 * 1024), ("late", 10 * 1024 * 1024)]
        
        results = []
        all_success = True
        
        for label, offset in positions:
            skip_blocks = offset // SECTOR_SIZE
            result = self._run_command(
                ["dd", f"if={self.device}", "of=/dev/null", f"bs={SECTOR_SIZE}", "count=1", f"skip={skip_blocks}", "status=none"],
                TIMEOUT_MEDIUM
            )
            
            results.append({"position": label, "offsetBytes": offset, "success": result["success"]})
            
            if result["success"]:
                ptprint(f"  ✓ {label.capitalize()} position OK", "OK", condition=not self.args.json)
            else:
                ptprint(f"  ✗ {label.capitalize()} FAILED", "ERROR", condition=not self.args.json)
                all_success = False
        
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "diagnosticTest",
            properties={
                "testId": 4,
                "testName": "Random Read",
                "success": all_success,
                "positions": results,
                "successfulReads": sum(1 for r in results if r["success"]),
                "totalReads": len(results)
            }
        ))
        
        return all_success
    
    def test_5_speed_measurement(self) -> Tuple[bool, float]:
        """Test 5/5: Speed Measurement (10 MB)"""
        ptprint("\nTest 5/5: Read Speed Measurement (10 MB)", "TITLE", condition=not self.args.json)
        
        block_count = (10 * 1024 * 1024) // SECTOR_SIZE
        result = self._run_command(
            ["dd", f"if={self.device}", "of=/dev/null", f"bs={SECTOR_SIZE}", f"count={block_count}", "status=none"],
            TIMEOUT_LONG
        )
        
        speed_mbs = 0.0
        if result["success"] and result["duration"] > 0:
            speed_mbs = 10 / result["duration"]
        
        speed_ok = speed_mbs >= SPEED_CRITICAL_MBS if result["success"] else False
        
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "diagnosticTest",
            properties={
                "testId": 5,
                "testName": "Speed Measurement",
                "success": result["success"],
                "speedMBps": round(speed_mbs, 2),
                "speedStatus": "CRITICAL" if speed_mbs < SPEED_CRITICAL_MBS else ("WARNING" if speed_mbs < SPEED_WARNING_MBS else "OK")
            }
        ))
        
        if result["success"]:
            if speed_mbs >= SPEED_WARNING_MBS:
                ptprint(f"✓ Speed: {speed_mbs:.2f} MB/s (GOOD)", "OK", condition=not self.args.json)
            elif speed_mbs >= SPEED_CRITICAL_MBS:
                ptprint(f"⚠ Speed: {speed_mbs:.2f} MB/s (SLOW)", "WARNING", condition=not self.args.json)
            else:
                ptprint(f"✗ Speed: {speed_mbs:.2f} MB/s (CRITICAL)", "ERROR", condition=not self.args.json)
        
        return speed_ok, speed_mbs
    
    def determine_final_status(self) -> str:
        """Determine final media status"""
        nodes = self.ptjsonlib.json_data["result"]["nodes"]
        test_results = {
            node["properties"]["testId"]: node["properties"]["success"]
            for node in nodes if node["type"] == "diagnosticTest"
        }
        
        if not test_results.get(1, False):
            status = "UNREADABLE"
            recommendation = "Physical repair required (device not detected)"
            next_step = 4
        elif not test_results.get(2, False):
            status = "UNREADABLE"
            recommendation = "Physical repair required (first sector unreadable)"
            next_step = 4
        elif all(test_results.values()):
            status = "READABLE"
            recommendation = "dd"
            next_step = 5
        elif test_results.get(3, False):
            status = "PARTIAL"
            recommendation = "ddrescue"
            next_step = 5
        else:
            status = "UNREADABLE"
            recommendation = "Physical repair required"
            next_step = 4
        
        self.ptjsonlib.add_properties({
            "mediaStatus": status,
            "recommendedTool": recommendation,
            "nextStep": next_step
        })
        
        return status
    
    def run(self) -> None:
        """Main execution method"""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"MEDIA READABILITY TEST v{__version__}", "TITLE", condition=not self.args.json)
        ptprint(f"Case ID: {self.case_id}", "INFO", condition=not self.args.json)
        ptprint(f"Device: {self.device}", "INFO", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        
        if not self.test_1_os_detection():
            ptprint("\n✗ OS detection failed - aborting", "ERROR", condition=not self.args.json)
            self.determine_final_status()
            self.ptjsonlib.set_status("finished")
            return
        
        if not self.test_2_first_sector():
            ptprint("\n✗ First sector failed - aborting", "ERROR", condition=not self.args.json)
            self.determine_final_status()
            self.ptjsonlib.set_status("finished")
            return
        
        seq_ok = self.test_3_sequential_read()
        self.test_4_random_read()
        
        if seq_ok:
            self.test_5_speed_measurement()
        
        status = self.determine_final_status()
        
        # Print summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("TEST RESULTS SUMMARY", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        
        props = self.ptjsonlib.json_data["result"]["properties"]
        bullet_map = {"READABLE": "OK", "PARTIAL": "WARNING", "UNREADABLE": "ERROR"}
        
        ptprint(f"Media Status: {status}", bullet_map.get(status, "INFO"), condition=not self.args.json)
        ptprint(f"Recommended Tool: {props['recommendedTool']}", "INFO", condition=not self.args.json)
        ptprint(f"Next Step: {props['nextStep']}", "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        
        self.ptjsonlib.set_status("finished")
    
    def save_report(self) -> Optional[str]:
        """Save JSON report"""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None
        else:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            safe_case_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.case_id)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_case_id}_readability_{timestamp}.json"
            filepath = self.output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.ptjsonlib.get_result_json())
            
            ptprint(f"\n✓ Report saved: {filepath}", "OK", condition=not self.args.json)
            return str(filepath)


# ============================================================================
# MODULE-LEVEL WORKFLOW FUNCTIONS
# ============================================================================

def get_help():
    """Return help structure for ptprinthelper"""
    return [
        {"description": [
            "Forensic media readability diagnostic tool - ptlibs compliant",
            "Performs 5-stage diagnostic protocol to assess storage media condition"
        ]},
        {"usage": ["ptmediareadability <device> <case-id> [options]"]},
        {"usage_example": [
            "ptmediareadability /dev/sdb PHOTO-2025-001",
            "ptmediareadability /dev/sdc CASE-042 --json",
            "ptmediareadability /dev/sdd TEST-001 --dry-run"
        ]},
        {"options": [
            ["device", "", "Device path (e.g., /dev/sdb) - REQUIRED"],
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose", "", "Verbose logging"],
            ["--dry-run", "", "Simulate execution"],
            ["--skip-wb-check", "", "Skip write-blocker confirmation"],
            ["-j", "--json", "", "JSON output for platform"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"]
        ]},
        {"forensic_notes": [
            "ALWAYS use hardware write-blocker",
            "Tool performs READ-ONLY operations",
            "Complies with NIST SP 800-86 and ISO/IEC 27037"
        ]}
    ]


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} - Forensic media readability diagnostic"
    )
    
    parser.add_argument("device", help="Device path (e.g., /dev/sdb)")
    parser.add_argument("case_id", help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-wb-check", action="store_true")
    parser.add_argument("-j", "--json", action="store_true")
    parser.add_argument("--version", action='version', version=f'{SCRIPTNAME} {__version__}')
    
    # Platform integration arguments
    parser.add_argument("--socket-address", type=str, default=None)
    parser.add_argument("--socket-port", type=str, default=None)
    parser.add_argument("--process-ident", type=str, default=None)
    
    if len(sys.argv) == 1 or "-h" in sys.argv or "--help" in sys.argv:
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)
    
    args = parser.parse_args()
    
    if args.json:
        args.quiet = True
    
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    
    return args


def main():
    """Main entry point"""
    global SCRIPTNAME
    SCRIPTNAME = "ptmediareadability"
    
    try:
        args = parse_args()
        
        # Write-blocker confirmation
        if not args.dry_run and not args.json and not args.skip_wb_check:
            if not confirm_write_blocker():
                ptprint("\n✗ Test ABORTED - write-blocker required!", "ERROR", condition=True, colortext=True)
                return 99
        
        # Run test
        script = PtMediaReadability(args)
        script.run()
        script.save_report()
        
        # Return exit code
        status = script.ptjsonlib.json_data["result"]["properties"]["mediaStatus"]
        exit_codes = {"READABLE": 0, "PARTIAL": 1, "UNREADABLE": 2, "UNKNOWN": 99}
        return exit_codes.get(status, 99)
        
    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as e:
        ptprint(f"ERROR: {e}", "ERROR", condition=True)
        return 99


# ============================================================================
# SCRIPT ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    sys.exit(main())
