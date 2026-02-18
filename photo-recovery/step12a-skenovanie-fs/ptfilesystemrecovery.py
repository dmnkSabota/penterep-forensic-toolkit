#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptfilesystemrecovery - Forensic filesystem-based photo recovery tool

    ptfilesystemrecovery is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptfilesystemrecovery is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptfilesystemrecovery.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import re
import json
import shutil
import subprocess
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
FLS_TIMEOUT    = 1800   # 30 minutes for large media
ICAT_TIMEOUT   = 60     # 60 seconds per file
EXIF_TIMEOUT   = 30     # 30 seconds per file

# Supported image file extensions (lowercase)
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg',
    '.png',
    '.tif', '.tiff',
    '.bmp',
    '.gif',
    '.heic', '.heif',
    '.webp',
    # RAW formats
    '.cr2', '.cr3',     # Canon
    '.nef', '.nrw',     # Nikon
    '.arw', '.srf', '.sr2',  # Sony
    '.dng',             # Adobe / Generic
    '.orf',             # Olympus
    '.raf',             # Fuji
    '.rw2',             # Panasonic
    '.pef',             # Pentax
    '.raw',             # Generic RAW
}

# Human-readable format grouping for statistics
FORMAT_GROUPS = {
    'jpeg': ['.jpg', '.jpeg'],
    'png':  ['.png'],
    'tiff': ['.tif', '.tiff'],
    'bmp':  ['.bmp'],
    'gif':  ['.gif'],
    'heic': ['.heic', '.heif'],
    'webp': ['.webp'],
    'raw':  ['.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2',
             '.dng', '.orf', '.raf', '.rw2', '.pef', '.raw'],
}


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtFilesystemRecovery:
    """
    Forensic filesystem-based photo recovery tool - ptlibs compliant.

    Six-phase recovery process:
    1. Load filesystem analysis from Step 10 (partition info, image path)
    2. Check required tools (fls, icat, file, identify, exiftool)
    3. Prepare output directory structure
    4. Scan filesystem with fls (active + deleted files)
    5. Extract image files with icat, validate, extract metadata
    6. Generate JSON report and text summary

    Complies with ISO/IEC 27037:2012 and NIST SP 800-86.
    READ-ONLY: never modifies the forensic image.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.force      = self.args.force
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State filled during run
        self.image_path  = None
        self.fs_analysis = None      # dict loaded from Step 10 JSON

        # Output sub-directories (created in prepare_directories)
        self.recovery_base  = self.output_dir / f"{self.case_id}_recovered"
        self.active_dir     = self.recovery_base / "active"
        self.deleted_dir    = self.recovery_base / "deleted"
        self.corrupted_dir  = self.recovery_base / "corrupted"
        self.metadata_dir   = self.recovery_base / "metadata"

        # Accumulated counters
        self._total_scanned  = 0
        self._active_images  = 0
        self._deleted_images = 0
        self._extracted      = 0
        self._valid          = 0
        self._corrupted      = 0
        self._invalid        = 0
        self._with_exif      = 0
        self._by_format: Dict[str, int] = {}
        self._recovered_files: List[Dict] = []

        # Top-level JSON properties
        self.ptjsonlib.add_properties({
            "caseId":                self.case_id,
            "outputDirectory":       str(self.output_dir),
            "timestamp":             datetime.now(timezone.utc).isoformat(),
            "scriptVersion":         __version__,
            "method":                "filesystem_scan",
            "imagePath":             None,
            "partitionsProcessed":   0,
            "totalFilesScanned":     0,
            "imageFilesFound":       0,
            "activeImages":          0,
            "deletedImages":         0,
            "imagesExtracted":       0,
            "validImages":           0,
            "corruptedImages":       0,
            "invalidImages":         0,
            "withExif":              0,
            "byFormat":              {},
            "successRate":           None,
            "recoveryBaseDir":       str(self.recovery_base),
            "dryRun":                self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------------------

    def _run_command(self, cmd: List[str], timeout: int = 300,
                     capture_binary: bool = False) -> Dict[str, Any]:
        """Execute a subprocess, return dict(success, stdout, stderr, returncode)."""
        result = {"success": False, "stdout": b"" if capture_binary else "",
                  "stderr": "", "returncode": -1}

        if self.dry_run:
            ptprint(f"[DRY-RUN] Would execute: {' '.join(str(c) for c in cmd)}",
                    "INFO", condition=not self.args.json)
            result["success"] = True
            result["stdout"]  = b"[DRY-RUN]" if capture_binary else "[DRY-RUN] Simulated success"
            return result

        try:
            if capture_binary:
                proc = subprocess.run(cmd, capture_output=True,
                                      timeout=timeout, check=False)
                result.update({
                    "success":    proc.returncode == 0,
                    "stdout":     proc.stdout,
                    "stderr":     proc.stderr.decode(errors="replace").strip(),
                    "returncode": proc.returncode,
                })
            else:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=timeout, check=False)
                result.update({
                    "success":    proc.returncode == 0,
                    "stdout":     proc.stdout.strip(),
                    "stderr":     proc.stderr.strip(),
                    "returncode": proc.returncode,
                })
        except subprocess.TimeoutExpired:
            result["stderr"] = f"Command timeout after {timeout}s"
        except Exception as exc:
            result["stderr"] = str(exc)

        return result

    def _format_group(self, ext: str) -> str:
        """Map a file extension to its format group key."""
        ext = ext.lower()
        for group, extensions in FORMAT_GROUPS.items():
            if ext in extensions:
                return group
        return ext.lstrip('.')

    # -------------------------------------------------------------------------
    # PHASE 1 – LOAD STEP 10 ANALYSIS
    # -------------------------------------------------------------------------

    def load_fs_analysis(self) -> bool:
        """
        Load filesystem analysis results from Step 10.

        Reads {case_id}_filesystem_analysis.json produced by ptfilesystemanalysis.
        Validates that the recommended method allows filesystem-based recovery.

        Returns:
            bool: True if analysis loaded and method is compatible
        """
        ptprint("\n[STEP 1/6] Loading Filesystem Analysis from Step 10",
                "TITLE", condition=not self.args.json)

        analysis_file = self.output_dir / f"{self.case_id}_filesystem_analysis.json"

        if not analysis_file.exists():
            ptprint(f"✗ File not found: {analysis_file.name}",
                    "ERROR", condition=not self.args.json)
            ptprint("  Please run Step 10 (Filesystem Analysis) first!",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False, "error": "filesystem_analysis.json not found"}
            ))
            return False

        try:
            with open(analysis_file, 'r', encoding='utf-8') as fh:
                raw = json.load(fh)
        except Exception as exc:
            ptprint(f"✗ Cannot read analysis file: {exc}",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False, "error": str(exc)}
            ))
            return False

        # Support both flat JSON (legacy step10 wrapper) and ptlibs JSON
        if "result" in raw and "properties" in raw["result"]:
            props = raw["result"]["properties"]
            recommended = props.get("recommendedMethod")
            # Partitions may live in nodes
            self.fs_analysis = {
                "recommended_method": recommended,
                "image_file":         props.get("imagePath"),
                "partitions":         [],
            }
            # Extract partition list from nodes
            for node in raw["result"].get("nodes", []):
                if node.get("type") == "partitionAnalysis":
                    self.fs_analysis["partitions"] = node.get("properties", {}).get("partitions", [])
                    break
        else:
            # Flat / legacy format
            self.fs_analysis = raw
            recommended = raw.get("recommended_method")

        # Resolve image path
        image_path_str = self.fs_analysis.get("image_file") or self.fs_analysis.get("imagePath")
        if not image_path_str:
            ptprint("✗ Image path missing in analysis file",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False, "error": "imagePath missing"}
            ))
            return False

        self.image_path = Path(image_path_str)
        if not self.image_path.exists() and not self.dry_run:
            ptprint(f"✗ Forensic image not found: {self.image_path}",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False, "error": f"Image file missing: {self.image_path}"}
            ))
            return False

        # Check method compatibility
        if recommended == "file_carving" and not self.force:
            ptprint("⚠ Step 10 recommended file_carving, not filesystem_scan",
                    "WARNING", condition=not self.args.json)
            ptprint("  Use --force to override, or run Step 12B (File Carving) instead",
                    "WARNING", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "fsAnalysisLoad",
                properties={"success": False, "error": "Method mismatch: file_carving recommended"}
            ))
            return False

        if recommended == "hybrid":
            ptprint("⚠ Step 10 recommended hybrid approach",
                    "WARNING", condition=not self.args.json)
            ptprint("  Will perform filesystem scan; consider also running Step 12B",
                    "INFO", condition=not self.args.json)

        partitions = self.fs_analysis.get("partitions", [])

        ptprint(f"✓ Analysis loaded: {analysis_file.name}",
                "OK", condition=not self.args.json)
        ptprint(f"  Image:      {self.image_path.name}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Method:     {recommended}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Partitions: {len(partitions)}",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "fsAnalysisLoad",
            properties={
                "success":            True,
                "sourceFile":         str(analysis_file),
                "recommendedMethod":  recommended,
                "imagePath":          str(self.image_path),
                "partitionsFound":    len(partitions),
            }
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 2 – CHECK TOOLS
    # -------------------------------------------------------------------------

    def check_tools(self) -> bool:
        """
        Verify that all required external tools are installed and available.

        Required: fls, icat (The Sleuth Kit), file (coreutils),
                  identify (ImageMagick), exiftool.

        Returns:
            bool: True if all tools present
        """
        ptprint("\n[STEP 2/6] Checking Required Tools",
                "TITLE", condition=not self.args.json)

        required = {
            'fls':      'The Sleuth Kit – file listing',
            'icat':     'The Sleuth Kit – inode extraction',
            'file':     'File type detection',
            'identify': 'ImageMagick – image validation',
            'exiftool': 'EXIF metadata extraction',
        }
        missing = []

        for tool, description in required.items():
            res = self._run_command(['which', tool], timeout=5)
            if res["success"]:
                ptprint(f"✓ {tool}: Found ({description})",
                        "OK", condition=not self.args.json)
            else:
                ptprint(f"✗ {tool}: NOT FOUND ({description})",
                        "ERROR", condition=not self.args.json)
                missing.append(tool)

        if missing:
            ptprint(f"✗ Missing tools: {', '.join(missing)}",
                    "ERROR", condition=not self.args.json)
            ptprint("  Install: sudo apt-get install sleuthkit imagemagick libimage-exiftool-perl",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "toolsCheck",
                properties={"success": False, "missingTools": missing}
            ))
            return False

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "toolsCheck",
            properties={"success": True, "toolsChecked": list(required.keys())}
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 3 – PREPARE DIRECTORIES
    # -------------------------------------------------------------------------

    def prepare_directories(self) -> bool:
        """
        Create output directory structure.

        Structure:
            {case_id}_recovered/
                active/      – active files, original dir tree preserved
                deleted/     – deleted-but-recoverable files
                corrupted/   – partially damaged files
                metadata/    – per-file JSON metadata catalogs

        Returns:
            bool: True always (mkdir errors are fatal)
        """
        ptprint("\n[STEP 3/6] Preparing Output Directories",
                "TITLE", condition=not self.args.json)

        dirs = {
            "active":    self.active_dir,
            "deleted":   self.deleted_dir,
            "corrupted": self.corrupted_dir,
            "metadata":  self.metadata_dir,
        }

        for name, path in dirs.items():
            if not self.dry_run:
                path.mkdir(parents=True, exist_ok=True)
            ptprint(f"  {name}/  →  {path}",
                    "INFO", condition=not self.args.json)

        ptprint("✓ Output directories ready",
                "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "directoriesPrep",
            properties={
                "success":      True,
                "recoveryBase": str(self.recovery_base),
                "activeDir":    str(self.active_dir),
                "deletedDir":   str(self.deleted_dir),
                "corruptedDir": str(self.corrupted_dir),
                "metadataDir":  str(self.metadata_dir),
            }
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 4 – SCAN FILESYSTEM  (fls)
    # -------------------------------------------------------------------------

    def scan_filesystem(self, partition: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Run fls -r -d -p on a single partition to list all file entries
        including deleted ones.

        fls output line format:
            r/r * 12845:   /DCIM/100CANON/IMG_0001.JPG
            ^   ^ ^         ^
            type del inode  full-path

        Args:
            partition: Partition dict (keys: offset, number)

        Returns:
            List of file entry dicts (inode, path, filename, deleted)
        """
        offset = partition.get("offset", 0)
        part_num = partition.get("number", 0)

        ptprint(f"\n  [fls] Scanning partition {part_num} (offset={offset}) …",
                "INFO", condition=not self.args.json)

        cmd = ['fls', '-r', '-d', '-p', '-o', str(offset), str(self.image_path)]
        result = self._run_command(cmd, timeout=FLS_TIMEOUT)

        if not result["success"]:
            ptprint(f"  ✗ fls failed: {result['stderr']}",
                    "ERROR", condition=not self.args.json)
            return []

        entries = []
        for line in result["stdout"].splitlines():
            line = line.strip()
            if not line:
                continue

            # Skip directory lines (start with d/d)
            if line.startswith('d/d'):
                continue

            is_deleted = '*' in line.split(':')[0]   # star appears before the colon

            # Extract inode: last integer before the colon
            inode_match = re.search(r'(\d+):', line)
            if not inode_match:
                continue
            inode = int(inode_match.group(1))

            # Extract path: everything after "inode: "
            path_match = re.search(r':\s+(.+)$', line)
            if not path_match:
                continue
            filepath = path_match.group(1).strip()

            entries.append({
                "inode":    inode,
                "path":     filepath,
                "filename": os.path.basename(filepath),
                "deleted":  is_deleted,
            })
            self._total_scanned += 1

        ptprint(f"  ✓ {len(entries)} file entries found",
                "OK", condition=not self.args.json)
        return entries

    def filter_image_files(self, entries: List[Dict[str, Any]]) \
            -> Tuple[List[Dict], List[Dict]]:
        """
        Split file entries into active and deleted image files.

        Args:
            entries: All file entries from fls

        Returns:
            Tuple (active_images, deleted_images)
        """
        active, deleted = [], []

        for entry in entries:
            ext = os.path.splitext(entry["filename"].lower())[1]
            if ext not in IMAGE_EXTENSIONS:
                continue

            group = self._format_group(ext)
            self._by_format[group] = self._by_format.get(group, 0) + 1

            if entry["deleted"]:
                deleted.append(entry)
                self._deleted_images += 1
            else:
                active.append(entry)
                self._active_images += 1

        total = len(active) + len(deleted)
        ptprint(f"  ✓ Image files: {total}  (active={len(active)}, deleted={len(deleted)})",
                "OK", condition=not self.args.json)
        return active, deleted

    # -------------------------------------------------------------------------
    # PHASE 5 – EXTRACT / VALIDATE / METADATA  (icat + file + identify + exiftool)
    # -------------------------------------------------------------------------

    def _extract_single(self, entry: Dict, offset: int,
                        output_base: Path) -> Optional[Path]:
        """
        Extract one file from the forensic image using icat.

        Args:
            entry:       File entry (inode, path, …)
            offset:      Partition sector offset
            output_base: active_dir or deleted_dir

        Returns:
            Path of extracted file, or None on failure
        """
        inode = entry["inode"]
        # Preserve original directory tree
        relative = entry["path"].lstrip('/')
        dest = output_base / relative
        dest.parent.mkdir(parents=True, exist_ok=True)

        cmd = ['icat', '-o', str(offset), str(self.image_path), str(inode)]

        if self.dry_run:
            self._run_command(cmd)   # logs only
            return dest              # pretend success

        try:
            with open(dest, 'wb') as fh:
                proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE,
                                      timeout=ICAT_TIMEOUT, check=False)
            if proc.returncode == 0:
                return dest
            ptprint(f"    ✗ icat inode {inode}: {proc.stderr.decode(errors='replace').strip()}",
                    "WARNING", condition=not self.args.json)
            if dest.exists():
                dest.unlink()
            return None
        except Exception as exc:
            ptprint(f"    ✗ icat inode {inode}: {exc}",
                    "WARNING", condition=not self.args.json)
            if dest.exists():
                dest.unlink()
            return None

    def _validate_image(self, filepath: Path) \
            -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate an extracted image file.

        Three-stage check:
        1. Non-zero size
        2. `file` command confirms image type
        3. ImageMagick `identify` confirms readable structure

        Returns:
            (is_valid, status, info)
            status ∈ {'valid', 'corrupted', 'invalid'}
        """
        info: Dict[str, Any] = {
            "size": 0, "fileType": None,
            "imageFormat": None, "dimensions": None,
            "validationErrors": [],
        }

        # Stage 1 – size
        try:
            size = filepath.stat().st_size
            info["size"] = size
        except Exception as exc:
            info["validationErrors"].append(f"stat failed: {exc}")
            return False, 'invalid', info

        if size == 0:
            info["validationErrors"].append("Empty file (0 bytes)")
            return False, 'invalid', info

        # Stage 2 – file command
        res = self._run_command(['file', '-b', str(filepath)], timeout=10)
        if res["success"]:
            info["fileType"] = res["stdout"]
            keywords = ['image', 'jpeg', 'png', 'tiff', 'gif', 'bitmap', 'raw',
                        'canon', 'nikon', 'exif', 'riff webp']
            if not any(kw in res["stdout"].lower() for kw in keywords):
                info["validationErrors"].append(f"file: not an image ({res['stdout'][:80]})")
                return False, 'invalid', info

        # Stage 3 – ImageMagick identify
        res = self._run_command(['identify', str(filepath)], timeout=30)
        if res["success"]:
            m = re.search(r'(\w+)\s+(\d+)x(\d+)', res["stdout"])
            if m:
                info["imageFormat"] = m.group(1)
                info["dimensions"]  = f"{m.group(2)}x{m.group(3)}"
            return True, 'valid', info

        info["validationErrors"].append("identify failed – file likely corrupted")
        return False, ('corrupted' if size > 1024 else 'invalid'), info

    def _extract_metadata(self, filepath: Path,
                          entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract filesystem timestamps and EXIF data for a recovered file.

        Args:
            filepath: Extracted file path
            entry:    Original fls entry

        Returns:
            Metadata dictionary
        """
        meta: Dict[str, Any] = {
            "filename":     filepath.name,
            "originalPath": entry["path"],
            "inode":        entry["inode"],
            "deleted":      entry["deleted"],
            "fsMetadata":   {},
            "exifMetadata": {},
            "hasExif":      False,
        }

        # FS timestamps
        try:
            st = filepath.stat()
            meta["fsMetadata"] = {
                "sizeBytes":    st.st_size,
                "modifiedTime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "accessedTime": datetime.fromtimestamp(st.st_atime, tz=timezone.utc).isoformat(),
                "createdTime":  datetime.fromtimestamp(st.st_ctime, tz=timezone.utc).isoformat(),
            }
        except Exception as exc:
            meta["fsMetadata"]["error"] = str(exc)

        # EXIF via exiftool
        res = self._run_command(
            ['exiftool', '-json', '-charset', 'utf8', str(filepath)],
            timeout=EXIF_TIMEOUT
        )
        if res["success"]:
            try:
                exif_list = json.loads(res["stdout"])
                if exif_list:
                    meta["exifMetadata"] = exif_list[0]
                    exif_keys = {'DateTimeOriginal', 'CreateDate', 'GPSLatitude',
                                 'Make', 'Model', 'LensModel'}
                    if exif_keys & set(exif_list[0].keys()):
                        meta["hasExif"] = True
                        self._with_exif += 1
            except Exception as exc:
                meta["exifMetadata"] = {"parseError": str(exc)}

        return meta

    def process_partition(self, partition: Dict[str, Any]) -> None:
        """
        Run the full scan → filter → extract → validate → metadata pipeline
        for one partition.

        Args:
            partition: Partition dict from Step 10 analysis
        """
        part_num = partition.get("number", 0)
        offset   = partition.get("offset", 0)

        ptprint(f"\n{'='*70}", "TITLE", condition=not self.args.json)
        ptprint(f"PROCESSING PARTITION {part_num}  (offset={offset})",
                "TITLE", condition=not self.args.json)
        ptprint(f"{'='*70}", "TITLE", condition=not self.args.json)

        # Skip partitions whose filesystem was not recognised by Step 10
        fs_info = partition.get("filesystem", {})
        if fs_info and not fs_info.get("recognized", True):
            ptprint("  ⚠ Filesystem not recognized – skipping this partition",
                    "WARNING", condition=not self.args.json)
            ptprint("    Consider running Step 12B (File Carving) for this partition",
                    "INFO",    condition=not self.args.json)
            return

        # ── Scan ──────────────────────────────────────────────────────────────
        entries = self.scan_filesystem(partition)
        if not entries:
            ptprint("  No file entries found in this partition", "WARNING",
                    condition=not self.args.json)
            return

        # ── Filter ────────────────────────────────────────────────────────────
        active_imgs, deleted_imgs = self.filter_image_files(entries)
        if not active_imgs and not deleted_imgs:
            ptprint("  No image files found in this partition", "WARNING",
                    condition=not self.args.json)
            return

        # ── Extract + Validate + Metadata ────────────────────────────────────
        all_targets = (
            [(e, self.active_dir,  "active")  for e in active_imgs] +
            [(e, self.deleted_dir, "deleted") for e in deleted_imgs]
        )
        total = len(all_targets)

        ptprint(f"\n  Extracting {total} image files …",
                "TITLE", condition=not self.args.json)

        partition_node = self.ptjsonlib.create_node_object(
            "partitionRecovery",
            properties={
                "partitionNumber": part_num,
                "offset":          offset,
                "totalImages":     total,
            }
        )
        self.ptjsonlib.add_node(partition_node)

        for idx, (entry, out_base, status_label) in enumerate(all_targets, 1):
            if idx % 25 == 0 or idx == total:
                pct = idx * 100 // total
                ptprint(f"    Progress: {idx}/{total} ({pct}%)",
                        "INFO", condition=not self.args.json)

            # Extract
            extracted = self._extract_single(entry, offset, out_base)
            if extracted is None:
                self._invalid += 1
                continue
            self._extracted += 1

            # Validate
            is_valid, vstatus, vinfo = self._validate_image(extracted)

            if vstatus == 'valid':
                self._valid += 1

                # Metadata
                meta = self._extract_metadata(extracted, entry)
                meta_file = self.metadata_dir / f"{extracted.name}_metadata.json"
                if not self.dry_run:
                    with open(meta_file, 'w', encoding='utf-8') as fh:
                        json.dump(meta, fh, indent=2, ensure_ascii=False,
                                  default=str)

                self._recovered_files.append({
                    "filename":     extracted.name,
                    "originalPath": entry["path"],
                    "recoveredPath": str(extracted.relative_to(self.recovery_base)),
                    "inode":        entry["inode"],
                    "status":       status_label,
                    "sizeBytes":    vinfo["size"],
                    "format":       vinfo.get("imageFormat"),
                    "dimensions":   vinfo.get("dimensions"),
                    "hasExif":      meta.get("hasExif", False),
                })

            elif vstatus == 'corrupted':
                self._corrupted += 1
                dest = self.corrupted_dir / extracted.name
                if not self.dry_run:
                    shutil.move(str(extracted), str(dest))

            else:  # invalid
                self._invalid += 1
                if not self.dry_run and extracted.exists():
                    extracted.unlink()

        ptprint(f"  ✓ Partition {part_num} done",
                "OK", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full six-phase recovery pipeline."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("FILESYSTEM-BASED PHOTO RECOVERY", "TITLE",
                condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        # Phase 1 – Load Step 10 results
        if not self.load_fs_analysis():
            self.ptjsonlib.set_status("finished")
            return

        # Phase 2 – Tools
        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return

        # Phase 3 – Directories
        if not self.prepare_directories():
            self.ptjsonlib.set_status("finished")
            return

        # Phases 4–5 – Per-partition recovery
        partitions = self.fs_analysis.get("partitions", [])
        partitions_done = 0

        for partition in partitions:
            self.process_partition(partition)
            partitions_done += 1

        # Phase 6 – Final stats
        total_images = self._active_images + self._deleted_images
        success_rate: Optional[float] = None
        if self._extracted > 0:
            success_rate = round(self._valid / self._extracted * 100, 1)

        self.ptjsonlib.add_properties({
            "partitionsProcessed": partitions_done,
            "totalFilesScanned":   self._total_scanned,
            "imageFilesFound":     total_images,
            "activeImages":        self._active_images,
            "deletedImages":       self._deleted_images,
            "imagesExtracted":     self._extracted,
            "validImages":         self._valid,
            "corruptedImages":     self._corrupted,
            "invalidImages":       self._invalid,
            "withExif":            self._with_exif,
            "byFormat":            self._by_format,
            "successRate":         success_rate,
        })

        # Summary node
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "recoverySummary",
            properties={
                "partitionsProcessed": partitions_done,
                "imageFilesFound":     total_images,
                "imagesExtracted":     self._extracted,
                "validImages":         self._valid,
                "corruptedImages":     self._corrupted,
                "invalidImages":       self._invalid,
                "withExif":            self._with_exif,
                "byFormat":            self._by_format,
                "successRate":         success_rate,
            }
        ))

        # Console summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("RECOVERY COMPLETED", "OK", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Image files found:  {total_images}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Active:           {self._active_images}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Deleted:          {self._deleted_images}",
                "INFO", condition=not self.args.json)
        ptprint(f"Extracted:          {self._extracted}",
                "INFO", condition=not self.args.json)
        ptprint(f"Valid images:       {self._valid}",
                "OK",   condition=not self.args.json)
        ptprint(f"Corrupted:          {self._corrupted}",
                "WARNING", condition=not self.args.json)
        ptprint(f"Invalid:            {self._invalid}",
                "ERROR",   condition=not self.args.json)
        if success_rate is not None:
            ptprint(f"Success rate:       {success_rate}%",
                    "OK", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint("\nNext step: Step 13 (Photo Cataloging)",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        """
        Persist the JSON report and write a human-readable text summary.

        In --json mode the result is printed to stdout only.
        Otherwise two files are written:
          - {case_id}_recovery_report.json  (machine-readable)
          - {case_id}_recovered/RECOVERY_REPORT.txt (human-readable)

        Returns:
            Path to the JSON file, or None in --json mode
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        # Machine-readable JSON
        json_file = self.output_dir / f"{self.case_id}_recovery_report.json"

        report = {
            "result":         json.loads(self.ptjsonlib.get_result_json()),
            "recoveredFiles": self._recovered_files,
            "outputDirectories": {
                "active":    str(self.active_dir),
                "deleted":   str(self.deleted_dir),
                "corrupted": str(self.corrupted_dir),
                "metadata":  str(self.metadata_dir),
            },
        }

        with open(json_file, 'w', encoding='utf-8') as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False, default=str)

        ptprint(f"✓ JSON report saved: {json_file}",
                "OK", condition=not self.args.json)

        # Human-readable text summary
        txt_file = self.recovery_base / "RECOVERY_REPORT.txt"
        self.recovery_base.mkdir(parents=True, exist_ok=True)

        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        with open(txt_file, 'w', encoding='utf-8') as fh:
            fh.write("=" * 70 + "\n")
            fh.write("FILESYSTEM-BASED PHOTO RECOVERY REPORT\n")
            fh.write("=" * 70 + "\n\n")
            fh.write(f"Case ID:   {self.case_id}\n")
            fh.write(f"Timestamp: {props.get('timestamp','')}\n")
            fh.write(f"Method:    {props.get('method','filesystem_scan')}\n\n")
            fh.write("STATISTICS:\n")
            fh.write(f"  Files scanned:    {props.get('totalFilesScanned',0)}\n")
            fh.write(f"  Images found:     {props.get('imageFilesFound',0)}\n")
            fh.write(f"    Active:         {props.get('activeImages',0)}\n")
            fh.write(f"    Deleted:        {props.get('deletedImages',0)}\n")
            fh.write(f"  Extracted:        {props.get('imagesExtracted',0)}\n")
            fh.write(f"  Valid:            {props.get('validImages',0)}\n")
            fh.write(f"  Corrupted:        {props.get('corruptedImages',0)}\n")
            fh.write(f"  Invalid:          {props.get('invalidImages',0)}\n")
            fh.write(f"  With EXIF:        {props.get('withExif',0)}\n")
            if props.get('successRate') is not None:
                fh.write(f"  Success rate:     {props['successRate']}%\n")
            fh.write("\nBY FORMAT:\n")
            for fmt, cnt in sorted(props.get('byFormat', {}).items()):
                fh.write(f"  {fmt.upper():8s}: {cnt}\n")
            fh.write("\n" + "=" * 70 + "\n")
            fh.write("RECOVERED FILES (first 100):\n")
            fh.write("=" * 70 + "\n\n")
            for rec in self._recovered_files[:100]:
                fh.write(f"{rec['filename']}\n")
                fh.write(f"  Original:   {rec['originalPath']}\n")
                fh.write(f"  Recovered:  {rec['recoveredPath']}\n")
                fh.write(f"  Size:       {rec['sizeBytes']} bytes\n")
                if rec.get('dimensions'):
                    fh.write(f"  Dimensions: {rec['dimensions']}\n")
                fh.write(f"  EXIF:       {'Yes' if rec.get('hasExif') else 'No'}\n\n")
            if len(self._recovered_files) > 100:
                fh.write(f"… and {len(self._recovered_files)-100} more files\n")

        ptprint(f"✓ Text report saved: {txt_file}",
                "OK", condition=not self.args.json)
        return str(json_file)


# ============================================================================
# CLI HELPERS
# ============================================================================

def get_help():
    """Return help structure for ptprinthelper.help_print."""
    return [
        {"description": [
            "Forensic filesystem-based photo recovery tool – ptlibs compliant",
            "Recovers image files using fls + icat (The Sleuth Kit)",
            "Preserves original filenames, directory structure and EXIF metadata",
        ]},
        {"usage": ["ptfilesystemrecovery <case-id> [options]"]},
        {"usage_example": [
            "ptfilesystemrecovery PHOTO-2025-001",
            "ptfilesystemrecovery CASE-042 --json",
            "ptfilesystemrecovery TEST-001 --dry-run",
            "ptfilesystemrecovery CASE-007 --force   # override carving recommendation",
        ]},
        {"options": [
            ["case-id",    "",              "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<dir>",  f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",              "Simulate without executing external commands"],
            ["--force",    "",              "Run even if Step 10 recommended file_carving"],
            ["-j",  "--json",       "",      "JSON output for platform integration"],
            ["-q",  "--quiet",      "",      "Suppress progress output"],
            ["-h",  "--help",       "",      "Show this help message and exit"],
            ["--version",  "",              "Show version and exit"],
        ]},
        {"recovery_phases": [
            "Phase 1: Load filesystem analysis (Step 10 JSON)",
            "Phase 2: Check tools (fls, icat, file, identify, exiftool)",
            "Phase 3: Prepare output directories",
            "Phase 4: Scan filesystem with fls  (active + deleted files)",
            "Phase 5: Extract (icat), validate, extract metadata",
            "Phase 6: Save JSON report + text summary",
        ]},
        {"output_structure": [
            "active/    – active files with original directory tree",
            "deleted/   – deleted-but-recoverable files",
            "corrupted/ – partially damaged files",
            "metadata/  – per-file JSON metadata catalogs",
        ]},
        {"forensic_notes": [
            "READ-ONLY: never modifies the forensic image",
            "Requires Step 10 (Filesystem Analysis) to have been run first",
            "Complies with ISO/IEC 27037:2012 and NIST SP 800-86",
        ]},
    ]


def parse_args():
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Forensic filesystem-based photo recovery"
    )

    parser.add_argument("case_id",        help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--force",        action="store_true")
    parser.add_argument("-j", "--json",   action="store_true")
    parser.add_argument("-q", "--quiet",  action="store_true")
    parser.add_argument("--version",      action='version',
                        version=f'{SCRIPTNAME} {__version__}')

    # Platform integration
    parser.add_argument("--socket-address", type=str, default=None)
    parser.add_argument("--socket-port",    type=str, default=None)
    parser.add_argument("--process-ident",  type=str, default=None)

    if len(sys.argv) == 1 or "-h" in sys.argv or "--help" in sys.argv:
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()

    if args.json:
        args.quiet = True

    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main():
    """Entry point."""
    global SCRIPTNAME
    SCRIPTNAME = "ptfilesystemrecovery"

    try:
        args = parse_args()
        tool = PtFilesystemRecovery(args)
        tool.run()
        tool.save_report()

        # Exit code based on recovery outcome
        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("validImages", 0) > 0 else 1

    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    sys.exit(main())
