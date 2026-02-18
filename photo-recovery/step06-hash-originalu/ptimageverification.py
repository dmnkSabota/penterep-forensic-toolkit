#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno
    
    ptimageverification - Forensic image hash verification tool
    
    ptimageverification is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    ptimageverification is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with ptimageverification.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import hashlib
import subprocess
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/images"
HASH_BLOCK_SIZE = 4 * 1024 * 1024  # 4 MB chunks for hash calculation
PROGRESS_INTERVAL_GB = 1.0  # Report progress every 1 GB


# ============================================================================
# MAIN IMAGE VERIFICATION CLASS
# ============================================================================

class PtImageVerification:
    """
    Forensic image hash verification tool - ptlibs compliant
    
    Two-phase integrity verification:
    1. Phase 1 (Step 5): source_hash calculated during imaging
    2. Phase 2 (Step 6): image_hash calculated from image file
    
    Hash match proves bit-for-bit forensic integrity.
    Complies with NIST SP 800-86 and ISO/IEC 27037 standards.
    """
    
    def __init__(self, args):
        """
        Initialize image hash verification with ptlibs integration
        
        Args:
            args: Parsed command-line arguments
        """
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        
        self.case_id = self.args.case_id.strip()
        self.dry_run = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Image file details
        self.image_path = None
        self.image_format = None
        self.image_size_bytes = None
        
        # Hash values
        self.source_hash = None  # From Step 5 (imaging)
        self.image_hash = None   # Calculated from image file
        
        # Add forensic metadata as properties
        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "imagePath": None,
            "imageFormat": None,
            "imageSizeBytes": None,
            "sourceHash": None,
            "imageHash": None,
            "hashMatch": None,
            "calculationTimeSeconds": None,
            "verificationStatus": "UNKNOWN",
            "dryRun": self.dry_run
        })
        
        ptprint(f"Initialized: case={self.case_id}", 
               "INFO", condition=not self.args.json)
    
    def load_imaging_results(self) -> bool:
        """
        Load imaging results from Step 5
        Extracts source_hash that was calculated during imaging
        
        Returns:
            bool: True if source_hash loaded successfully
        """
        ptprint("\n[STEP 1/4] Loading Imaging Results from Step 5", 
               "TITLE", condition=not self.args.json)
        
        # Look for Step 5 imaging JSON
        imaging_patterns = [
            self.output_dir / f"{self.case_id}_imaging*.json",
            self.output_dir / f"{self.case_id}_imaging.json"
        ]
        
        imaging_file = None
        for pattern in imaging_patterns:
            files = list(self.output_dir.glob(pattern.name))
            if files:
                imaging_file = files[0]
                break
        
        if not imaging_file or not imaging_file.exists():
            error_msg = f"Imaging results not found in {self.output_dir}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            ptprint("Please run Step 5 (Forensic Imaging) first!", 
                   "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "prerequisiteCheck",
                properties={
                    "checkName": "Imaging Results",
                    "success": False,
                    "error": "Missing Step 5 results"
                }
            ))
            return False
        
        try:
            with open(imaging_file, 'r') as f:
                data = json.load(f)
            
            # Extract source_hash from Step 5 results
            if "result" in data and "properties" in data["result"]:
                self.source_hash = data["result"]["properties"].get("sourceHash")
            else:
                self.source_hash = data.get("source_hash")
            
            if not self.source_hash:
                error_msg = "No source hash found in imaging results"
                ptprint(error_msg, "ERROR", condition=not self.args.json)
                ptprint("Step 5 may not have completed successfully", 
                       "ERROR", condition=not self.args.json)
                
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "prerequisiteCheck",
                    properties={
                        "checkName": "Source Hash",
                        "success": False,
                        "error": "Source hash not found"
                    }
                ))
                return False
            
            # Validate hash format (64 hex characters)
            if len(self.source_hash) != 64 or not all(c in '0123456789abcdef' for c in self.source_hash.lower()):
                error_msg = f"Invalid hash format: {self.source_hash}"
                ptprint(error_msg, "ERROR", condition=not self.args.json)
                
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "prerequisiteCheck",
                    properties={
                        "checkName": "Source Hash Format",
                        "success": False,
                        "error": "Invalid hash format"
                    }
                ))
                return False
            
            # Update properties
            self.ptjsonlib.add_properties({"sourceHash": self.source_hash})
            
            ptprint(f"✓ Source hash loaded: {self.source_hash[:16]}...", 
                   "OK", condition=not self.args.json)
            
            # Add successful check node
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "prerequisiteCheck",
                properties={
                    "checkName": "Imaging Results",
                    "success": True,
                    "sourceHash": self.source_hash,
                    "resultsFile": str(imaging_file)
                }
            ))
            
            return True
            
        except Exception as e:
            error_msg = f"Error reading imaging results: {str(e)}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "prerequisiteCheck",
                properties={
                    "checkName": "Imaging Results",
                    "success": False,
                    "error": str(e)
                }
            ))
            return False
    
    def find_image_file(self) -> bool:
        """
        Find forensic image file created in Step 5
        Supports .dd, .raw, and .E01 formats
        
        Returns:
            bool: True if image file found
        """
        ptprint("\n[STEP 2/4] Locating Forensic Image File", 
               "TITLE", condition=not self.args.json)
        
        # Possible image formats
        possible_files = [
            self.output_dir / f"{self.case_id}.dd",
            self.output_dir / f"{self.case_id}.raw",
            self.output_dir / f"{self.case_id}.E01",
            self.output_dir / f"{self.case_id}.e01"
        ]
        
        for path in possible_files:
            if path.exists():
                self.image_path = path
                self.image_format = path.suffix.lower()
                self.image_size_bytes = path.stat().st_size
                
                size_gb = self.image_size_bytes / (1024**3)
                
                # Update properties
                self.ptjsonlib.add_properties({
                    "imagePath": str(path),
                    "imageFormat": self.image_format,
                    "imageSizeBytes": self.image_size_bytes
                })
                
                ptprint(f"✓ Found image: {path.name}", "OK", condition=not self.args.json)
                ptprint(f"  Format: {self.image_format}", "INFO", condition=not self.args.json)
                ptprint(f"  Size: {size_gb:.2f} GB ({self.image_size_bytes:,} bytes)", 
                       "INFO", condition=not self.args.json)
                
                # Add node
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "imageFileCheck",
                    properties={
                        "success": True,
                        "imagePath": str(path),
                        "imageFormat": self.image_format,
                        "imageSizeBytes": self.image_size_bytes,
                        "imageSizeGB": round(size_gb, 2)
                    }
                ))
                
                return True
        
        error_msg = f"No image file found for case {self.case_id}"
        ptprint(error_msg, "ERROR", condition=not self.args.json)
        ptprint("Expected files:", "INFO", condition=not self.args.json)
        for path in possible_files:
            ptprint(f"  - {path}", "INFO", condition=not self.args.json)
        ptprint("\nPlease run Step 5 (Forensic Imaging) first!", 
               "ERROR", condition=not self.args.json)
        
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "imageFileCheck",
            properties={
                "success": False,
                "error": "Image file not found"
            }
        ))
        
        return False
    
    def calculate_image_hash(self) -> bool:
        """
        Calculate SHA-256 hash of image file
        Uses different methods for RAW vs E01 formats
        
        Returns:
            bool: True if hash calculated successfully
        """
        ptprint("\n[STEP 3/4] Calculating Image File Hash", 
               "TITLE", condition=not self.args.json)
        
        if self.image_format in ['.dd', '.raw']:
            return self._calculate_hash_raw()
        elif self.image_format in ['.e01']:
            return self._calculate_hash_e01()
        else:
            error_msg = f"Unsupported image format: {self.image_format}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashCalculation",
                properties={
                    "success": False,
                    "error": "Unsupported format",
                    "imageFormat": self.image_format
                }
            ))
            return False
    
    def _calculate_hash_raw(self) -> bool:
        """
        Calculate SHA-256 for RAW images (.dd, .raw)
        Uses Python hashlib for reliability
        
        Returns:
            bool: True if successful
        """
        ptprint(f"Image: {self.image_path.name}", "INFO", condition=not self.args.json)
        ptprint("Algorithm: SHA-256", "INFO", condition=not self.args.json)
        ptprint("Method: Python hashlib (4MB chunks)", "INFO", condition=not self.args.json)
        
        if self.dry_run:
            ptprint("[DRY-RUN] Simulating hash calculation", "INFO", condition=not self.args.json)
            self.image_hash = self.source_hash  # Simulate match
            
            self.ptjsonlib.add_properties({"imageHash": self.image_hash})
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashCalculation",
                properties={
                    "success": True,
                    "dryRun": True,
                    "simulatedHash": self.image_hash
                }
            ))
            return True
        
        # Estimate time
        size_gb = self.image_size_bytes / (1024**3)
        estimated_minutes = (size_gb * 1024) / (200 * 60)  # Assume 200 MB/s
        
        ptprint(f"\nEstimated time: ~{estimated_minutes:.1f} minutes", 
               "INFO", condition=not self.args.json)
        ptprint("Starting hash calculation...", "INFO", condition=not self.args.json)
        ptprint("", "TEXT", condition=not self.args.json)
        
        # Hash calculation
        sha256_hash = hashlib.sha256()
        total_read = 0
        last_progress_gb = 0
        
        start_time = time.time()
        
        try:
            with open(self.image_path, 'rb') as f:
                while True:
                    chunk = f.read(HASH_BLOCK_SIZE)
                    if not chunk:
                        break
                    
                    sha256_hash.update(chunk)
                    total_read += len(chunk)
                    
                    # Progress reporting every 1 GB
                    current_gb = total_read / (1024**3)
                    if current_gb - last_progress_gb >= PROGRESS_INTERVAL_GB:
                        elapsed = time.time() - start_time
                        speed_mbps = (total_read / (1024**2)) / elapsed if elapsed > 0 else 0
                        
                        ptprint(f"Progress: {current_gb:.1f} GB processed ({speed_mbps:.1f} MB/s)", 
                               "INFO", condition=not self.args.json)
                        last_progress_gb = current_gb
            
            duration = time.time() - start_time
            self.image_hash = sha256_hash.hexdigest()
            
            # Update properties
            self.ptjsonlib.add_properties({
                "imageHash": self.image_hash,
                "calculationTimeSeconds": round(duration, 2)
            })
            
            ptprint(f"\n✓ Hash calculation completed in {duration:.0f}s ({duration/60:.1f} min)", 
                   "OK", condition=not self.args.json)
            ptprint(f"Image SHA-256: {self.image_hash}", "OK", condition=not self.args.json)
            
            # Add node
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashCalculation",
                properties={
                    "success": True,
                    "algorithm": "SHA-256",
                    "method": "Python hashlib",
                    "imageHash": self.image_hash,
                    "durationSeconds": round(duration, 2),
                    "averageSpeedMBps": round((self.image_size_bytes / (1024**2)) / duration, 2) if duration > 0 else 0
                }
            ))
            
            return True
            
        except Exception as e:
            error_msg = f"Hash calculation failed: {str(e)}"
            ptprint(f"\n{error_msg}", "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashCalculation",
                properties={
                    "success": False,
                    "error": str(e)
                }
            ))
            return False
    
    def _calculate_hash_e01(self) -> bool:
        """
        Calculate hash for E01 images using ewfverify
        E01 has integrated CRC and hash verification
        
        Returns:
            bool: True if successful
        """
        ptprint(f"Image: {self.image_path.name}", "INFO", condition=not self.args.json)
        ptprint("Algorithm: SHA-256", "INFO", condition=not self.args.json)
        ptprint("Method: ewfverify (E01 format verification)", "INFO", condition=not self.args.json)
        
        # Check if ewfverify available
        try:
            result = subprocess.run(["which", "ewfverify"], capture_output=True, timeout=5)
            if result.returncode != 0:
                error_msg = "ewfverify not found. Install: sudo apt install libewf-tools"
                ptprint(error_msg, "ERROR", condition=not self.args.json)
                
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "hashCalculation",
                    properties={
                        "success": False,
                        "error": "ewfverify not available"
                    }
                ))
                return False
        except Exception as e:
            ptprint(f"Error checking ewfverify: {str(e)}", "ERROR", condition=not self.args.json)
            return False
        
        ptprint("\nStarting E01 verification...", "INFO", condition=not self.args.json)
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                ["ewfverify", "-d", "sha256", str(self.image_path)],
                capture_output=True,
                text=True,
                timeout=7200  # 2 hours max
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                # Parse hash from ewfverify output
                for line in result.stdout.split('\n'):
                    if 'SHA256' in line or 'sha256' in line:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            self.image_hash = parts[-1].strip()
                            break
                
                if self.image_hash:
                    # Update properties
                    self.ptjsonlib.add_properties({
                        "imageHash": self.image_hash,
                        "calculationTimeSeconds": round(duration, 2)
                    })
                    
                    ptprint(f"\n✓ E01 verification completed in {duration:.0f}s", 
                           "OK", condition=not self.args.json)
                    ptprint(f"Image SHA-256: {self.image_hash}", "OK", condition=not self.args.json)
                    
                    # Add node
                    self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                        "hashCalculation",
                        properties={
                            "success": True,
                            "algorithm": "SHA-256",
                            "method": "ewfverify",
                            "imageHash": self.image_hash,
                            "durationSeconds": round(duration, 2)
                        }
                    ))
                    
                    return True
                else:
                    error_msg = "Could not parse hash from ewfverify output"
                    ptprint(error_msg, "WARNING", condition=not self.args.json)
                    
                    self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                        "hashCalculation",
                        properties={
                            "success": False,
                            "error": "Hash parsing failed"
                        }
                    ))
                    return False
            else:
                error_msg = f"E01 verification failed: {result.stderr}"
                ptprint(error_msg, "ERROR", condition=not self.args.json)
                
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "hashCalculation",
                    properties={
                        "success": False,
                        "error": result.stderr,
                        "returnCode": result.returncode
                    }
                ))
                return False
                
        except subprocess.TimeoutExpired:
            error_msg = "Hash calculation timeout (exceeded 2 hours)"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashCalculation",
                properties={
                    "success": False,
                    "error": "Timeout"
                }
            ))
            return False
        except Exception as e:
            error_msg = f"Hash calculation error: {str(e)}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashCalculation",
                properties={
                    "success": False,
                    "error": str(e)
                }
            ))
            return False
    
    def verify_hashes(self) -> bool:
        """
        Compare source_hash (from Step 5) with image_hash (just calculated)
        Exact match proves bit-for-bit forensic integrity
        
        Returns:
            bool: True if hashes match
        """
        ptprint("\n[STEP 4/4] Verifying Hash Match", 
               "TITLE", condition=not self.args.json)
        
        if not self.source_hash or not self.image_hash:
            error_msg = "Missing hash values for comparison"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashVerification",
                properties={
                    "success": False,
                    "error": "Missing hash values"
                }
            ))
            return False
        
        ptprint(f"Source hash (from Step 5): {self.source_hash}", 
               "INFO", condition=not self.args.json)
        ptprint(f"Image hash  (from file):   {self.image_hash}", 
               "INFO", condition=not self.args.json)
        ptprint("", "TEXT", condition=not self.args.json)
        
        hash_match = (self.source_hash == self.image_hash)
        
        # Update properties
        self.ptjsonlib.add_properties({
            "hashMatch": hash_match,
            "verificationStatus": "VERIFIED" if hash_match else "MISMATCH"
        })
        
        if hash_match:
            ptprint("✓ HASH MATCH: Image file is bit-for-bit identical to source", 
                   "OK", condition=not self.args.json, colortext=True)
            ptprint("✓ Forensic integrity mathematically proven", 
                   "OK", condition=not self.args.json)
            ptprint("✓ Image is admissible as evidence", 
                   "OK", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashVerification",
                properties={
                    "success": True,
                    "hashMatch": True,
                    "verificationStatus": "VERIFIED",
                    "sourceHash": self.source_hash,
                    "imageHash": self.image_hash
                }
            ))
            
            return True
        else:
            ptprint("✗ HASH MISMATCH: Image does NOT match source!", 
                   "ERROR", condition=not self.args.json, colortext=True)
            ptprint("✗ This is a CRITICAL error - imaging must be repeated", 
                   "ERROR", condition=not self.args.json, colortext=True)
            ptprint("", "TEXT", condition=not self.args.json)
            ptprint("Possible causes:", "INFO", condition=not self.args.json)
            ptprint("  1. I/O error during imaging (check Step 5 log)", 
                   "INFO", condition=not self.args.json)
            ptprint("  2. Image file corrupted on disk (filesystem issue)", 
                   "INFO", condition=not self.args.json)
            ptprint("  3. Image file modified after creation (security breach)", 
                   "INFO", condition=not self.args.json)
            ptprint("  4. Source media degraded during imaging", 
                   "INFO", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "hashVerification",
                properties={
                    "success": False,
                    "hashMatch": False,
                    "verificationStatus": "MISMATCH",
                    "sourceHash": self.source_hash,
                    "imageHash": self.image_hash,
                    "criticalError": True
                }
            ))
            
            return False
    
    def run(self) -> None:
        """Main execution method"""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FORENSIC IMAGE HASH VERIFICATION v{__version__}", 
               "TITLE", condition=not self.args.json)
        ptprint(f"Case ID: {self.case_id}", "INFO", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        
        # Step 1: Load imaging results
        if not self.load_imaging_results():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 2: Find image file
        if not self.find_image_file():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 3: Calculate image hash
        if not self.calculate_image_hash():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 4: Verify hash match
        hash_match = self.verify_hashes()
        
        # Summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        
        if hash_match:
            ptprint("VERIFICATION SUCCESSFUL", "OK", condition=not self.args.json)
            ptprint("=" * 70, "TITLE", condition=not self.args.json)
            ptprint("✓ Original media can be safely disconnected", 
                   "OK", condition=not self.args.json)
            ptprint("✓ All future analysis on verified image", 
                   "OK", condition=not self.args.json)
            ptprint("✓ Ready to proceed to Step 7 (Media Specifications)", 
                   "OK", condition=not self.args.json)
        else:
            ptprint("VERIFICATION FAILED - HASH MISMATCH", "ERROR", condition=not self.args.json)
            ptprint("=" * 70, "TITLE", condition=not self.args.json)
            ptprint("✗ Image is NOT identical to source", 
                   "ERROR", condition=not self.args.json)
            ptprint("✗ Imaging process must be repeated (Step 5)", 
                   "ERROR", condition=not self.args.json)
            ptprint("✗ Do NOT proceed with unverified image", 
                   "ERROR", condition=not self.args.json)
        
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        
        self.ptjsonlib.set_status("finished")
    
    def save_report(self) -> Optional[str]:
        """Save JSON report"""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None
        else:
            json_file = self.output_dir / f"{self.case_id}_verification.json"
            
            with open(json_file, 'w', encoding='utf-8') as f:
                f.write(self.ptjsonlib.get_result_json())
            
            ptprint(f"\n✓ Verification report saved: {json_file}", 
                   "OK", condition=not self.args.json)
            
            # Also save image hash to .sha256 file for compatibility
            if self.image_hash:
                hash_file = self.output_dir / f"{self.case_id}_image.sha256"
                with open(hash_file, 'w') as hf:
                    hf.write(f"{self.image_hash}  {self.image_path.name}\n")
                ptprint(f"✓ Hash file saved: {hash_file}", 
                       "OK", condition=not self.args.json)
            
            return str(json_file)


# ============================================================================
# MODULE-LEVEL WORKFLOW FUNCTIONS
# ============================================================================

def get_help():
    """Return help structure for ptprinthelper"""
    return [
        {"description": [
            "Forensic image hash verification tool - ptlibs compliant",
            "Compares source_hash (from imaging) with image_hash (from file)"
        ]},
        {"usage": ["ptimageverification <case-id> [options]"]},
        {"usage_example": [
            "ptimageverification PHOTO-2025-001",
            "ptimageverification CASE-042 --json",
            "ptimageverification TEST-001 --dry-run"
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run", "", "Simulate verification without calculations"],
            ["-j", "--json", "", "JSON output for platform integration"],
            ["-q", "--quiet", "", "Suppress progress output"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"]
        ]},
        {"verification_process": [
            "Step 1: Load source_hash from Step 5 results",
            "Step 2: Find forensic image file (.dd/.raw/.E01)",
            "Step 3: Calculate SHA-256 hash of image file",
            "Step 4: Compare hashes - MATCH = verified, MISMATCH = error"
        ]},
        {"forensic_notes": [
            "Requires Step 5 (Imaging) results",
            "Hash match proves bit-for-bit integrity",
            "Supports RAW (.dd, .raw) and E01 formats",
            "Complies with NIST SP 800-86 and ISO/IEC 27037"
        ]}
    ]


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} - Forensic image hash verification"
    )
    
    parser.add_argument("case_id", help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
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
    SCRIPTNAME = "ptimageverification"
    
    try:
        args = parse_args()
        
        # Run verification
        verifier = PtImageVerification(args)
        verifier.run()
        verifier.save_report()
        
        # Return exit code based on verification status
        props = verifier.ptjsonlib.json_data["result"]["properties"]
        
        if props.get("verificationStatus") == "VERIFIED":
            return 0  # Success - hashes match
        elif props.get("verificationStatus") == "MISMATCH":
            return 1  # Failed - hash mismatch (critical!)
        else:
            return 99  # Error - verification incomplete
        
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
