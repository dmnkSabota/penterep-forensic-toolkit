#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-CONSOLIDATE: Konsolidácia výstupov z recovery metód
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript konsoliduje výstupy z krokov 12A (FS-based) a/alebo 12B (file carving)
do jedného organizovaného datasetu s odstránením duplikátov.
"""

import subprocess
import json
import sys
import os
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False
    print("WARNING: ptlibs not found, using fallback output")


class RecoveryConsolidation:
    """
    Konsolidácia výsledkov z rôznych recovery metód.
    
    Proces:
    1. Detect available recovery sources (12A, 12B, or both)
    2. Inventory all recovered files
    3. Calculate SHA-256 hashes
    4. Detect duplicates (FS-based has priority)
    5. Copy unique files to consolidated directory
    6. Organize by source and type
    7. Create master catalog
    8. Generate statistics
    """
    
    # Podporované obrazové formáty
    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
        '.heic', '.heif', '.webp',
        '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2',
        '.dng', '.orf', '.raf', '.rw2', '.pef', '.raw'
    }
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Zdrojové adresáre
        self.fs_recovery_dir = self.output_dir / f"{case_id}_recovered"
        self.carving_dir = self.output_dir / f"{case_id}_carved"
        
        # Výstupný adresár
        self.consolidated_dir = self.output_dir / f"{case_id}_consolidated"
        self.fs_based_dir = self.consolidated_dir / "fs_based"
        self.carved_dir = self.consolidated_dir / "carved"
        self.duplicates_dir = self.consolidated_dir / "duplicates"
        
        # Štatistiky
        self.stats = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sources_found": [],
            "total_files_discovered": 0,
            "fs_based_files": 0,
            "carved_files": 0,
            "duplicates_detected": 0,
            "final_unique_files": 0,
            "by_format": {},
            "by_source": {},
            "total_size_bytes": 0,
            "success": False
        }
        
        # File tracking
        self.all_files = []
        self.unique_files = []
        self.duplicates = []
        self.hash_database = {}
    
    def _print(self, message, level="INFO"):
        """Helper pre výpis s farbami"""
        if PTLIBS_AVAILABLE:
            ptprinthelper.ptprint(message, level)
        else:
            prefix = {
                "TITLE": "[*]",
                "OK": "[✓]",
                "ERROR": "[✗]",
                "WARNING": "[!]",
                "INFO": "[i]"
            }.get(level, "")
            print(f"{prefix} {message}")
    
    def detect_sources(self):
        """
        Detekcia dostupných zdrojov obnovy.
        """
        self._print("\nDetecting recovery sources...", "TITLE")
        
        sources_found = []
        
        # Kontrola FS-based recovery (Step 12A)
        if self.fs_recovery_dir.exists():
            # Hľadáme active/ alebo deleted/ adresáre
            active_dir = self.fs_recovery_dir / "active"
            deleted_dir = self.fs_recovery_dir / "deleted"
            
            if active_dir.exists() or deleted_dir.exists():
                sources_found.append("fs_based")
                self.stats["sources_found"].append("filesystem_recovery")
                self._print("Found: Step 12A (Filesystem-based recovery)", "OK")
        
        # Kontrola file carving (Step 12B)
        if self.carving_dir.exists():
            # Hľadáme organized/ adresár
            organized_dir = self.carving_dir / "organized"
            
            if organized_dir.exists():
                sources_found.append("carved")
                self.stats["sources_found"].append("file_carving")
                self._print("Found: Step 12B (File carving)", "OK")
        
        if not sources_found:
            self._print("ERROR: No recovery sources found!", "ERROR")
            self._print("Please run Step 12A and/or Step 12B first!", "ERROR")
            return False
        
        self._print(f"Total sources: {len(sources_found)}", "INFO")
        
        return sources_found
    
    def calculate_hash(self, filepath):
        """Vypočíta SHA-256 hash súboru"""
        sha256_hash = hashlib.sha256()
        
        try:
            with open(filepath, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            
            return sha256_hash.hexdigest()
        except Exception as e:
            self._print(f"Hash calculation error for {filepath}: {str(e)}", "WARNING")
            return None
    
    def scan_directory_recursive(self, directory, source_name):
        """
        Rekurzívne skenuje adresár a zbiera obrazové súbory.
        
        Args:
            directory: Path to directory
            source_name: 'fs_based' or 'carved'
        
        Returns:
            List of file info dictionaries
        """
        files = []
        
        for item in directory.rglob('*'):
            if item.is_file():
                ext = item.suffix.lower()
                
                if ext in self.IMAGE_EXTENSIONS:
                    files.append({
                        "path": item,
                        "source": source_name,
                        "size": item.stat().st_size,
                        "extension": ext.lstrip('.'),
                        "relative_path": str(item.relative_to(directory))
                    })
        
        return files
    
    def inventory_sources(self, sources):
        """
        FÁZA 1-2: Inventarizácia všetkých súborov zo všetkých zdrojov.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("INVENTORY PHASE", "TITLE")
        self._print("="*70, "TITLE")
        
        all_files = []
        
        # FS-based recovery
        if "fs_based" in sources:
            self._print("\nScanning FS-based recovery...", "INFO")
            
            # Active files
            active_dir = self.fs_recovery_dir / "active"
            if active_dir.exists():
                active_files = self.scan_directory_recursive(active_dir, "fs_based")
                all_files.extend(active_files)
                self._print(f"  Active files: {len(active_files)}", "INFO")
            
            # Deleted files
            deleted_dir = self.fs_recovery_dir / "deleted"
            if deleted_dir.exists():
                deleted_files = self.scan_directory_recursive(deleted_dir, "fs_based")
                all_files.extend(deleted_files)
                self._print(f"  Deleted files: {len(deleted_files)}", "INFO")
            
            self.stats["fs_based_files"] = len([f for f in all_files if f["source"] == "fs_based"])
        
        # File carving
        if "carved" in sources:
            self._print("\nScanning file carving...", "INFO")
            
            organized_dir = self.carving_dir / "organized"
            if organized_dir.exists():
                carved_files = self.scan_directory_recursive(organized_dir, "carved")
                all_files.extend(carved_files)
                self._print(f"  Carved files: {len(carved_files)}", "INFO")
            
            self.stats["carved_files"] = len([f for f in all_files if f["source"] == "carved"])
        
        self.stats["total_files_discovered"] = len(all_files)
        
        self._print(f"\nTotal files discovered: {len(all_files)}", "OK")
        self._print(f"  FS-based: {self.stats['fs_based_files']}", "INFO")
        self._print(f"  Carved: {self.stats['carved_files']}", "INFO")
        
        return all_files
    
    def calculate_hashes_and_detect_duplicates(self, files):
        """
        FÁZA 3: Výpočet hashov a detekcia duplikátov.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("HASH CALCULATION AND DEDUPLICATION", "TITLE")
        self._print("="*70, "TITLE")
        
        self._print(f"\nCalculating hashes for {len(files)} files...", "INFO")
        
        unique_files = []
        duplicates = []
        
        total = len(files)
        
        for idx, file_info in enumerate(files, 1):
            if idx % 50 == 0 or idx == total:
                self._print(f"Progress: {idx}/{total} ({idx*100//total}%)", "INFO")
            
            # Výpočet hashu
            file_hash = self.calculate_hash(file_info["path"])
            
            if not file_hash:
                continue
            
            file_info["hash"] = file_hash
            
            # Kontrola duplikátu
            if file_hash in self.hash_database:
                # Duplikát nájdený
                original = self.hash_database[file_hash]
                
                # FS-based má prioritu
                if file_info["source"] == "fs_based" and original["source"] == "carved":
                    # Vymeň - fs_based má prednosť
                    duplicates.append(original)
                    self.hash_database[file_hash] = file_info
                    
                    # Odstráň starý z unique_files
                    unique_files = [f for f in unique_files if f["hash"] != file_hash]
                    unique_files.append(file_info)
                else:
                    # Nechaj pôvodný
                    duplicates.append(file_info)
                
                self.stats["duplicates_detected"] += 1
                
            else:
                # Unikátny súbor
                self.hash_database[file_hash] = file_info
                unique_files.append(file_info)
        
        self.stats["final_unique_files"] = len(unique_files)
        
        self._print(f"\nHash calculation completed", "OK")
        self._print(f"Unique files: {len(unique_files)}", "OK")
        self._print(f"Duplicates detected: {len(duplicates)}", "INFO")
        
        if len(duplicates) > 0:
            dup_rate = (len(duplicates) / total) * 100
            self._print(f"Duplication rate: {dup_rate:.1f}%", "INFO")
        
        return unique_files, duplicates
    
    def prepare_directories(self):
        """Vytvorenie výstupných adresárov"""
        self._print("\nPreparing consolidated directories...", "INFO")
        
        for directory in [self.fs_based_dir, self.carved_dir, self.duplicates_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Type-specific subdirectories
        for base_dir in [self.fs_based_dir, self.carved_dir]:
            for fmt in ['jpg', 'png', 'tiff', 'raw', 'other']:
                (base_dir / fmt).mkdir(exist_ok=True)
        
        return True
    
    def copy_and_organize(self, unique_files, duplicates):
        """
        FÁZA 4-5: Kopírovanie a organizácia súborov.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("COPYING AND ORGANIZING FILES", "TITLE")
        self._print("="*70, "TITLE")
        
        # Počítadlá pre renaming
        format_counters = defaultdict(lambda: defaultdict(int))
        
        self._print(f"\nCopying {len(unique_files)} unique files...", "INFO")
        
        organized_files = []
        
        for file_info in unique_files:
            source = file_info["source"]
            ext = file_info["extension"]
            
            # Určenie target base directory
            if source == "fs_based":
                target_base = self.fs_based_dir
            else:
                target_base = self.carved_dir
            
            # Určenie type subdirectory
            if ext in ['jpg', 'jpeg']:
                type_dir = target_base / 'jpg'
                format_key = 'jpg'
            elif ext == 'png':
                type_dir = target_base / 'png'
                format_key = 'png'
            elif ext in ['tif', 'tiff']:
                type_dir = target_base / 'tiff'
                format_key = 'tiff'
            elif ext in ['cr2', 'cr3', 'nef', 'nrw', 'arw', 'srf', 'sr2', 'dng', 'orf', 'raf', 'rw2', 'pef', 'raw']:
                type_dir = target_base / 'raw'
                format_key = 'raw'
            else:
                type_dir = target_base / 'other'
                format_key = 'other'
            
            # Určenie názvu súboru
            original_name = file_info["path"].name
            
            if source == "fs_based":
                # Zachovaj pôvodný názov
                target_path = type_dir / original_name
                
                # Handle collisions (different files with same name)
                if target_path.exists():
                    format_counters[source][format_key] += 1
                    seq = format_counters[source][format_key]
                    stem = target_path.stem
                    target_path = type_dir / f"{stem}_{seq}{target_path.suffix}"
            else:
                # Systematický názov pre carved
                format_counters[source][format_key] += 1
                seq = format_counters[source][format_key]
                target_path = type_dir / f"{self.case_id}_{format_key}_{seq:06d}.{ext}"
            
            # Kopírovanie
            try:
                shutil.copy2(file_info["path"], target_path)
                
                # Update file info
                file_info["consolidated_path"] = str(target_path.relative_to(self.consolidated_dir))
                file_info["consolidated_name"] = target_path.name
                
                organized_files.append(file_info)
                
                # Štatistiky
                self.stats["by_format"][format_key] = self.stats["by_format"].get(format_key, 0) + 1
                self.stats["by_source"][source] = self.stats["by_source"].get(source, 0) + 1
                self.stats["total_size_bytes"] += file_info["size"]
                
            except Exception as e:
                self._print(f"Error copying {file_info['path']}: {str(e)}", "WARNING")
        
        # Kopírovanie duplikátov do duplicates/
        self._print(f"\nMoving {len(duplicates)} duplicates to audit folder...", "INFO")
        
        for dup_info in duplicates:
            dup_path = self.duplicates_dir / dup_info["path"].name
            
            # Handle name collisions
            if dup_path.exists():
                stem = dup_path.stem
                dup_path = self.duplicates_dir / f"{stem}_{dup_info['hash'][:8]}{dup_path.suffix}"
            
            try:
                shutil.copy2(dup_info["path"], dup_path)
            except Exception as e:
                self._print(f"Error moving duplicate: {str(e)}", "WARNING")
        
        self._print(f"\nOrganization completed", "OK")
        self._print(f"Files organized: {len(organized_files)}", "OK")
        
        return organized_files
    
    def create_master_catalog(self, organized_files):
        """
        FÁZA 6: Vytvorenie master katalógu.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("CREATING MASTER CATALOG", "TITLE")
        self._print("="*70, "TITLE")
        
        catalog = {
            "case_id": self.case_id,
            "timestamp": self.stats["timestamp"],
            "summary": {
                "total_files": len(organized_files),
                "total_size_bytes": self.stats["total_size_bytes"],
                "total_size_mb": round(self.stats["total_size_bytes"] / (1024 * 1024), 2),
                "sources_used": self.stats["sources_found"],
                "fs_based_files": self.stats["fs_based_files"],
                "carved_files": self.stats["carved_files"],
                "duplicates_removed": self.stats["duplicates_detected"],
                "final_unique_files": self.stats["final_unique_files"]
            },
            "by_format": self.stats["by_format"],
            "by_source": self.stats["by_source"],
            "files": []
        }
        
        # Vytvorenie file entries
        for idx, file_info in enumerate(organized_files, 1):
            entry = {
                "id": idx,
                "filename": file_info["consolidated_name"],
                "original_filename": file_info["path"].name,
                "path": file_info["consolidated_path"],
                "size_bytes": file_info["size"],
                "size_mb": round(file_info["size"] / (1024 * 1024), 2),
                "hash_sha256": file_info["hash"],
                "format": file_info["extension"],
                "recovery_method": file_info["source"],
                "original_path": str(file_info["path"])
            }
            
            catalog["files"].append(entry)
        
        # Uloženie katalógu
        catalog_file = self.consolidated_dir / "master_catalog.json"
        
        with open(catalog_file, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        
        self._print(f"Master catalog created: {catalog_file.name}", "OK")
        self._print(f"Total entries: {len(catalog['files'])}", "INFO")
        
        return catalog
    
    def run_consolidation(self):
        """Hlavná funkcia - spustí celý konsolidačný proces"""
        
        self._print("="*70, "TITLE")
        self._print("RECOVERY CONSOLIDATION", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Detekcia zdrojov
        sources = self.detect_sources()
        
        if not sources:
            self.stats["success"] = False
            return self.stats
        
        # 2. Inventarizácia
        all_files = self.inventory_sources(sources)
        
        if not all_files:
            self._print("No files found in recovery sources", "ERROR")
            self.stats["success"] = False
            return self.stats
        
        # 3. Hashe a duplikáty
        unique_files, duplicates = self.calculate_hashes_and_detect_duplicates(all_files)
        
        # 4. Príprava adresárov
        self.prepare_directories()
        
        # 5. Kopírovanie a organizácia
        organized_files = self.copy_and_organize(unique_files, duplicates)
        
        # 6. Master katalóg
        catalog = self.create_master_catalog(organized_files)
        
        # 7. Finalizácia
        self._print("\n" + "="*70, "TITLE")
        self._print("CONSOLIDATION COMPLETED", "OK")
        self._print("="*70, "TITLE")
        
        self._print(f"Total discovered: {self.stats['total_files_discovered']}", "INFO")
        self._print(f"Duplicates removed: {self.stats['duplicates_detected']}", "INFO")
        self._print(f"Final unique files: {self.stats['final_unique_files']}", "OK")
        self._print(f"Total size: {self.stats['total_size_bytes'] / (1024*1024*1024):.2f} GB", "INFO")
        
        self._print("\nBy format:", "INFO")
        for fmt, count in sorted(self.stats['by_format'].items()):
            self._print(f"  {fmt.upper()}: {count}", "INFO")
        
        self._print("="*70 + "\n", "TITLE")
        
        self.stats["success"] = True
        
        return self.stats
    
    def save_report(self):
        """Uloženie štatistického reportu"""
        
        report_file = self.output_dir / f"{self.case_id}_consolidation_report.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)
        
        self._print(f"Consolidation report saved: {report_file}", "OK")
        
        # Textový report
        text_report = self.consolidated_dir / "CONSOLIDATION_REPORT.txt"
        
        with open(text_report, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("RECOVERY CONSOLIDATION REPORT\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"Case ID: {self.case_id}\n")
            f.write(f"Timestamp: {self.stats['timestamp']}\n\n")
            
            f.write("SOURCES:\n")
            for source in self.stats['sources_found']:
                f.write(f"  - {source}\n")
            f.write("\n")
            
            f.write("STATISTICS:\n")
            f.write(f"  Total files discovered: {self.stats['total_files_discovered']}\n")
            f.write(f"  FS-based files: {self.stats['fs_based_files']}\n")
            f.write(f"  Carved files: {self.stats['carved_files']}\n")
            f.write(f"  Duplicates removed: {self.stats['duplicates_detected']}\n")
            f.write(f"  Final unique files: {self.stats['final_unique_files']}\n\n")
            
            f.write(f"  Total size: {self.stats['total_size_bytes'] / (1024*1024*1024):.2f} GB\n\n")
            
            f.write("BY FORMAT:\n")
            for fmt, count in sorted(self.stats['by_format'].items()):
                f.write(f"  {fmt.upper()}: {count}\n")
            f.write("\n")
            
            f.write("BY SOURCE:\n")
            for source, count in sorted(self.stats['by_source'].items()):
                f.write(f"  {source}: {count}\n")
        
        self._print(f"Text report saved: {text_report}", "OK")
        
        return str(report_file)


def main():
    """
    Hlavná funkcia - entry point pre Penterep platformu
    """
    
    print("\n" + "="*70)
    print("FOR-COL-CONSOLIDATE: Recovery Consolidation")
    print("="*70 + "\n")
    
    # Vstupné parametre
    if len(sys.argv) >= 2:
        case_id = sys.argv[1]
    else:
        case_id = input("Case ID (e.g., PHOTO-2025-01-26-001): ").strip()
    
    # Validácia
    if not case_id:
        print("ERROR: Case ID cannot be empty")
        sys.exit(1)
    
    # Spustenie konsolidácie
    consolidation = RecoveryConsolidation(case_id)
    results = consolidation.run_consolidation()
    
    # Uloženie reportu
    if results["success"]:
        report_path = consolidation.save_report()
        print(f"\nConsolidation completed successfully")
        print(f"Final unique files: {results['final_unique_files']}")
        print(f"Duplicates removed: {results['duplicates_detected']}")
        print(f"Output: {consolidation.consolidated_dir}")
        print(f"Next step: Step 14 (EXIF Analysis)")
        sys.exit(0)
    else:
        print("\nConsolidation failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - KEY FEATURES
================================================================================

RECOVERY CONSOLIDATION
- Consolidates outputs from Step 12A (FS-based) and Step 12B (file carving)
- Removes duplicates using SHA-256 hashing
- FS-based files have priority (preserved names)
- Creates unified master catalog

SIX-PHASE PROCESS
1. Detect sources (12A, 12B, or both)
2. Inventory all files from all sources
3. Calculate SHA-256 hashes and detect duplicates
4. Copy unique files to consolidated directory
5. Organize by source (fs_based/, carved/) and type (jpg/, png/, raw/)
6. Create master catalog JSON with all metadata

DEDUPLICATION LOGIC
- FS-based files have priority over carved files
- Same file found by both methods → keep FS-based version
- Duplicates moved to duplicates/ folder for audit
- Typical duplication rate: 15-25% in hybrid approach

OUTPUT STRUCTURE
consolidated/
  ├─ fs_based/
  │  ├─ jpg/          (IMG_0001.JPG - original names)
  │  ├─ png/
  │  ├─ tiff/
  │  └─ raw/
  ├─ carved/
  │  ├─ jpg/          (CASE-001_jpg_000001.jpg - systematic names)
  │  ├─ png/
  │  ├─ tiff/
  │  └─ raw/
  ├─ duplicates/      (removed duplicates for audit)
  └─ master_catalog.json

MASTER CATALOG
- Complete inventory of all unique files
- Metadata: filename, hash, size, format, source, path
- Summary statistics
- By-format and by-source breakdowns
- Ready for Step 14 (EXIF Analysis)

================================================================================
EXAMPLE OUTPUT
================================================================================

======================================================================
RECOVERY CONSOLIDATION
Case ID: PHOTO-2025-01-26-001
======================================================================

Detecting recovery sources...
[✓] Found: Step 12A (Filesystem-based recovery)
[✓] Found: Step 12B (File carving)
[i] Total sources: 2

======================================================================
INVENTORY PHASE
======================================================================

Scanning FS-based recovery...
[i]   Active files: 412
[i]   Deleted files: 75

Scanning file carving...
[i]   Carved files: 314

[✓] Total files discovered: 801
[i]   FS-based: 487
[i]   Carved: 314

======================================================================
HASH CALCULATION AND DEDUPLICATION
======================================================================

Calculating hashes for 801 files...
[i] Progress: 801/801 (100%)

[✓] Hash calculation completed
[✓] Unique files: 692
[i] Duplicates detected: 109
[i] Duplication rate: 13.6%

======================================================================
COPYING AND ORGANIZING FILES
======================================================================

Copying 692 unique files...
Moving 109 duplicates to audit folder...

[✓] Organization completed
[✓] Files organized: 692

======================================================================
CREATING MASTER CATALOG
======================================================================

[✓] Master catalog created: master_catalog.json
[i] Total entries: 692

======================================================================
CONSOLIDATION COMPLETED
======================================================================
[i] Total discovered: 801
[i] Duplicates removed: 109
[✓] Final unique files: 692
[i] Total size: 2.35 GB

By format:
[i]   JPG: 589
[i]   PNG: 78
[i]   RAW: 18
[i]   TIFF: 7
======================================================================

Consolidation completed successfully
Final unique files: 692
Duplicates removed: 109

================================================================================
MASTER CATALOG FORMAT
================================================================================

{
  "case_id": "PHOTO-2025-01-26-001",
  "timestamp": "2025-01-26T22:45:00Z",
  "summary": {
    "total_files": 692,
    "total_size_bytes": 2524971008,
    "total_size_mb": 2407.45,
    "sources_used": ["filesystem_recovery", "file_carving"],
    "fs_based_files": 487,
    "carved_files": 314,
    "duplicates_removed": 109,
    "final_unique_files": 692
  },
  "by_format": {
    "jpg": 589,
    "png": 78,
    "raw": 18,
    "tiff": 7
  },
  "by_source": {
    "fs_based": 487,
    "carved": 205
  },
  "files": [
    {
      "id": 1,
      "filename": "IMG_0001.JPG",
      "original_filename": "IMG_0001.JPG",
      "path": "fs_based/jpg/IMG_0001.JPG",
      "size_bytes": 2458624,
      "size_mb": 2.34,
      "hash_sha256": "a1b2c3d4...",
      "format": "jpg",
      "recovery_method": "fs_based",
      "original_path": "/path/to/recovered/active/DCIM/100CANON/IMG_0001.JPG"
    }
  ]
}

================================================================================
USAGE
================================================================================

INTERACTIVE MODE:
$ python3 step13_consolidation.py
Case ID: PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step13_consolidation.py PHOTO-2025-01-26-001

REQUIREMENTS:
- Step 12A and/or Step 12B must be completed first
- Python 3 with hashlib, json, shutil

TIME ESTIMATE:
- ~5-30 minutes depending on number of files
- Mostly limited by disk I/O for hash calculation

================================================================================
"""