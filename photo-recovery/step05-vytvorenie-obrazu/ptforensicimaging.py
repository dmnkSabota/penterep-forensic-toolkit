#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno
    
    ptforensicimaging - Forensic media imaging tool with intelligent tool selection
    
    ptforensicimaging is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    ptforensicimaging is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with ptforensicimaging.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import subprocess
import shutil
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/images"
DEFAULT_LOG_DIR = "/var/log/forensics"
TIMEOUT_HASH = 7200  # 2 hours for hash calculation
BLOCK_SIZE_MB = 1
SPACE_MARGIN = 1.1  # Require 110% of source size


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
    ptprint("CRITICAL SAFETY CHECK - WRITE-BLOCKER VERIFICATION", "WARNING", condition=True, colortext=True)
    ptprint("!" * 70, "WARNING", condition=True, colortext=True)
    ptprint("", "TEXT", condition=True)
    ptprint("A HARDWARE WRITE-BLOCKER is MANDATORY for forensic imaging!", 
           "WARNING", condition=True, colortext=True)
    ptprint("This tool will CREATE A FORENSIC IMAGE but cannot proceed", 
           "INFO", condition=True)
    ptprint("without verified write protection on the source device.", 
           "INFO", condition=True)
    ptprint("", "TEXT", condition=True)
    ptprint("Write-blocker requirements:", "INFO", condition=True)
    ptprint("  • Hardware write-blocker connected and powered", "TEXT", condition=True)
    ptprint("  • Write protection LED indicator shows PROTECTED", "TEXT", condition=True)
    ptprint("  • Source device connected ONLY through write-blocker", "TEXT", condition=True)
    ptprint("  • NEVER connect source device directly to computer", "TEXT", condition=True)
    ptprint("", "TEXT", condition=True)
    
    response = input("Confirm write-blocker is connected and active [yes/NO]: ").strip().lower()
    
    if response in ['yes', 'y']:
        ptprint("✓ Write-blocker confirmed - proceeding with imaging", 
               "OK", condition=True)
        return True
    else:
        ptprint("✗ Write-blocker NOT confirmed - imaging ABORTED", 
               "ERROR", condition=True, colortext=True)
        ptprint("DO NOT proceed without proper write protection!", 
               "WARNING", condition=True, colortext=True)
        return False


# ============================================================================
# MAIN FORENSIC IMAGING CLASS
# ============================================================================

class PtForensicImaging:
    """
    Forensic media imaging tool - ptlibs compliant
    
    Intelligent tool selection based on media condition:
    - READABLE media → dc3dd (fast, integrated hashing)
    - PARTIAL media → ddrescue (damaged media recovery)
    - UNREADABLE media → ERROR (requires physical repair first)
    
    Creates bit-for-bit forensic image with SHA-256 hash calculation.
    Complies with NIST SP 800-86 and ISO/IEC 27037 standards.
    """
    
    def __init__(self, args):
        """
        Initialize forensic imaging process with ptlibs integration
        
        Args:
            args: Parsed command-line arguments
        """
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        
        # Validate device path
        if not self.args.device.startswith('/dev/'):
            self.ptjsonlib.end_error(
                f"Invalid device path: {self.args.device}. Must start with /dev/",
                self.args.json
            )
            sys.exit(99)
        
        # Check device exists
        if not self.args.dry_run and not os.path.exists(self.args.device):
            self.ptjsonlib.end_error(
                f"Device not found: {self.args.device}",
                self.args.json
            )
            sys.exit(99)
        
        self.device = self.args.device
        self.case_id = self.args.case_id.strip()
        self.dry_run = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Imaging state
        self.tool_selected = None
        self.media_status = None
        self.source_size_bytes = None
        
        # Add forensic metadata as properties
        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "devicePath": self.device,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "toolSelected": None,
            "mediaStatus": None,
            "imagePath": None,
            "imageFormat": None,
            "sourceSizeBytes": None,
            "sourceHash": None,
            "durationSeconds": None,
            "averageSpeedMBps": None,
            "errorSectors": 0,
            "imagingLog": None,
            "dryRun": self.dry_run
        })
        
        ptprint(f"Initialized: device={self.device}, case={self.case_id}", 
               "INFO", condition=not self.args.json)
    
    def _run_command(self, cmd: List[str], timeout: Optional[int] = None, 
                    realtime: bool = False) -> Dict[str, Any]:
        """
        Execute command with timeout and error handling
        
        Args:
            cmd: Command and arguments as list
            timeout: Timeout in seconds
            realtime: Show real-time output for long operations
            
        Returns:
            Dict with success, stdout, stderr, returncode, duration
        """
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
        
        try:
            start_time = time.time()
            
            if realtime:
                # For imaging - show progress in real-time
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                output_lines = []
                for line in process.stdout:
                    if not self.args.json and not self.args.quiet:
                        print(line, end='')
                    output_lines.append(line)
                
                process.wait()
                duration = time.time() - start_time
                
                result.update({
                    "success": process.returncode == 0,
                    "stdout": "".join(output_lines),
                    "returncode": process.returncode,
                    "duration": duration
                })
            else:
                # For quick commands
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False
                )
                
                duration = time.time() - start_time
                
                result.update({
                    "success": proc.returncode == 0,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                    "returncode": proc.returncode,
                    "duration": duration
                })
                
        except subprocess.TimeoutExpired:
            result["stderr"] = f"Command timeout after {timeout}s"
        except Exception as e:
            result["stderr"] = str(e)
        
        return result
    
    def load_readability_results(self) -> bool:
        """
        Load readability test results from Step 3
        Determines which imaging tool to use
        
        Returns:
            bool: True if results loaded successfully
        """
        ptprint("\n[STEP 1/5] Loading Readability Test Results", 
               "TITLE", condition=not self.args.json)
        
        # Look for JSON report from Step 3
        readability_patterns = [
            self.output_dir / f"{self.case_id}_readability_*.json",
            self.output_dir / f"{self.case_id}_readability.json"
        ]
        
        readability_file = None
        for pattern in readability_patterns:
            files = list(self.output_dir.glob(pattern.name))
            if files:
                readability_file = files[0]
                break
        
        if not readability_file or not readability_file.exists():
            error_msg = f"Readability test results not found in {self.output_dir}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            ptprint("Please run Step 3 (Media Readability Test) first!", 
                   "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "prerequisiteCheck",
                properties={
                    "checkName": "Readability Results",
                    "success": False,
                    "error": "Missing Step 3 results"
                }
            ))
            return False
        
        try:
            with open(readability_file, 'r') as f:
                data = json.load(f)
            
            # Extract media status from Step 3 results
            if "result" in data and "properties" in data["result"]:
                self.media_status = data["result"]["properties"].get("mediaStatus", "UNKNOWN")
            else:
                self.media_status = data.get("status", "UNKNOWN")
            
            ptprint(f"Media status from Step 3: {self.media_status}", 
                   "INFO", condition=not self.args.json)
            
            # Tool selection based on status
            if self.media_status == "READABLE":
                self.tool_selected = "dc3dd"
                ptprint("✓ Selected tool: dc3dd (media fully readable)", 
                       "OK", condition=not self.args.json)
            elif self.media_status == "PARTIAL":
                self.tool_selected = "ddrescue"
                ptprint("⚠ Selected tool: ddrescue (media has bad sectors)", 
                       "WARNING", condition=not self.args.json)
            else:  # UNREADABLE
                error_msg = "Media is UNREADABLE - imaging not possible without physical repair"
                ptprint(error_msg, "ERROR", condition=not self.args.json)
                ptprint("Media should go through Physical Repair (Step 4) first", 
                       "ERROR", condition=not self.args.json)
                
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "prerequisiteCheck",
                    properties={
                        "checkName": "Media Status",
                        "success": False,
                        "mediaStatus": self.media_status,
                        "error": "Media unreadable"
                    }
                ))
                return False
            
            # Update properties
            self.ptjsonlib.add_properties({
                "toolSelected": self.tool_selected,
                "mediaStatus": self.media_status
            })
            
            # Add successful check node
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "prerequisiteCheck",
                properties={
                    "checkName": "Readability Results",
                    "success": True,
                    "mediaStatus": self.media_status,
                    "toolSelected": self.tool_selected,
                    "resultsFile": str(readability_file)
                }
            ))
            
            return True
            
        except Exception as e:
            error_msg = f"Error reading readability results: {str(e)}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "prerequisiteCheck",
                properties={
                    "checkName": "Readability Results",
                    "success": False,
                    "error": str(e)
                }
            ))
            return False
    
    def verify_write_blocker(self) -> bool:
        """
        Verify write-blocker is actually protecting the device
        
        Returns:
            bool: True if write-blocker verified
        """
        ptprint("\n[STEP 2/5] Verifying Write-Blocker Protection", 
               "TITLE", condition=not self.args.json)
        
        if self.dry_run:
            ptprint("[DRY-RUN] Skipping write-blocker verification", 
                   "INFO", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "writeBlockerVerification",
                properties={
                    "success": True,
                    "dryRun": True,
                    "message": "Skipped in dry-run mode"
                }
            ))
            return True
        
        # Attempt write test - MUST fail if write-blocker working
        result = self._run_command([
            "dd",
            "if=/dev/zero",
            f"of={self.device}",
            "bs=512",
            "count=1"
        ], timeout=10)
        
        # Check if write was blocked
        if result["success"]:
            # Write succeeded - CRITICAL FAILURE!
            error_msg = "CRITICAL: Write-blocker NOT working! Write operation succeeded!"
            ptprint(error_msg, "ERROR", condition=not self.args.json, colortext=True)
            ptprint("ABORT: Cannot proceed without write-blocker protection", 
                   "ERROR", condition=not self.args.json, colortext=True)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "writeBlockerVerification",
                properties={
                    "success": False,
                    "criticalFailure": True,
                    "error": "Write-blocker not protecting device",
                    "writeTestResult": "succeeded (DANGEROUS)"
                }
            ))
            return False
        else:
            # Write failed - check if it's read-only error
            error_msg = result.get("stderr", "").lower()
            
            if "read-only" in error_msg or "permission denied" in error_msg:
                ptprint("✓ Write-blocker verified: Device is read-only", 
                       "OK", condition=not self.args.json)
                
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "writeBlockerVerification",
                    properties={
                        "success": True,
                        "writeTestResult": "blocked (SAFE)",
                        "errorMessage": result.get("stderr", "")
                    }
                ))
                return True
            else:
                # Different error - unclear if write-blocker working
                ptprint(f"⚠ Unexpected error during write test: {error_msg}", 
                       "WARNING", condition=not self.args.json)
                
                if not self.args.json:
                    confirm = input("Continue anyway? (yes/no): ").strip().lower()
                    if confirm not in ["yes", "y"]:
                        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                            "writeBlockerVerification",
                            properties={
                                "success": False,
                                "userAborted": True,
                                "writeTestError": error_msg
                            }
                        ))
                        return False
                
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "writeBlockerVerification",
                    properties={
                        "success": True,
                        "warning": "Verification unclear, user confirmed",
                        "writeTestError": error_msg
                    }
                ))
                return True
    
    def check_storage_space(self) -> bool:
        """
        Check if target storage has sufficient space
        Requires 110% of source device size
        
        Returns:
            bool: True if sufficient space available
        """
        ptprint("\n[STEP 3/5] Checking Target Storage Space", 
               "TITLE", condition=not self.args.json)
        
        # Get source device size
        result = self._run_command(["blockdev", "--getsize64", self.device], timeout=10)
        
        if not result["success"]:
            ptprint("⚠ Could not determine source size, skipping space check", 
                   "WARNING", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "storageSpaceCheck",
                properties={
                    "success": True,
                    "skipped": True,
                    "reason": "Could not determine source size"
                }
            ))
            return True
        
        self.source_size_bytes = int(result["stdout"])
        source_size_gb = self.source_size_bytes / (1024**3)
        
        # Required space: 110% of source
        required_bytes = int(self.source_size_bytes * SPACE_MARGIN)
        required_gb = required_bytes / (1024**3)
        
        # Available space on target
        stat = shutil.disk_usage(self.output_dir)
        available_gb = stat.free / (1024**3)
        
        ptprint(f"Source device size: {source_size_gb:.2f} GB", 
               "INFO", condition=not self.args.json)
        ptprint(f"Required space (110%): {required_gb:.2f} GB", 
               "INFO", condition=not self.args.json)
        ptprint(f"Available space: {available_gb:.2f} GB", 
               "INFO", condition=not self.args.json)
        
        # Update properties
        self.ptjsonlib.add_properties({"sourceSizeBytes": self.source_size_bytes})
        
        if stat.free < required_bytes:
            error_msg = f"Insufficient space! Need {required_gb:.2f} GB, have {available_gb:.2f} GB"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "storageSpaceCheck",
                properties={
                    "success": False,
                    "sourceSizeGB": round(source_size_gb, 2),
                    "requiredSpaceGB": round(required_gb, 2),
                    "availableSpaceGB": round(available_gb, 2),
                    "shortfallGB": round(required_gb - available_gb, 2)
                }
            ))
            return False
        else:
            margin_gb = available_gb - required_gb
            ptprint(f"✓ Sufficient space available ({margin_gb:.2f} GB margin)", 
                   "OK", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "storageSpaceCheck",
                properties={
                    "success": True,
                    "sourceSizeGB": round(source_size_gb, 2),
                    "requiredSpaceGB": round(required_gb, 2),
                    "availableSpaceGB": round(available_gb, 2),
                    "marginGB": round(margin_gb, 2)
                }
            ))
            return True
    
    def run_imaging_dc3dd(self) -> bool:
        """
        Create forensic image using dc3dd
        For READABLE media with integrated SHA-256 hashing
        
        Returns:
            bool: True if imaging successful
        """
        ptprint("\n[STEP 4/5] Creating Forensic Image with DC3DD", 
               "TITLE", condition=not self.args.json)
        
        image_file = self.output_dir / f"{self.case_id}.dd"
        hash_file = self.output_dir / f"{self.case_id}.dd.sha256"
        log_file = self.output_dir / f"{self.case_id}_imaging.log"
        
        ptprint(f"Source: {self.device}", "INFO", condition=not self.args.json)
        ptprint(f"Target: {image_file}", "INFO", condition=not self.args.json)
        
        # dc3dd command
        cmd = [
            "dc3dd",
            f"if={self.device}",
            f"of={image_file}",
            "hash=sha256",
            f"log={log_file}",
            f"bs={BLOCK_SIZE_MB}M",
            "progress=on"
        ]
        
        ptprint(f"Command: {' '.join(cmd)}", "INFO", condition=not self.args.json)
        ptprint("", "TEXT", condition=not self.args.json)
        
        start_time = time.time()
        result = self._run_command(cmd, timeout=None, realtime=True)
        duration = time.time() - start_time
        
        if result["success"]:
            ptprint(f"\n✓ Imaging completed in {duration:.0f} seconds ({duration/60:.1f} min)", 
                   "OK", condition=not self.args.json)
            
            # Extract hash from log
            source_hash = None
            if log_file.exists():
                with open(log_file, 'r') as f:
                    for line in f:
                        if 'sha256' in line.lower() and ':' in line:
                            parts = line.split(':')
                            if len(parts) >= 2:
                                source_hash = parts[-1].strip()
                                break
            
            if source_hash:
                ptprint(f"Source SHA-256: {source_hash}", "OK", condition=not self.args.json)
                
                # Save hash to file
                with open(hash_file, 'w') as hf:
                    hf.write(f"{source_hash}  {image_file.name}\n")
            else:
                ptprint("⚠ Could not extract hash from log", "WARNING", condition=not self.args.json)
            
            # Calculate speed
            if image_file.exists():
                file_size_mb = image_file.stat().st_size / (1024**2)
                avg_speed_mbps = file_size_mb / duration if duration > 0 else 0
            else:
                file_size_mb = 0
                avg_speed_mbps = 0
            
            # Update properties
            self.ptjsonlib.add_properties({
                "imagePath": str(image_file),
                "imageFormat": "raw (.dd)",
                "sourceHash": source_hash,
                "durationSeconds": round(duration, 2),
                "averageSpeedMBps": round(avg_speed_mbps, 2),
                "imagingLog": str(log_file)
            })
            
            # Add imaging node
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "imagingProcess",
                properties={
                    "tool": "dc3dd",
                    "success": True,
                    "imagePath": str(image_file),
                    "imageFormat": "raw",
                    "sourceSizeBytes": self.source_size_bytes,
                    "sourceHash": source_hash,
                    "durationSeconds": round(duration, 2),
                    "averageSpeedMBps": round(avg_speed_mbps, 2),
                    "command": " ".join(cmd),
                    "logFile": str(log_file)
                }
            ))
            
            return True
        else:
            error_msg = f"Imaging failed: {result.get('stderr', 'Unknown error')}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "imagingProcess",
                properties={
                    "tool": "dc3dd",
                    "success": False,
                    "error": result.get("stderr", "Unknown error"),
                    "returnCode": result["returncode"]
                }
            ))
            return False
    
    def run_imaging_ddrescue(self) -> bool:
        """
        Create forensic image using ddrescue
        For PARTIAL media with damaged sectors
        
        Returns:
            bool: True if imaging successful
        """
        ptprint("\n[STEP 4/5] Creating Forensic Image with DDRESCUE", 
               "TITLE", condition=not self.args.json)
        ptprint("⚠ Damaged media recovery mode", "WARNING", condition=not self.args.json)
        
        image_file = self.output_dir / f"{self.case_id}.dd"
        mapfile = self.output_dir / f"{self.case_id}.mapfile"
        hash_file = self.output_dir / f"{self.case_id}.dd.sha256"
        log_file = self.output_dir / f"{self.case_id}_imaging.log"
        
        ptprint(f"Source: {self.device}", "INFO", condition=not self.args.json)
        ptprint(f"Target: {image_file}", "INFO", condition=not self.args.json)
        ptprint(f"Mapfile: {mapfile}", "INFO", condition=not self.args.json)
        
        # ddrescue command
        cmd = [
            "ddrescue",
            "-f",  # Force overwrite
            "-v",  # Verbose
            self.device,
            str(image_file),
            str(mapfile)
        ]
        
        ptprint(f"Command: {' '.join(cmd)}", "INFO", condition=not self.args.json)
        ptprint("", "TEXT", condition=not self.args.json)
        
        start_time = time.time()
        result = self._run_command(cmd, timeout=None, realtime=True)
        duration = time.time() - start_time
        
        if result["success"] or result["returncode"] == 0:
            ptprint(f"\n✓ Imaging completed in {duration:.0f} seconds ({duration/60:.1f} min)", 
                   "OK", condition=not self.args.json)
            
            # Parse mapfile for bad sectors
            bad_sectors = 0
            if mapfile.exists():
                with open(mapfile, 'r') as f:
                    mapfile_content = f.read()
                    bad_sectors = mapfile_content.count('-')
                
                if bad_sectors > 0:
                    ptprint(f"⚠ {bad_sectors} bad sectors detected", 
                           "WARNING", condition=not self.args.json)
                else:
                    ptprint("✓ All sectors read successfully", 
                           "OK", condition=not self.args.json)
            
            # Calculate hash (ddrescue doesn't have built-in hashing)
            ptprint("\nCalculating SHA-256 hash of source...", 
                   "INFO", condition=not self.args.json)
            
            hash_cmd = f"dd if={self.device} bs=1M status=none | sha256sum"
            try:
                hash_result = subprocess.run(
                    hash_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_HASH
                )
                
                if hash_result.returncode == 0:
                    source_hash = hash_result.stdout.strip().split()[0]
                    ptprint(f"Source SHA-256: {source_hash}", 
                           "OK", condition=not self.args.json)
                    
                    # Save hash
                    with open(hash_file, 'w') as hf:
                        hf.write(f"{source_hash}  {image_file.name}\n")
                else:
                    source_hash = None
                    ptprint("⚠ Could not calculate source hash", 
                           "WARNING", condition=not self.args.json)
            except Exception as e:
                source_hash = None
                ptprint(f"⚠ Hash calculation failed: {str(e)}", 
                       "WARNING", condition=not self.args.json)
            
            # Calculate speed
            if image_file.exists():
                file_size_mb = image_file.stat().st_size / (1024**2)
                avg_speed_mbps = file_size_mb / duration if duration > 0 else 0
            else:
                file_size_mb = 0
                avg_speed_mbps = 0
            
            # Write log
            with open(log_file, 'w') as lf:
                lf.write("=== DDRESCUE IMAGING LOG ===\n")
                lf.write(f"Case ID: {self.case_id}\n")
                lf.write(f"Source: {self.device}\n")
                lf.write(f"Target: {image_file}\n")
                lf.write(f"Start: {datetime.fromtimestamp(start_time).isoformat()}\n")
                lf.write(f"Duration: {duration:.2f} seconds\n")
                lf.write(f"Bad sectors: {bad_sectors}\n")
                lf.write(f"Average speed: {avg_speed_mbps:.2f} MB/s\n")
                lf.write(f"Source hash: {source_hash or 'N/A'}\n")
                lf.write("\n=== DDRESCUE OUTPUT ===\n")
                lf.write(result["stdout"])
            
            # Update properties
            self.ptjsonlib.add_properties({
                "imagePath": str(image_file),
                "imageFormat": "raw (.dd)",
                "sourceHash": source_hash,
                "durationSeconds": round(duration, 2),
                "averageSpeedMBps": round(avg_speed_mbps, 2),
                "errorSectors": bad_sectors,
                "imagingLog": str(log_file)
            })
            
            # Add imaging node
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "imagingProcess",
                properties={
                    "tool": "ddrescue",
                    "success": True,
                    "imagePath": str(image_file),
                    "imageFormat": "raw",
                    "sourceSizeBytes": self.source_size_bytes,
                    "sourceHash": source_hash,
                    "durationSeconds": round(duration, 2),
                    "averageSpeedMBps": round(avg_speed_mbps, 2),
                    "badSectors": bad_sectors,
                    "mapfile": str(mapfile),
                    "command": " ".join(cmd),
                    "logFile": str(log_file)
                }
            ))
            
            return True
        else:
            error_msg = f"Imaging failed: {result.get('stderr', 'Unknown error')}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "imagingProcess",
                properties={
                    "tool": "ddrescue",
                    "success": False,
                    "error": result.get("stderr", "Unknown error"),
                    "returnCode": result["returncode"]
                }
            ))
            return False
    
    def run(self) -> None:
        """Main execution method"""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FORENSIC IMAGING PROCESS v{__version__}", 
               "TITLE", condition=not self.args.json)
        ptprint(f"Case ID: {self.case_id}", "INFO", condition=not self.args.json)
        ptprint(f"Device: {self.device}", "INFO", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        
        # Step 1: Load readability results
        if not self.load_readability_results():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 2: Verify write-blocker
        if not self.verify_write_blocker():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 3: Check storage space
        if not self.check_storage_space():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 4: Run imaging based on tool selection
        if self.tool_selected == "dc3dd":
            success = self.run_imaging_dc3dd()
        elif self.tool_selected == "ddrescue":
            success = self.run_imaging_ddrescue()
        else:
            ptprint(f"ERROR: Unknown tool: {self.tool_selected}", 
                   "ERROR", condition=not self.args.json)
            success = False
        
        # Summary
        if success:
            ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
            ptprint("IMAGING COMPLETED SUCCESSFULLY", "OK", condition=not self.args.json)
            ptprint("=" * 70, "TITLE", condition=not self.args.json)
            
            props = self.ptjsonlib.json_data["result"]["properties"]
            ptprint(f"Image file: {props['imagePath']}", "INFO", condition=not self.args.json)
            ptprint(f"Duration: {props['durationSeconds']:.0f}s ({props['durationSeconds']/60:.1f} min)", 
                   "INFO", condition=not self.args.json)
            ptprint(f"Average speed: {props['averageSpeedMBps']:.2f} MB/s", 
                   "INFO", condition=not self.args.json)
            if props['errorSectors'] > 0:
                ptprint(f"Bad sectors: {props['errorSectors']}", 
                       "WARNING", condition=not self.args.json)
            ptprint(f"Source hash: {props['sourceHash']}", "INFO", condition=not self.args.json)
            ptprint("=" * 70, "TITLE", condition=not self.args.json)
            ptprint("\nNext step: Step 6 (Hash Verification)", 
                   "INFO", condition=not self.args.json)
        else:
            ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
            ptprint("IMAGING FAILED", "ERROR", condition=not self.args.json)
            ptprint("=" * 70, "TITLE", condition=not self.args.json)
        
        self.ptjsonlib.set_status("finished")
    
    def save_report(self) -> Optional[str]:
        """Save JSON report"""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None
        else:
            json_file = self.output_dir / f"{self.case_id}_imaging.json"
            
            with open(json_file, 'w', encoding='utf-8') as f:
                f.write(self.ptjsonlib.get_result_json())
            
            ptprint(f"\n✓ JSON report saved: {json_file}", 
                   "OK", condition=not self.args.json)
            return str(json_file)


# ============================================================================
# MODULE-LEVEL WORKFLOW FUNCTIONS
# ============================================================================

def get_help():
    """Return help structure for ptprinthelper"""
    return [
        {"description": [
            "Forensic media imaging tool with intelligent tool selection",
            "Creates bit-for-bit forensic image with SHA-256 hash calculation"
        ]},
        {"usage": ["ptforensicimaging <device> <case-id> [options]"]},
        {"usage_example": [
            "ptforensicimaging /dev/sdb PHOTO-2025-001",
            "ptforensicimaging /dev/sdc CASE-042 --json",
            "ptforensicimaging /dev/sdd TEST-001 --dry-run"
        ]},
        {"options": [
            ["device", "", "Device path (e.g., /dev/sdb) - REQUIRED"],
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run", "", "Simulate execution without imaging"],
            ["--skip-wb-check", "", "Skip write-blocker confirmation (dangerous!)"],
            ["-j", "--json", "", "JSON output for platform integration"],
            ["-q", "--quiet", "", "Suppress progress output"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"]
        ]},
        {"tool_selection": [
            "READABLE media → dc3dd (fast, integrated hashing)",
            "PARTIAL media → ddrescue (damaged sector recovery)",
            "UNREADABLE media → ERROR (requires Step 4 repair)"
        ]},
        {"forensic_notes": [
            "ALWAYS use hardware write-blocker",
            "Requires Step 3 (Readability Test) results",
            "110% free space required on target",
            "Complies with NIST SP 800-86 and ISO/IEC 27037"
        ]}
    ]


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} - Forensic media imaging"
    )
    
    parser.add_argument("device", help="Device path (e.g., /dev/sdb)")
    parser.add_argument("case_id", help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-wb-check", action="store_true")
    parser.add_argument("-j", "--json", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
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
    SCRIPTNAME = "ptforensicimaging"
    
    try:
        args = parse_args()
        
        # Write-blocker confirmation
        if not args.dry_run and not args.json and not args.skip_wb_check:
            if not confirm_write_blocker():
                ptprint("\n✗ Imaging ABORTED - write-blocker required!", 
                       "ERROR", condition=True, colortext=True)
                return 99
        
        # Run imaging
        imager = PtForensicImaging(args)
        imager.run()
        imager.save_report()
        
        # Return exit code based on success
        props = imager.ptjsonlib.json_data["result"]["properties"]
        if props.get("imagePath"):
            return 0  # Success
        else:
            return 1  # Failed
        
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
