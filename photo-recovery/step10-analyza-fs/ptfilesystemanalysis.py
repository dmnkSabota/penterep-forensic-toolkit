#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno
    
    ptfilesystemanalysis - Forensic filesystem analysis tool
    
    ptfilesystemanalysis is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    ptfilesystemanalysis is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with ptfilesystemanalysis.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import subprocess
import json
import re
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
FLS_TIMEOUT = 600  # 10 minutes for large media

# Supported image file extensions
IMAGE_EXTENSIONS = {
    'jpeg': ['.jpg', '.jpeg'],
    'png': ['.png'],
    'gif': ['.gif'],
    'bmp': ['.bmp'],
    'tiff': ['.tiff', '.tif'],
    'raw': ['.raw', '.cr2', '.nef', '.arw', '.dng', '.orf', '.raf'],
    'heic': ['.heic', '.heif'],
    'webp': ['.webp']
}


# ============================================================================
# MAIN FILESYSTEM ANALYSIS CLASS
# ============================================================================

class PtFilesystemAnalysis:
    """
    Forensic filesystem analysis tool - ptlibs compliant
    
    Five-phase analysis process:
    1. Partition analysis (mmls) - Detect partition table and partitions
    2. Filesystem analysis (fsstat) - Identify FS type and metadata
    3. Directory structure test (fls) - Check if directories readable
    4. Image file identification - Count and categorize photo files
    5. Recovery strategy determination - Recommend optimal method
    
    Complies with ISO/IEC 27037 and NIST SP 800-86 standards.
    """
    
    def __init__(self, args):
        """
        Initialize filesystem analysis with ptlibs integration
        
        Args:
            args: Parsed command-line arguments
        """
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        
        self.case_id = self.args.case_id.strip()
        self.dry_run = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Image path (loaded from Step 6)
        self.image_path = None
        
        # Analysis state
        self.partitions = []
        self.filesystem_recognized = False
        self.directory_readable = False
        
        # Add forensic metadata as properties
        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "imagePath": None,
            "partitionTableType": None,
            "partitionsFound": 0,
            "filesystemRecognized": False,
            "directoryStructureReadable": False,
            "imageFilesFound": {
                "total": 0,
                "active": 0,
                "deleted": 0,
                "byType": {}
            },
            "recommendedMethod": None,
            "recommendedTool": None,
            "estimatedTimeMinutes": None,
            "dryRun": self.dry_run
        })
        
        ptprint(f"Initialized: case={self.case_id}", 
               "INFO", condition=not self.args.json)
    
    def _run_command(self, cmd: List[str], timeout: Optional[int] = 300) -> Dict[str, Any]:
        """
        Execute command with timeout and error handling
        
        Args:
            cmd: Command and arguments as list
            timeout: Timeout in seconds
            
        Returns:
            Dict with success, stdout, stderr, returncode
        """
        result = {
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1
        }
        
        if self.dry_run:
            ptprint(f"[DRY-RUN] Would execute: {' '.join(cmd)}", 
                   "INFO", condition=not self.args.json)
            result["success"] = True
            result["stdout"] = "[DRY-RUN] Simulated success"
            return result
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            
            result.update({
                "success": proc.returncode == 0,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "returncode": proc.returncode
            })
                
        except subprocess.TimeoutExpired:
            result["stderr"] = f"Command timeout after {timeout}s"
        except Exception as e:
            result["stderr"] = str(e)
        
        return result
    
    def load_image_path(self) -> bool:
        """
        Load forensic image path from Step 6 verification results
        
        Returns:
            bool: True if image path loaded successfully
        """
        ptprint("\n[STEP 1/6] Loading Image Path from Step 6", 
               "TITLE", condition=not self.args.json)
        
        # Try multiple sources for image path
        search_patterns = [
            (self.output_dir / f"{self.case_id}_verification*.json", "Step 6"),
            (self.output_dir / f"{self.case_id}_imaging*.json", "Step 5"),
            (self.output_dir / f"{self.case_id}.dd", "Default location")
        ]
        
        for pattern, source in search_patterns:
            if isinstance(pattern, Path) and pattern.suffix == '.dd':
                # Direct file check
                if pattern.exists():
                    self.image_path = pattern
                    self.ptjsonlib.add_properties({"imagePath": str(pattern)})
                    
                    ptprint(f"✓ Image found at default location: {pattern.name}", 
                           "OK", condition=not self.args.json)
                    
                    self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                        "imagePathCheck",
                        properties={
                            "success": True,
                            "source": source,
                            "imagePath": str(pattern)
                        }
                    ))
                    return True
            else:
                # JSON file search
                files = list(self.output_dir.glob(pattern.name))
                if files:
                    try:
                        with open(files[0], 'r') as f:
                            data = json.load(f)
                        
                        # Try different JSON structures
                        image_path = None
                        if "result" in data and "properties" in data["result"]:
                            image_path = data["result"]["properties"].get("imagePath")
                        else:
                            image_path = data.get("image_path") or data.get("imagePath")
                        
                        if image_path and Path(image_path).exists():
                            self.image_path = Path(image_path)
                            self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})
                            
                            ptprint(f"✓ Image path loaded from {source}: {self.image_path.name}", 
                                   "OK", condition=not self.args.json)
                            
                            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                                "imagePathCheck",
                                properties={
                                    "success": True,
                                    "source": source,
                                    "imagePath": str(self.image_path),
                                    "sourceFile": str(files[0])
                                }
                            ))
                            return True
                    except Exception as e:
                        ptprint(f"Warning: Could not read {files[0]}: {str(e)}", 
                               "WARNING", condition=not self.args.json)
        
        # Not found
        error_msg = "Cannot find forensic image"
        ptprint(error_msg, "ERROR", condition=not self.args.json)
        ptprint("Please ensure Steps 5 and 6 have been completed", 
               "ERROR", condition=not self.args.json)
        
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "imagePathCheck",
            properties={
                "success": False,
                "error": "Image not found"
            }
        ))
        return False
    
    def check_tools(self) -> bool:
        """
        Check if The Sleuth Kit tools are available
        
        Returns:
            bool: True if all tools available
        """
        ptprint("\n[STEP 2/6] Checking The Sleuth Kit Tools", 
               "TITLE", condition=not self.args.json)
        
        required_tools = ['mmls', 'fsstat', 'fls']
        missing_tools = []
        
        for tool in required_tools:
            result = self._run_command(['which', tool], timeout=5)
            
            if result["success"]:
                ptprint(f"✓ {tool}: Found", "OK", condition=not self.args.json)
            else:
                ptprint(f"✗ {tool}: NOT FOUND", "ERROR", condition=not self.args.json)
                missing_tools.append(tool)
        
        if missing_tools:
            error_msg = f"Missing tools: {', '.join(missing_tools)}"
            ptprint(error_msg, "ERROR", condition=not self.args.json)
            ptprint("Install: sudo apt-get install sleuthkit", 
                   "ERROR", condition=not self.args.json)
            
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "toolsCheck",
                properties={
                    "success": False,
                    "missingTools": missing_tools
                }
            ))
            return False
        
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "toolsCheck",
            properties={
                "success": True,
                "toolsChecked": required_tools
            }
        ))
        return True
    
    def analyze_partitions(self) -> bool:
        """
        Phase 1: Analyze partitions using mmls
        Detects partition table type and all partitions
        
        Returns:
            bool: True if analysis successful
        """
        ptprint("\n[STEP 3/6] Analyzing Partition Structure", 
               "TITLE", condition=not self.args.json)
        
        cmd = ['mmls', str(self.image_path)]
        result = self._run_command(cmd)
        
        partition_table_type = None
        partitions_found = []
        
        if not result["success"]:
            # No partition table = superfloppy format
            partition_table_type = "superfloppy"
            
            ptprint("⚠ No partition table detected (superfloppy format)", 
                   "WARNING", condition=not self.args.json)
            ptprint("  Device likely formatted as single filesystem", 
                   "INFO", condition=not self.args.json)
            
            # Add whole device as single "partition"
            partitions_found.append({
                "number": 0,
                "offset": 0,
                "sizeSectors": None,
                "type": "whole_device",
                "description": "No partition table - superfloppy format"
            })
        else:
            # Parse mmls output
            lines = result["stdout"].split('\n')
            
            for line in lines:
                # Detect partition table type
                if 'DOS Partition Table' in line or 'DOS' in line:
                    partition_table_type = "DOS/MBR"
                elif 'GPT' in line or 'GUID Partition Table' in line:
                    partition_table_type = "GPT"
                
                # Parse partition entries
                # Format: 002:  00:00  00001  62521343  62521343  Linux (0x83)
                match = re.match(r'(\d+):\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)', line)
                if match:
                    slot = int(match.group(1))
                    part_type = match.group(2)
                    start = int(match.group(3))
                    size = int(match.group(5))
                    description = match.group(6).strip()
                    
                    # Skip meta entries
                    if part_type.lower() in ['meta', '-----'] or size == 0:
                        continue
                    
                    partition = {
                        "number": slot,
                        "offset": start,
                        "sizeSectors": size,
                        "type": part_type,
                        "description": description
                    }
                    
                    partitions_found.append(partition)
                    
                    ptprint(f"  Partition {slot}: offset={start}, size={size} sectors", 
                           "INFO", condition=not self.args.json)
            
            ptprint(f"✓ Partition table type: {partition_table_type or 'unknown'}", 
                   "OK", condition=not self.args.json)
            ptprint(f"✓ Found {len(partitions_found)} partition(s)", 
                   "OK", condition=not self.args.json)
        
        # Update state
        self.partitions = partitions_found
        self.ptjsonlib.add_properties({
            "partitionTableType": partition_table_type or "unknown",
            "partitionsFound": len(partitions_found)
        })
        
        # Add node
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "partitionAnalysis",
            properties={
                "success": True,
                "partitionTableType": partition_table_type or "unknown",
                "partitionsFound": len(partitions_found),
                "partitions": partitions_found
            }
        ))
        
        return True
    
    def analyze_filesystem(self, partition: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 2: Analyze filesystem using fsstat
        Identifies filesystem type and metadata
        
        Args:
            partition: Partition info dictionary
            
        Returns:
            Dict with filesystem information
        """
        offset = partition.get("offset", 0)
        
        ptprint(f"\n[STEP 4/6] Analyzing Filesystem (offset={offset})", 
               "TITLE", condition=not self.args.json)
        
        cmd = ['fsstat', '-o', str(offset), str(self.image_path)]
        result = self._run_command(cmd)
        
        fs_info = {
            "offset": offset,
            "recognized": False,
            "type": "unknown",
            "state": "unrecognized",
            "label": None,
            "uuid": None,
            "sectorSize": None,
            "clusterSize": None,
            "totalClusters": None,
            "freeClusters": None
        }
        
        if not result["success"]:
            ptprint(f"✗ Filesystem not recognized at offset {offset}", 
                   "ERROR", condition=not self.args.json)
            return fs_info
        
        # Parse fsstat output
        output = result["stdout"]
        
        # Detect filesystem type
        fs_types = {
            'FAT32': 'FAT32', 'FAT16': 'FAT16', 'FAT12': 'FAT12',
            'exFAT': 'exFAT', 'NTFS': 'NTFS',
            'Ext4': 'ext4', 'ext4': 'ext4',
            'Ext3': 'ext3', 'ext3': 'ext3',
            'Ext2': 'ext2', 'ext2': 'ext2',
            'HFS+': 'HFS+', 'APFS': 'APFS',
            'ISO 9660': 'ISO9660'
        }
        
        for pattern, fs_type in fs_types.items():
            if pattern in output:
                fs_info["type"] = fs_type
                break
        
        # Extract metadata using regex
        metadata_patterns = {
            "label": r'(?:Volume Label|Label):\s*(.+)',
            "uuid": r'(?:Serial Number|UUID):\s*(.+)',
            "sectorSize": r'(?:Sector Size|sector size):\s*(\d+)',
            "clusterSize": r'(?:Cluster Size|Block Size):\s*(\d+)',
            "totalClusters": r'(?:Total Clusters|Block Count):\s*(\d+)',
            "freeClusters": r'(?:Free Clusters|Free Blocks):\s*(\d+)'
        }
        
        for field, pattern in metadata_patterns.items():
            match = re.search(pattern, output)
            if match:
                value = match.group(1).strip()
                if field in ['sectorSize', 'clusterSize', 'totalClusters', 'freeClusters']:
                    fs_info[field] = int(value)
                else:
                    fs_info[field] = value
        
        if fs_info["type"] != "unknown":
            fs_info["recognized"] = True
            fs_info["state"] = "recognized"
            self.filesystem_recognized = True
            
            ptprint(f"✓ Filesystem type: {fs_info['type']}", 
                   "OK", condition=not self.args.json)
            if fs_info["label"]:
                ptprint(f"  Volume label: {fs_info['label']}", 
                       "INFO", condition=not self.args.json)
        else:
            ptprint("⚠ Could not identify filesystem type", 
                   "WARNING", condition=not self.args.json)
        
        return fs_info
    
    def test_directory_structure(self, partition: Dict[str, Any], 
                                 fs_info: Dict[str, Any]) -> Tuple[bool, int, int, List[Dict]]:
        """
        Phase 3: Test directory structure readability using fls
        
        Args:
            partition: Partition info
            fs_info: Filesystem info
            
        Returns:
            Tuple (readable, active_count, deleted_count, file_list)
        """
        offset = partition.get("offset", 0)
        
        ptprint(f"\n[STEP 5/6] Testing Directory Structure (offset={offset})", 
               "TITLE", condition=not self.args.json)
        
        # Skip if filesystem not recognized
        if not fs_info.get("recognized"):
            ptprint("⚠ Skipping fls (filesystem not recognized)", 
                   "WARNING", condition=not self.args.json)
            return False, 0, 0, []
        
        cmd = ['fls', '-r', '-o', str(offset), str(self.image_path)]
        result = self._run_command(cmd, timeout=FLS_TIMEOUT)
        
        if not result["success"] or not result["stdout"]:
            ptprint("✗ Directory structure not readable", 
                   "ERROR", condition=not self.args.json)
            return False, 0, 0, []
        
        # Parse fls output
        lines = result["stdout"].split('\n')
        file_list = []
        active_count = 0
        deleted_count = 0
        
        for line in lines:
            if not line.strip():
                continue
            
            # fls format: r/r * 12345: filename.jpg
            # r = regular file, * = deleted
            is_deleted = '*' in line
            
            # Extract filename
            match = re.search(r':\s*(.+)$', line)
            if match:
                filename = match.group(1).strip()
                
                file_entry = {
                    "filename": filename,
                    "deleted": is_deleted,
                    "fullLine": line
                }
                
                file_list.append(file_entry)
                
                if is_deleted:
                    deleted_count += 1
                else:
                    active_count += 1
        
        total = active_count + deleted_count
        self.directory_readable = True
        
        ptprint(f"✓ Directory structure readable: {total} entries found", 
               "OK", condition=not self.args.json)
        ptprint(f"  Active files: {active_count}", "INFO", condition=not self.args.json)
        ptprint(f"  Deleted files: {deleted_count}", "INFO", condition=not self.args.json)
        
        return True, active_count, deleted_count, file_list
    
    def identify_image_files(self, file_list: List[Dict]) -> Dict[str, Any]:
        """
        Phase 4: Identify and count image files by type
        
        Args:
            file_list: List of files from fls
            
        Returns:
            Dict with image file counts
        """
        image_files = {
            "total": 0,
            "active": 0,
            "deleted": 0,
            "byType": {}
        }
        
        # Initialize counters for each type
        for img_type in IMAGE_EXTENSIONS.keys():
            image_files["byType"][img_type] = {"active": 0, "deleted": 0}
        
        for file_entry in file_list:
            filename = file_entry["filename"].lower()
            is_deleted = file_entry["deleted"]
            
            # Check for image extensions
            for img_type, extensions in IMAGE_EXTENSIONS.items():
                if any(filename.endswith(ext) for ext in extensions):
                    image_files["total"] += 1
                    
                    if is_deleted:
                        image_files["deleted"] += 1
                        image_files["byType"][img_type]["deleted"] += 1
                    else:
                        image_files["active"] += 1
                        image_files["byType"][img_type]["active"] += 1
                    
                    break  # Count each file only once
        
        # Log results
        if image_files["total"] > 0:
            ptprint(f"✓ Image files found: {image_files['total']}", 
                   "OK", condition=not self.args.json)
            ptprint(f"  Active: {image_files['active']}, Deleted: {image_files['deleted']}", 
                   "INFO", condition=not self.args.json)
            
            # Show breakdown by type
            for img_type, counts in image_files["byType"].items():
                total_type = counts["active"] + counts["deleted"]
                if total_type > 0:
                    ptprint(f"  {img_type.upper()}: {total_type} "
                           f"(active: {counts['active']}, deleted: {counts['deleted']})", 
                           "INFO", condition=not self.args.json)
        else:
            ptprint("⚠ No image files found", "WARNING", condition=not self.args.json)
        
        return image_files
    
    def determine_recovery_strategy(self, total_images: int) -> Tuple[str, str, float, List[str]]:
        """
        Phase 5: Determine optimal recovery strategy
        
        Args:
            total_images: Total number of image files found
            
        Returns:
            Tuple (method, tool, estimated_time_minutes, notes)
        """
        ptprint("\n[STEP 6/6] Determining Recovery Strategy", 
               "TITLE", condition=not self.args.json)
        
        method = None
        tool = None
        estimated_time = None
        notes = []
        
        # Decision logic
        if self.filesystem_recognized and self.directory_readable:
            # Ideal scenario - filesystem-based recovery
            method = "filesystem_scan"
            tool = "fls + icat (The Sleuth Kit)"
            estimated_time = max(15, total_images * 0.1)  # ~0.1 min per file
            
            notes.append("Filesystem structure intact - filesystem-based recovery recommended")
            notes.append("Original filenames and directory structure will be preserved")
            notes.append("Fast recovery method")
            
            ptprint("✓ Recommended method: FILESYSTEM SCAN", 
                   "OK", condition=not self.args.json, colortext=True)
            
        elif self.filesystem_recognized and not self.directory_readable:
            # Filesystem recognized but damaged
            method = "hybrid"
            tool = "fls + photorec (combined approach)"
            estimated_time = max(45, total_images * 0.3)
            
            notes.append("Filesystem recognized but directory structure damaged")
            notes.append("Hybrid approach recommended: filesystem scan + file carving")
            notes.append("Some filenames may be lost")
            
            ptprint("⚠ Recommended method: HYBRID (filesystem + carving)", 
                   "WARNING", condition=not self.args.json, colortext=True)
            
        else:
            # Filesystem not recognized - file carving required
            method = "file_carving"
            tool = "photorec / foremost"
            estimated_time = max(90, total_images * 0.5) if total_images > 0 else 90
            
            notes.append("Filesystem not recognized or severely damaged")
            notes.append("File carving required (signature-based recovery)")
            notes.append("Original filenames and directory structure will be lost")
            notes.append("Files recovered with generic names")
            notes.append("Slower but more thorough method")
            
            ptprint("⚠ Recommended method: FILE CARVING", 
                   "WARNING", condition=not self.args.json, colortext=True)
        
        ptprint(f"  Tool: {tool}", "INFO", condition=not self.args.json)
        ptprint(f"  Estimated time: ~{estimated_time:.0f} minutes", 
               "INFO", condition=not self.args.json)
        
        return method, tool, estimated_time, notes
    
    def run(self) -> None:
        """Main execution method"""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FILESYSTEM ANALYSIS v{__version__}", 
               "TITLE", condition=not self.args.json)
        ptprint(f"Case ID: {self.case_id}", "INFO", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        
        # Step 1: Load image path
        if not self.load_image_path():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 2: Check tools
        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 3: Analyze partitions
        if not self.analyze_partitions():
            self.ptjsonlib.set_status("finished")
            return
        
        # Step 4-5: Analyze each partition
        total_image_files = {"total": 0, "active": 0, "deleted": 0, "byType": {}}
        
        for partition in self.partitions:
            # Analyze filesystem
            fs_info = self.analyze_filesystem(partition)
            
            # Test directory structure
            readable, active, deleted, file_list = self.test_directory_structure(
                partition, fs_info
            )
            
            if readable:
                # Identify image files
                image_files = self.identify_image_files(file_list)
                
                # Accumulate totals
                total_image_files["total"] += image_files["total"]
                total_image_files["active"] += image_files["active"]
                total_image_files["deleted"] += image_files["deleted"]
                
                # Merge by-type counts
                for img_type, counts in image_files["byType"].items():
                    if img_type not in total_image_files["byType"]:
                        total_image_files["byType"][img_type] = {"active": 0, "deleted": 0}
                    total_image_files["byType"][img_type]["active"] += counts["active"]
                    total_image_files["byType"][img_type]["deleted"] += counts["deleted"]
        
        # Step 6: Determine recovery strategy
        method, tool, est_time, notes = self.determine_recovery_strategy(
            total_image_files["total"]
        )
        
        # Update properties
        self.ptjsonlib.add_properties({
            "filesystemRecognized": self.filesystem_recognized,
            "directoryStructureReadable": self.directory_readable,
            "imageFilesFound": total_image_files,
            "recommendedMethod": method,
            "recommendedTool": tool,
            "estimatedTimeMinutes": est_time
        })
        
        # Add strategy node
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "recoveryStrategy",
            properties={
                "recommendedMethod": method,
                "recommendedTool": tool,
                "estimatedTimeMinutes": est_time,
                "notes": notes,
                "filesystemRecognized": self.filesystem_recognized,
                "directoryReadable": self.directory_readable,
                "imageFilesFound": total_image_files["total"]
            }
        ))
        
        # Summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("ANALYSIS COMPLETED", "OK", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Filesystem recognized: {self.filesystem_recognized}", 
               "INFO", condition=not self.args.json)
        ptprint(f"Directory readable: {self.directory_readable}", 
               "INFO", condition=not self.args.json)
        ptprint(f"Image files found: {total_image_files['total']}", 
               "INFO", condition=not self.args.json)
        ptprint(f"Recovery method: {method}", "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint("\nNext step: Step 11 (Recovery Strategy Decision)", 
               "INFO", condition=not self.args.json)
        
        self.ptjsonlib.set_status("finished")
    
    def save_report(self) -> Optional[str]:
        """Save JSON report"""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None
        else:
            json_file = self.output_dir / f"{self.case_id}_filesystem_analysis.json"
            
            with open(json_file, 'w', encoding='utf-8') as f:
                f.write(self.ptjsonlib.get_result_json())
            
            ptprint(f"\n✓ Analysis report saved: {json_file}", 
                   "OK", condition=not self.args.json)
            return str(json_file)


# ============================================================================
# MODULE-LEVEL WORKFLOW FUNCTIONS
# ============================================================================

def get_help():
    """Return help structure for ptprinthelper"""
    return [
        {"description": [
            "Forensic filesystem analysis tool - ptlibs compliant",
            "Analyzes filesystem structure and recommends recovery strategy"
        ]},
        {"usage": ["ptfilesystemanalysis <case-id> [options]"]},
        {"usage_example": [
            "ptfilesystemanalysis PHOTO-2025-001",
            "ptfilesystemanalysis CASE-042 --json",
            "ptfilesystemanalysis TEST-001 --dry-run"
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run", "", "Simulate analysis without executing commands"],
            ["-j", "--json", "", "JSON output for platform integration"],
            ["-q", "--quiet", "", "Suppress progress output"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"]
        ]},
        {"analysis_phases": [
            "Phase 1: Partition analysis (mmls)",
            "Phase 2: Filesystem analysis (fsstat)",
            "Phase 3: Directory structure test (fls)",
            "Phase 4: Image file identification",
            "Phase 5: Recovery strategy determination"
        ]},
        {"recovery_methods": [
            "filesystem_scan - Fast, preserves names (recognized FS)",
            "hybrid - Medium speed, partial recovery (damaged FS)",
            "file_carving - Slow, thorough (unrecognized FS)"
        ]},
        {"forensic_notes": [
            "Requires Step 6 (Hash Verification) results",
            "Uses The Sleuth Kit (mmls, fsstat, fls)",
            "Supports FAT32, exFAT, NTFS, ext4, and more",
            "Complies with ISO/IEC 27037 and NIST SP 800-86"
        ]}
    ]


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} - Forensic filesystem analysis"
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
    SCRIPTNAME = "ptfilesystemanalysis"
    
    try:
        args = parse_args()
        
        # Run analysis
        analyzer = PtFilesystemAnalysis(args)
        analyzer.run()
        analyzer.save_report()
        
        # Return exit code based on success
        props = analyzer.ptjsonlib.json_data["result"]["properties"]
        
        if props.get("recommendedMethod"):
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
