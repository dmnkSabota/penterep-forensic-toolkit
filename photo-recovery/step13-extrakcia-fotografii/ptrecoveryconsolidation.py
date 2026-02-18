#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptrecoveryconsolidation - Forensic recovery consolidation tool

    ptrecoveryconsolidation is free software: you can redistribute it and/or
    modify it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptrecoveryconsolidation is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptrecoveryconsolidation.
    If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import os
import json
import shutil
import hashlib
from collections import defaultdict
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
HASH_CHUNK = 65536   # 64 KB for SHA-256 reads

# All image extensions that will be collected from recovery directories
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.tiff', '.tif', '.heic', '.heif', '.webp',
    '.cr2', '.cr3', '.nef', '.nrw',
    '.arw', '.srf', '.sr2', '.dng',
    '.orf', '.raf', '.rw2', '.pef', '.raw',
}

# Extension → format group key
FORMAT_MAP: Dict[str, str] = {
    'jpg': 'jpg', 'jpeg': 'jpg',
    'png': 'png',
    'tif': 'tiff', 'tiff': 'tiff',
    'gif': 'other', 'bmp': 'other',
    'heic': 'other', 'heif': 'other', 'webp': 'other',
    'cr2': 'raw', 'cr3': 'raw',
    'nef': 'raw', 'nrw': 'raw',
    'arw': 'raw', 'srf': 'raw', 'sr2': 'raw',
    'dng': 'raw', 'orf': 'raw', 'raf': 'raw',
    'rw2': 'raw', 'pef': 'raw', 'raw': 'raw',
}


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtRecoveryConsolidation:
    """
    Forensic recovery consolidation tool - ptlibs compliant.

    Six-phase process:
    1. Detect available recovery sources (Step 12A _recovered/, Step 12B _carved/)
    2. Inventory all image files from all sources with metadata
    3. Calculate SHA-256 hashes and detect cross-source duplicates
       (FS-based files have priority over carved files)
    4. Prepare consolidated directory structure
    5. Copy unique files, organise by source + type, move duplicates to audit folder
    6. Create master catalog JSON and save reports

    Complies with ISO/IEC 27037:2012 and NIST SP 800-86.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Source directories (from Steps 12A and 12B)
        self.fs_recovery_dir = self.output_dir / f"{self.case_id}_recovered"
        self.carving_dir     = self.output_dir / f"{self.case_id}_carved"

        # Output directory tree
        self.consolidated_dir = self.output_dir / f"{self.case_id}_consolidated"
        self.fs_based_out     = self.consolidated_dir / "fs_based"
        self.carved_out       = self.consolidated_dir / "carved"
        self.duplicates_out   = self.consolidated_dir / "duplicates"

        # Counters
        self._total_discovered  = 0
        self._fs_files          = 0
        self._carved_files      = 0
        self._duplicates        = 0
        self._final_unique      = 0
        self._total_size        = 0
        self._by_format: Dict[str, int] = {}
        self._by_source: Dict[str, int] = {}

        # Per-file tracking
        self._hash_db: Dict[str, Dict] = {}         # sha256 → file_info dict
        self._organised: List[Dict]    = []

        # Top-level JSON properties
        self.ptjsonlib.add_properties({
            "caseId":              self.case_id,
            "outputDirectory":     str(self.output_dir),
            "timestamp":           datetime.now(timezone.utc).isoformat(),
            "scriptVersion":       __version__,
            "sourcesFound":        [],
            "totalDiscovered":     0,
            "fsBasedFiles":        0,
            "carvedFiles":         0,
            "duplicatesDetected":  0,
            "finalUniqueFiles":    0,
            "totalSizeBytes":      0,
            "totalSizeMb":         0.0,
            "byFormat":            {},
            "bySource":            {},
            "consolidatedDir":     str(self.consolidated_dir),
            "dryRun":              self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------------------

    def _sha256(self, filepath: Path) -> Optional[str]:
        """Return hex SHA-256 digest, or None on read error."""
        h = hashlib.sha256()
        try:
            with open(filepath, "rb") as fh:
                for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    def _scan_dir(self, directory: Path, source_label: str) -> List[Dict[str, Any]]:
        """
        Recursively collect image files from a directory.

        Args:
            directory:    Root directory to scan
            source_label: 'fs_based' or 'carved'

        Returns:
            List of file info dicts (path, source, size, ext)
        """
        files = []
        for item in directory.rglob('*'):
            if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
                files.append({
                    "path":         item,
                    "source":       source_label,
                    "size":         size,
                    "ext":          item.suffix.lstrip('.').lower(),
                    "relativePath": str(item.relative_to(directory)),
                })
        return files

    # -------------------------------------------------------------------------
    # PHASE 1 – DETECT SOURCES
    # -------------------------------------------------------------------------

    def detect_sources(self) -> List[str]:
        """
        Discover which recovery outputs are available.

        Looks for:
          - {case_id}_recovered/active/  or  /deleted/   → Step 12A present
          - {case_id}_carved/organized/                  → Step 12B present

        Returns:
            List of source keys present ('fs_based', 'carved'), empty = failure
        """
        ptprint("\n[STEP 1/6] Detecting Recovery Sources",
                "TITLE", condition=not self.args.json)

        sources: List[str] = []

        # Step 12A
        if self.fs_recovery_dir.exists():
            if ((self.fs_recovery_dir / "active").exists() or
                    (self.fs_recovery_dir / "deleted").exists()):
                sources.append("fs_based")
                ptprint(f"✓ Step 12A (FS-based): {self.fs_recovery_dir.name}",
                        "OK", condition=not self.args.json)

        # Step 12B
        if self.carving_dir.exists():
            if (self.carving_dir / "organized").exists():
                sources.append("carved")
                ptprint(f"✓ Step 12B (File carving): {self.carving_dir.name}",
                        "OK", condition=not self.args.json)

        if not sources:
            ptprint("✗ No recovery sources found!",
                    "ERROR", condition=not self.args.json)
            ptprint("  Run Step 12A and/or Step 12B first.",
                    "ERROR", condition=not self.args.json)

        ptprint(f"  Sources available: {len(sources)}",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "sourceDetection",
            properties={"success": len(sources) > 0, "sources": sources}
        ))
        return sources

    # -------------------------------------------------------------------------
    # PHASE 2 – INVENTORY
    # -------------------------------------------------------------------------

    def inventory_sources(self, sources: List[str]) -> List[Dict[str, Any]]:
        """
        Scan all available source directories and collect every image file.

        Args:
            sources: List of source keys (subset of ['fs_based', 'carved'])

        Returns:
            Combined list of file info dicts from all sources
        """
        ptprint("\n[STEP 2/6] Inventorying All Sources",
                "TITLE", condition=not self.args.json)

        all_files: List[Dict] = []

        if "fs_based" in sources:
            for sub in ["active", "deleted"]:
                d = self.fs_recovery_dir / sub
                if d.exists():
                    batch = self._scan_dir(d, "fs_based")
                    all_files.extend(batch)
                    ptprint(f"  FS-based/{sub}/: {len(batch)} image files",
                            "INFO", condition=not self.args.json)

        if "carved" in sources:
            organized = self.carving_dir / "organized"
            if organized.exists():
                batch = self._scan_dir(organized, "carved")
                all_files.extend(batch)
                ptprint(f"  Carved/organized/: {len(batch)} image files",
                        "INFO", condition=not self.args.json)

        self._fs_files     = sum(1 for f in all_files if f["source"] == "fs_based")
        self._carved_files = sum(1 for f in all_files if f["source"] == "carved")
        self._total_discovered = len(all_files)

        ptprint(f"✓ Total: {self._total_discovered}  "
                f"(fs_based={self._fs_files}, carved={self._carved_files})",
                "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "inventory",
            properties={
                "totalDiscovered": self._total_discovered,
                "fsBasedFiles":    self._fs_files,
                "carvedFiles":     self._carved_files,
            }
        ))
        return all_files

    # -------------------------------------------------------------------------
    # PHASE 3 – HASH + DEDUP
    # -------------------------------------------------------------------------

    def hash_and_deduplicate(self, all_files: List[Dict]) \
            -> Tuple[List[Dict], List[Dict]]:
        """
        Calculate SHA-256 for every file and remove duplicates.

        Priority rule: if the same hash appears in both fs_based and carved,
        the fs_based copy is kept (preserves original filenames/metadata).

        Args:
            all_files: Full inventory from Phase 2

        Returns:
            (unique_files, duplicates)
        """
        ptprint("\n[STEP 3/6] Hashing and Deduplicating",
                "TITLE", condition=not self.args.json)

        total = len(all_files)
        unique: List[Dict]  = []
        dupes:  List[Dict]  = []

        for idx, fi in enumerate(all_files, 1):
            if idx % 50 == 0 or idx == total:
                pct = idx * 100 // total
                ptprint(f"  Progress: {idx}/{total} ({pct}%)",
                        "INFO", condition=not self.args.json)

            if self.dry_run:
                digest = f"dry-run-{idx:08d}"
            else:
                digest = self._sha256(fi["path"])
                if digest is None:
                    ptprint(f"  ⚠ Could not hash {fi['path'].name}",
                            "WARNING", condition=not self.args.json)
                    continue

            fi["hash"] = digest

            if digest in self._hash_db:
                existing = self._hash_db[digest]

                # FS-based wins over carved
                if fi["source"] == "fs_based" and existing["source"] == "carved":
                    # Replace the carved copy with the fs_based copy
                    dupes.append(existing)
                    unique = [u for u in unique if u.get("hash") != digest]
                    self._hash_db[digest] = fi
                    unique.append(fi)
                else:
                    dupes.append(fi)

                self._duplicates += 1
            else:
                self._hash_db[digest] = fi
                unique.append(fi)

        dup_rate = self._duplicates / total * 100 if total else 0

        ptprint(f"✓ Unique files:  {len(unique)}",
                "OK", condition=not self.args.json)
        ptprint(f"  Duplicates:    {self._duplicates}  ({dup_rate:.1f}%)",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "deduplication",
            properties={
                "totalInput":     total,
                "uniqueFiles":    len(unique),
                "duplicates":     self._duplicates,
                "duplicationRate": round(dup_rate, 1),
            }
        ))
        return unique, dupes

    # -------------------------------------------------------------------------
    # PHASE 4 – PREPARE DIRECTORIES
    # -------------------------------------------------------------------------

    def prepare_directories(self) -> bool:
        """
        Create consolidated output directory structure.

        Structure:
            {case_id}_consolidated/
                fs_based/   jpg/  png/  tiff/  raw/  other/
                carved/     jpg/  png/  tiff/  raw/  other/
                duplicates/

        Returns:
            bool: True always
        """
        ptprint("\n[STEP 4/6] Preparing Consolidated Directories",
                "TITLE", condition=not self.args.json)

        type_subs = ["jpg", "png", "tiff", "raw", "other"]

        for base in [self.fs_based_out, self.carved_out]:
            for sub in type_subs:
                d = base / sub
                if not self.dry_run:
                    d.mkdir(parents=True, exist_ok=True)
                ptprint(f"  {d.relative_to(self.consolidated_dir)}/",
                        "INFO", condition=not self.args.json)

        if not self.dry_run:
            self.duplicates_out.mkdir(parents=True, exist_ok=True)

        ptprint("✓ Directories ready", "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "directoriesPrep",
            properties={
                "success":         True,
                "consolidatedDir": str(self.consolidated_dir),
                "fsBasedDir":      str(self.fs_based_out),
                "carvedDir":       str(self.carved_out),
                "duplicatesDir":   str(self.duplicates_out),
            }
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 5 – COPY + ORGANISE
    # -------------------------------------------------------------------------

    def copy_and_organise(self, unique: List[Dict],
                          dupes: List[Dict]) -> List[Dict]:
        """
        Copy unique files into the consolidated tree and move duplicates
        to the audit folder.

        Naming rules:
          - fs_based files: keep original filename (collision-safe suffix added)
          - carved  files: systematic name {case_id}_{type}_{seq:06d}.{ext}

        Args:
            unique: Unique file list from Phase 3
            dupes:  Duplicate list (moved to duplicates/ for audit)

        Returns:
            List of dicts describing every organised file
        """
        ptprint("\n[STEP 5/6] Copying and Organising Files",
                "TITLE", condition=not self.args.json)

        format_counters: Dict[str, Dict[str, int]] = {
            "fs_based": defaultdict(int),
            "carved":   defaultdict(int),
        }
        organised: List[Dict] = []

        for fi in unique:
            source    = fi["source"]
            ext       = fi["ext"]
            fmt_group = FORMAT_MAP.get(ext, "other")
            base_out  = self.fs_based_out if source == "fs_based" else self.carved_out
            type_dir  = base_out / fmt_group

            # Determine target filename
            if source == "fs_based":
                new_name = fi["path"].name
                dest     = type_dir / new_name
                # Collision guard
                if not self.dry_run and dest.exists():
                    format_counters[source][fmt_group] += 1
                    stem    = dest.stem
                    new_name = f"{stem}_{format_counters[source][fmt_group]}{dest.suffix}"
                    dest    = type_dir / new_name
            else:
                format_counters[source][fmt_group] += 1
                seq      = format_counters[source][fmt_group]
                new_name = f"{self.case_id}_{fmt_group}_{seq:06d}.{ext}"
                dest     = type_dir / new_name

            # Copy
            if not self.dry_run:
                shutil.copy2(str(fi["path"]), str(dest))

            # Accumulate stats
            self._by_format[fmt_group] = self._by_format.get(fmt_group, 0) + 1
            self._by_source[source]    = self._by_source.get(source, 0) + 1
            self._total_size          += fi["size"]

            fi["consolidatedName"] = new_name
            fi["consolidatedPath"] = str(dest.relative_to(self.consolidated_dir)) \
                                     if not self.dry_run else new_name
            organised.append(fi)

        # Move duplicates to audit folder
        ptprint(f"  Moving {len(dupes)} duplicates to audit folder …",
                "INFO", condition=not self.args.json)

        for dup in dupes:
            dest = self.duplicates_out / dup["path"].name
            if not self.dry_run:
                if dest.exists():
                    h8 = dup.get("hash", "00000000")[:8]
                    dest = self.duplicates_out / \
                           f"{dest.stem}_{h8}{dest.suffix}"
                shutil.copy2(str(dup["path"]), str(dest))

        self._final_unique = len(organised)

        ptprint(f"✓ {self._final_unique} files organised",
                "OK", condition=not self.args.json)

        self._organised = organised
        return organised

    # -------------------------------------------------------------------------
    # PHASE 6 – MASTER CATALOG + REPORTS
    # -------------------------------------------------------------------------

    def create_master_catalog(self, organised: List[Dict]) -> Dict:
        """
        Build and save master_catalog.json inside the consolidated directory.

        The catalog contains a complete file inventory (id, filename, hash,
        size, format, source, path) plus summary statistics.

        Returns:
            Catalog dict
        """
        ptprint("\n[STEP 6/6] Creating Master Catalog",
                "TITLE", condition=not self.args.json)

        size_mb = round(self._total_size / (1024 * 1024), 2)

        catalog = {
            "caseId":    self.case_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "totalFiles":       self._final_unique,
                "totalSizeBytes":   self._total_size,
                "totalSizeMb":      size_mb,
                "sourcesUsed":      list({f["source"] for f in organised}),
                "fsBasedFiles":     self._fs_files,
                "carvedFiles":      self._carved_files,
                "duplicatesRemoved": self._duplicates,
                "finalUniqueFiles": self._final_unique,
            },
            "byFormat": self._by_format,
            "bySource": self._by_source,
            "files":    [],
        }

        for idx, fi in enumerate(organised, 1):
            catalog["files"].append({
                "id":               idx,
                "filename":         fi["consolidatedName"],
                "originalFilename": fi["path"].name,
                "path":             fi["consolidatedPath"],
                "sizeBytes":        fi["size"],
                "sizeMb":           round(fi["size"] / (1024 * 1024), 4),
                "hashSha256":       fi.get("hash", ""),
                "format":           fi["ext"],
                "formatGroup":      FORMAT_MAP.get(fi["ext"], "other"),
                "recoveryMethod":   fi["source"],
                "originalPath":     str(fi["path"]),
            })

        if not self.dry_run:
            self.consolidated_dir.mkdir(parents=True, exist_ok=True)
            cat_file = self.consolidated_dir / "master_catalog.json"
            with open(cat_file, "w", encoding="utf-8") as fh:
                json.dump(catalog, fh, indent=2, ensure_ascii=False, default=str)
            ptprint(f"✓ master_catalog.json  ({len(catalog['files'])} entries)",
                    "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "masterCatalog",
            properties={
                "totalEntries":  len(catalog["files"]),
                "totalSizeMb":   size_mb,
                "byFormat":      self._by_format,
                "bySource":      self._by_source,
            }
        ))
        return catalog

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full six-phase consolidation pipeline."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("RECOVERY CONSOLIDATION", "TITLE", condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        # Phase 1 – Detect sources
        sources = self.detect_sources()
        if not sources:
            self.ptjsonlib.set_status("finished")
            return

        # Phase 2 – Inventory
        all_files = self.inventory_sources(sources)
        if not all_files:
            ptprint("✗ No image files found in recovery sources",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.set_status("finished")
            return

        # Phase 3 – Hash + dedup
        unique, dupes = self.hash_and_deduplicate(all_files)

        # Phase 4 – Directories
        self.prepare_directories()

        # Phase 5 – Copy + organise
        organised = self.copy_and_organise(unique, dupes)

        # Phase 6 – Master catalog
        self.create_master_catalog(organised)

        # Update top-level properties
        size_mb = round(self._total_size / (1024 * 1024), 2)
        self.ptjsonlib.add_properties({
            "sourcesFound":       list({f["source"] for f in organised}),
            "totalDiscovered":    self._total_discovered,
            "fsBasedFiles":       self._fs_files,
            "carvedFiles":        self._carved_files,
            "duplicatesDetected": self._duplicates,
            "finalUniqueFiles":   self._final_unique,
            "totalSizeBytes":     self._total_size,
            "totalSizeMb":        size_mb,
            "byFormat":           self._by_format,
            "bySource":           self._by_source,
        })

        # Console summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("CONSOLIDATION COMPLETED", "OK", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Total discovered:  {self._total_discovered}",
                "INFO", condition=not self.args.json)
        ptprint(f"  FS-based:        {self._fs_files}",
                "INFO", condition=not self.args.json)
        ptprint(f"  Carved:          {self._carved_files}",
                "INFO", condition=not self.args.json)
        ptprint(f"Duplicates removed: {self._duplicates}",
                "INFO", condition=not self.args.json)
        ptprint(f"Final unique files: {self._final_unique}",
                "OK",   condition=not self.args.json)
        ptprint(f"Total size:        {size_mb:.1f} MB",
                "INFO", condition=not self.args.json)
        for fmt, cnt in sorted(self._by_format.items()):
            ptprint(f"  {fmt.upper():6s}: {cnt}",
                    "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint("\nNext step: Step 14 (EXIF Analysis / Validation)",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        """
        Save JSON report and human-readable text summary.

        --json mode: prints JSON to stdout only.
        Otherwise writes:
          - {case_id}_consolidation_report.json
          - {case_id}_consolidated/CONSOLIDATION_REPORT.txt

        Returns:
            Path to JSON file, or None in --json mode
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        json_file = self.output_dir / f"{self.case_id}_consolidation_report.json"

        report = {
            "result":        json.loads(self.ptjsonlib.get_result_json()),
            "consolidatedFiles": [
                {
                    "filename":         fi.get("consolidatedName"),
                    "originalFilename": fi["path"].name,
                    "consolidatedPath": fi.get("consolidatedPath"),
                    "source":           fi["source"],
                    "sizeBytes":        fi["size"],
                    "hashSha256":       fi.get("hash", ""),
                    "format":           fi["ext"],
                }
                for fi in self._organised
            ],
        }

        with open(json_file, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False, default=str)

        ptprint(f"✓ JSON report saved: {json_file}",
                "OK", condition=not self.args.json)

        # Text summary
        self.consolidated_dir.mkdir(parents=True, exist_ok=True)
        txt_file = self.consolidated_dir / "CONSOLIDATION_REPORT.txt"
        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]

        with open(txt_file, "w", encoding="utf-8") as fh:
            fh.write("=" * 70 + "\n")
            fh.write("RECOVERY CONSOLIDATION REPORT\n")
            fh.write("=" * 70 + "\n\n")
            fh.write(f"Case ID:   {self.case_id}\n")
            fh.write(f"Timestamp: {props.get('timestamp','')}\n\n")
            fh.write("SOURCES:\n")
            for src in props.get("sourcesFound", []):
                fh.write(f"  - {src}\n")
            fh.write("\nSTATISTICS:\n")
            fh.write(f"  Total discovered:    {props.get('totalDiscovered',0)}\n")
            fh.write(f"  FS-based files:      {props.get('fsBasedFiles',0)}\n")
            fh.write(f"  Carved files:        {props.get('carvedFiles',0)}\n")
            fh.write(f"  Duplicates removed:  {props.get('duplicatesDetected',0)}\n")
            fh.write(f"  Final unique files:  {props.get('finalUniqueFiles',0)}\n")
            fh.write(f"  Total size:          "
                     f"{props.get('totalSizeMb',0):.1f} MB\n")
            fh.write("\nBY FORMAT:\n")
            for fmt, cnt in sorted(props.get("byFormat", {}).items()):
                fh.write(f"  {fmt.upper():8s}: {cnt}\n")
            fh.write("\nBY SOURCE:\n")
            for src, cnt in sorted(props.get("bySource", {}).items()):
                fh.write(f"  {src}: {cnt}\n")

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
            "Forensic recovery consolidation tool – ptlibs compliant",
            "Merges outputs from Step 12A (FS-based) and/or Step 12B (file carving)",
            "into a single deduplicated dataset with a master catalog",
        ]},
        {"usage": ["ptrecoveryconsolidation <case-id> [options]"]},
        {"usage_example": [
            "ptrecoveryconsolidation PHOTO-2025-001",
            "ptrecoveryconsolidation CASE-042 --json",
            "ptrecoveryconsolidation TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",    "",              "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<dir>",  f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",              "Simulate without copying files"],
            ["-j",  "--json",       "",      "JSON output for platform integration"],
            ["-q",  "--quiet",      "",      "Suppress progress output"],
            ["-h",  "--help",       "",      "Show this help message and exit"],
            ["--version",  "",              "Show version and exit"],
        ]},
        {"consolidation_phases": [
            "Phase 1: Detect available sources (12A _recovered/, 12B _carved/)",
            "Phase 2: Inventory all image files from all sources",
            "Phase 3: SHA-256 hash + cross-source duplicate detection",
            "         (FS-based files have priority over carved files)",
            "Phase 4: Prepare consolidated directory structure",
            "Phase 5: Copy unique files, move duplicates to audit folder",
            "Phase 6: Build master_catalog.json, save reports",
        ]},
        {"output_structure": [
            "fs_based/  jpg/ png/ tiff/ raw/ other/   (original filenames)",
            "carved/    jpg/ png/ tiff/ raw/ other/   (systematic names)",
            "duplicates/                               (audit copies)",
            "master_catalog.json",
            "CONSOLIDATION_REPORT.txt",
        ]},
        {"forensic_notes": [
            "READ-ONLY on source directories (copies, never moves originals)",
            "FS-based files keep original names; carved files get CASEID_type_NNNNNN.ext",
            "SHA-256 hash of every file recorded in master catalog",
            "Complies with ISO/IEC 27037:2012 and NIST SP 800-86",
        ]},
    ]


def parse_args():
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Forensic recovery consolidation"
    )

    parser.add_argument("case_id",        help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run",      action="store_true")
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
    SCRIPTNAME = "ptrecoveryconsolidation"

    try:
        args = parse_args()
        tool = PtRecoveryConsolidation(args)
        tool.run()
        tool.save_report()

        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("finalUniqueFiles", 0) > 0 else 1

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
