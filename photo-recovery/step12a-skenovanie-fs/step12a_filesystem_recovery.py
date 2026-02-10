#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-FS-RECOVERY: Filesystem-based recovery obrazových súborov
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript využíva The Sleuth Kit (fls + icat) na obnovu obrazových súborov
zo súborového systému so zachovaním pôvodných názvov a štruktúry.
"""

import subprocess
import json
import sys
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
import hashlib

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False
    print("WARNING: ptlibs not found, using fallback output")


class FilesystemRecovery:
    """
    Filesystem-based recovery pre obrazové súbory.
    
    Proces:
    1. Load partition info from Step 10
    2. Scan filesystem using fls (active + deleted files)
    3. Filter image files
    4. Extract using icat (by inode)
    5. Validate recovered files
    6. Extract metadata (FS + EXIF)
    7. Organize output (active/deleted/corrupted)
    8. Generate report
    """
    
    # Podporované obrazové formáty
    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg',  # JPEG
        '.png',  # PNG
        '.tif', '.tiff',  # TIFF
        '.bmp',  # Bitmap
        '.gif',  # GIF
        '.heic', '.heif',  # HEIC (Apple)
        '.webp',  # WebP
        # RAW formáty
        '.cr2', '.cr3',  # Canon
        '.nef', '.nrw',  # Nikon
        '.arw', '.srf', '.sr2',  # Sony
        '.dng',  # Adobe/Generic
        '.orf',  # Olympus
        '.raf',  # Fuji
        '.rw2',  # Panasonic
        '.pef',  # Pentax
        '.raw',  # Generic RAW
    }
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Cesty k obrazu a analýze
        self.image_path = None
        self.fs_analysis = None
        
        # Výstupné adresáre
        self.recovery_base = self.output_dir / f"{case_id}_recovered"
        self.active_dir = self.recovery_base / "active"
        self.deleted_dir = self.recovery_base / "deleted"
        self.corrupted_dir = self.recovery_base / "corrupted"
        self.metadata_dir = self.recovery_base / "metadata"
        
        # Štatistiky
        self.stats = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "method": "filesystem_scan",
            "partitions_processed": 0,
            "total_files_scanned": 0,
            "image_files_found": 0,
            "active_images": 0,
            "deleted_images": 0,
            "images_extracted": 0,
            "valid_images": 0,
            "corrupted_images": 0,
            "invalid_images": 0,
            "with_exif": 0,
            "by_format": {},
            "extraction_duration_seconds": 0,
            "validation_duration_seconds": 0,
            "success": False
        }
        
        # Zoznam obnovených súborov
        self.recovered_files = []
    
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
    
    def _run_command(self, cmd, timeout=300, capture_binary=False):
        """Spustí príkaz a zachytí výstup"""
        try:
            if capture_binary:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=timeout
                )
                return {
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "success": result.returncode == 0
                }
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                return {
                    "returncode": result.returncode,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "success": result.returncode == 0
                }
        except subprocess.TimeoutExpired:
            return {"returncode": -1, "stdout": "", "stderr": "Timeout", "success": False}
        except Exception as e:
            return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}
    
    def load_fs_analysis(self):
        """Načíta výsledky z Kroku 10 (Filesystem Analysis)"""
        self._print("\nLoading filesystem analysis from Step 10...", "TITLE")
        
        analysis_file = self.output_dir / f"{self.case_id}_filesystem_analysis.json"
        
        if not analysis_file.exists():
            self._print(f"ERROR: Filesystem analysis not found: {analysis_file}", "ERROR")
            self._print("Please run Step 10 (Filesystem Analysis) first!", "ERROR")
            return False
        
        try:
            with open(analysis_file, 'r') as f:
                self.fs_analysis = json.load(f)
            
            # Kontrola, či je filesystem_scan odporúčaný
            method = self.fs_analysis.get("recommended_method")
            
            if method == "file_carving":
                self._print("WARNING: Step 10 recommended file_carving, not filesystem_scan", "WARNING")
                self._print("This step may not work well. Consider using Step 12B instead.", "WARNING")
                
                confirm = input("Continue anyway? (yes/no): ").strip().lower()
                if confirm not in ["yes", "y"]:
                    return False
            
            elif method == "hybrid":
                self._print("Step 10 recommended hybrid approach", "INFO")
                self._print("Will attempt filesystem scan, then recommend carving for remaining files", "INFO")
            
            # Načítanie image path
            self.image_path = Path(self.fs_analysis.get("image_file"))
            
            if not self.image_path.exists():
                self._print(f"ERROR: Image file not found: {self.image_path}", "ERROR")
                return False
            
            self._print(f"Image path: {self.image_path}", "OK")
            self._print(f"Recommended method: {method}", "INFO")
            self._print(f"Partitions to process: {len(self.fs_analysis.get('partitions', []))}", "INFO")
            
            return True
            
        except Exception as e:
            self._print(f"ERROR reading filesystem analysis: {str(e)}", "ERROR")
            return False
    
    def check_tools(self):
        """Overte dostupnosť potrebných nástrojov"""
        self._print("\nChecking required tools...", "TITLE")
        
        tools = {
            'fls': 'The Sleuth Kit - file listing',
            'icat': 'The Sleuth Kit - inode cat',
            'file': 'File type detection',
            'identify': 'ImageMagick - image validation',
            'exiftool': 'EXIF metadata extraction'
        }
        
        missing_tools = []
        
        for tool, description in tools.items():
            result = self._run_command(['which', tool], timeout=5)
            if result["success"]:
                self._print(f"{tool}: Found ({description})", "OK")
            else:
                self._print(f"{tool}: NOT FOUND ({description})", "ERROR")
                missing_tools.append(tool)
        
        if missing_tools:
            self._print(f"\nERROR: Missing tools: {', '.join(missing_tools)}", "ERROR")
            self._print("Install:", "ERROR")
            self._print("  sudo apt-get install sleuthkit imagemagick libimage-exiftool-perl", "ERROR")
            return False
        
        return True
    
    def prepare_directories(self):
        """Vytvorenie výstupných adresárov"""
        self._print("\nPreparing output directories...", "TITLE")
        
        for directory in [self.active_dir, self.deleted_dir, self.corrupted_dir, self.metadata_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            self._print(f"Created: {directory.name}/", "INFO")
        
        return True
    
    def scan_filesystem(self, partition):
        """
        FÁZA 1: Skenovanie súborového systému pomocou fls.
        
        Args:
            partition: Dictionary s informáciami o partícii
        
        Returns:
            List of file entries (dictionaries)
        """
        offset = partition.get("offset", 0)
        
        self._print(f"\nScanning partition at offset {offset}...", "TITLE")
        
        # fls -r (recursive) -d (deleted) -p (full paths)
        cmd = ['fls', '-r', '-d', '-p', '-o', str(offset), str(self.image_path)]
        
        self._print("Running fls (this may take several minutes)...", "INFO")
        
        result = self._run_command(cmd, timeout=1800)  # 30 min timeout
        
        if not result["success"]:
            self._print(f"ERROR: fls failed: {result['stderr']}", "ERROR")
            return []
        
        # Parsovanie fls výstupu
        file_entries = []
        lines = result["stdout"].split('\n')
        
        for line in lines:
            if not line.strip():
                continue
            
            # fls formát: r/r * 12845:	/DCIM/100CANON/IMG_0001.JPG
            # r/r = regular file, * = deleted, 12845 = inode, /path = full path
            
            # Parse deleted flag
            is_deleted = '*' in line
            
            # Parse inode
            inode_match = re.search(r'(\d+):', line)
            if not inode_match:
                continue
            
            inode = int(inode_match.group(1))
            
            # Parse filepath (after inode:)
            filepath_match = re.search(r':\s+(.+)$', line)
            if not filepath_match:
                continue
            
            filepath = filepath_match.group(1).strip()
            
            # Skip directories
            if line.startswith('d/d'):
                continue
            
            # Vytvorenie entry
            entry = {
                "inode": inode,
                "path": filepath,
                "filename": os.path.basename(filepath),
                "deleted": is_deleted,
                "raw_line": line
            }
            
            file_entries.append(entry)
            self.stats["total_files_scanned"] += 1
        
        self._print(f"Found {len(file_entries)} file entries", "OK")
        
        return file_entries
    
    def filter_image_files(self, file_entries):
        """
        FÁZA 2: Filtrovanie obrazových súborov.
        
        Args:
            file_entries: List of all file entries
        
        Returns:
            Tuple (active_images, deleted_images)
        """
        self._print("\nFiltering image files...", "TITLE")
        
        active_images = []
        deleted_images = []
        
        for entry in file_entries:
            filename = entry["filename"].lower()
            
            # Kontrola prípony
            ext = os.path.splitext(filename)[1]
            
            if ext in self.IMAGE_EXTENSIONS:
                if entry["deleted"]:
                    deleted_images.append(entry)
                    self.stats["deleted_images"] += 1
                else:
                    active_images.append(entry)
                    self.stats["active_images"] += 1
                
                self.stats["image_files_found"] += 1
                
                # Počítanie podľa formátu
                format_key = ext.lstrip('.')
                self.stats["by_format"][format_key] = self.stats["by_format"].get(format_key, 0) + 1
        
        self._print(f"Image files found: {self.stats['image_files_found']}", "OK")
        self._print(f"  Active: {self.stats['active_images']}", "INFO")
        self._print(f"  Deleted: {self.stats['deleted_images']}", "INFO")
        
        return active_images, deleted_images
    
    def extract_file(self, entry, partition_offset, output_base_dir):
        """
        FÁZA 3: Extrakcia súboru pomocou icat.
        
        Args:
            entry: File entry dictionary
            partition_offset: Partition offset
            output_base_dir: Base directory (active or deleted)
        
        Returns:
            Path to extracted file or None
        """
        inode = entry["inode"]
        original_path = entry["path"]
        
        # Vytvorenie cieľovej cesty so zachovaním štruktúry
        # Remove leading slash if present
        relative_path = original_path.lstrip('/')
        output_path = output_base_dir / relative_path
        
        # Vytvorenie adresárov
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # icat na extrakciu
        cmd = ['icat', '-o', str(partition_offset), str(self.image_path), str(inode)]
        
        try:
            # Spustíme icat a zapíšeme výstup do súboru
            with open(output_path, 'wb') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    timeout=60
                )
            
            if result.returncode == 0:
                return output_path
            else:
                self._print(f"  Failed to extract inode {inode}: {result.stderr.decode()}", "WARNING")
                return None
                
        except Exception as e:
            self._print(f"  Error extracting inode {inode}: {str(e)}", "WARNING")
            return None
    
    def validate_image(self, filepath):
        """
        FÁZA 4: Validácia obrazového súboru.
        
        Args:
            filepath: Path to file
        
        Returns:
            Tuple (is_valid, status, info)
            status: 'valid', 'corrupted', 'invalid'
        """
        info = {
            "size": 0,
            "file_type": None,
            "image_format": None,
            "dimensions": None,
            "validation_errors": []
        }
        
        # Test 1: Kontrola veľkosti
        try:
            size = filepath.stat().st_size
            info["size"] = size
            
            if size == 0:
                info["validation_errors"].append("File is 0 bytes")
                return False, 'invalid', info
        except Exception as e:
            info["validation_errors"].append(f"Cannot read file: {str(e)}")
            return False, 'invalid', info
        
        # Test 2: file command
        result = self._run_command(['file', '-b', str(filepath)], timeout=10)
        if result["success"]:
            info["file_type"] = result["stdout"]
            
            # Kontrola, či je to skutočne obrázok
            if not any(img_type in result["stdout"].lower() for img_type in ['image', 'jpeg', 'png', 'tiff', 'gif', 'bitmap']):
                info["validation_errors"].append(f"Not an image according to 'file': {result['stdout']}")
                return False, 'invalid', info
        
        # Test 3: ImageMagick identify
        result = self._run_command(['identify', str(filepath)], timeout=30)
        if result["success"]:
            # identify output: filename.jpg JPEG 1920x1080 ...
            match = re.search(r'(\w+)\s+(\d+)x(\d+)', result["stdout"])
            if match:
                info["image_format"] = match.group(1)
                info["dimensions"] = f"{match.group(2)}x{match.group(3)}"
            
            return True, 'valid', info
        else:
            # identify zlyhalo - súbor je pravdepodobne korumpovaný
            info["validation_errors"].append("ImageMagick identify failed - file may be corrupted")
            
            # Ak má aspoň nejakú veľkosť, môže byť čiastočne obnoviteľný
            if size > 1024:  # Viac ako 1KB
                return False, 'corrupted', info
            else:
                return False, 'invalid', info
    
    def extract_metadata(self, filepath, entry):
        """
        FÁZA 5: Extrakcia metadát (FS + EXIF).
        
        Args:
            filepath: Path to file
            entry: Original file entry
        
        Returns:
            Dictionary with metadata
        """
        metadata = {
            "filename": filepath.name,
            "original_path": entry["path"],
            "inode": entry["inode"],
            "deleted": entry["deleted"],
            "fs_metadata": {},
            "exif_metadata": {}
        }
        
        # FS metadata
        try:
            stat_info = filepath.stat()
            metadata["fs_metadata"] = {
                "size_bytes": stat_info.st_size,
                "modified_time": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                "accessed_time": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
                "created_time": datetime.fromtimestamp(stat_info.st_ctime).isoformat()
            }
        except Exception as e:
            metadata["fs_metadata"]["error"] = str(e)
        
        # EXIF metadata pomocou exiftool
        result = self._run_command(['exiftool', '-json', str(filepath)], timeout=30)
        
        if result["success"]:
            try:
                exif_data = json.loads(result["stdout"])
                if exif_data and len(exif_data) > 0:
                    metadata["exif_metadata"] = exif_data[0]
                    
                    # Check for important EXIF fields
                    if any(key in metadata["exif_metadata"] for key in ['DateTimeOriginal', 'CreateDate', 'GPSLatitude']):
                        self.stats["with_exif"] += 1
                        metadata["has_exif"] = True
                    else:
                        metadata["has_exif"] = False
            except Exception as e:
                metadata["exif_metadata"]["error"] = str(e)
                metadata["has_exif"] = False
        else:
            metadata["has_exif"] = False
        
        return metadata
    
    def process_partition(self, partition):
        """Spracovanie jednej partície"""
        
        partition_num = partition.get("number", 0)
        offset = partition.get("offset", 0)
        
        self._print("\n" + "="*70, "TITLE")
        self._print(f"PROCESSING PARTITION {partition_num}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Skenovanie
        file_entries = self.scan_filesystem(partition)
        
        if not file_entries:
            self._print("No files found in this partition", "WARNING")
            return
        
        # 2. Filtrovanie
        active_images, deleted_images = self.filter_image_files(file_entries)
        
        if not active_images and not deleted_images:
            self._print("No image files found in this partition", "WARNING")
            return
        
        # 3. Extrakcia + Validácia + Metadata
        start_time = datetime.now()
        
        all_images = [
            (img, self.active_dir, "active") for img in active_images
        ] + [
            (img, self.deleted_dir, "deleted") for img in deleted_images
        ]
        
        total = len(all_images)
        
        self._print(f"\nExtracting {total} image files...", "TITLE")
        
        for idx, (entry, output_dir, status) in enumerate(all_images, 1):
            if idx % 10 == 0 or idx == total:
                self._print(f"Progress: {idx}/{total} ({idx*100//total}%)", "INFO")
            
            # Extrakcia
            extracted_path = self.extract_file(entry, offset, output_dir)
            
            if not extracted_path:
                self.stats["invalid_images"] += 1
                continue
            
            self.stats["images_extracted"] += 1
            
            # Validácia
            is_valid, validation_status, validation_info = self.validate_image(extracted_path)
            
            if validation_status == 'valid':
                self.stats["valid_images"] += 1
                
                # Extrakcia metadát
                metadata = self.extract_metadata(extracted_path, entry)
                
                # Uloženie metadát do JSON
                metadata_file = self.metadata_dir / f"{extracted_path.name}_metadata.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                # Pridanie do zoznamu obnovených
                self.recovered_files.append({
                    "filename": extracted_path.name,
                    "original_path": entry["path"],
                    "recovered_path": str(extracted_path.relative_to(self.recovery_base)),
                    "inode": entry["inode"],
                    "status": status,
                    "size_bytes": validation_info["size"],
                    "format": validation_info.get("image_format"),
                    "dimensions": validation_info.get("dimensions"),
                    "has_exif": metadata.get("has_exif", False)
                })
                
            elif validation_status == 'corrupted':
                self.stats["corrupted_images"] += 1
                
                # Presun do corrupted
                corrupted_path = self.corrupted_dir / extracted_path.name
                shutil.move(str(extracted_path), str(corrupted_path))
                
            else:  # invalid
                self.stats["invalid_images"] += 1
                
                # Vymazanie nevalidného súboru
                extracted_path.unlink()
        
        extraction_duration = (datetime.now() - start_time).total_seconds()
        self.stats["extraction_duration_seconds"] += extraction_duration
        
        self._print(f"\nExtraction completed in {extraction_duration:.0f} seconds", "OK")
    
    def run_recovery(self):
        """Hlavná funkcia - spustí celý recovery proces"""
        
        self._print("="*70, "TITLE")
        self._print("FILESYSTEM-BASED PHOTO RECOVERY", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Načítanie FS analýzy
        if not self.load_fs_analysis():
            self.stats["success"] = False
            return self.stats
        
        # 2. Kontrola nástrojov
        if not self.check_tools():
            self.stats["success"] = False
            return self.stats
        
        # 3. Príprava adresárov
        if not self.prepare_directories():
            self.stats["success"] = False
            return self.stats
        
        # 4. Spracovanie každej partície
        partitions = self.fs_analysis.get("partitions", [])
        
        for partition in partitions:
            # Skip partitions without recognized filesystem
            if not partition.get("filesystem", {}).get("recognized"):
                self._print(f"Skipping partition {partition.get('number')} - filesystem not recognized", "WARNING")
                continue
            
            self.process_partition(partition)
            self.stats["partitions_processed"] += 1
        
        # 5. Finalizácia
        self._print("\n" + "="*70, "TITLE")
        self._print("RECOVERY COMPLETED", "OK")
        self._print("="*70, "TITLE")
        
        self._print(f"Images found: {self.stats['image_files_found']}", "INFO")
        self._print(f"Images extracted: {self.stats['images_extracted']}", "INFO")
        self._print(f"Valid images: {self.stats['valid_images']}", "OK")
        self._print(f"Corrupted images: {self.stats['corrupted_images']}", "WARNING")
        self._print(f"Invalid images: {self.stats['invalid_images']}", "ERROR")
        
        if self.stats['images_extracted'] > 0:
            success_rate = (self.stats['valid_images'] / self.stats['images_extracted']) * 100
            self._print(f"Success rate: {success_rate:.1f}%", "OK")
            self.stats["success_rate"] = round(success_rate, 2)
        
        self._print("="*70 + "\n", "TITLE")
        
        self.stats["success"] = True
        
        return self.stats
    
    def save_reports(self):
        """Uloženie reportov"""
        
        # 1. Hlavný recovery report
        report_file = self.output_dir / f"{self.case_id}_recovery_report.json"
        
        report = {
            "statistics": self.stats,
            "recovered_files": self.recovered_files,
            "output_directories": {
                "active": str(self.active_dir),
                "deleted": str(self.deleted_dir),
                "corrupted": str(self.corrupted_dir),
                "metadata": str(self.metadata_dir)
            }
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self._print(f"Recovery report saved: {report_file}", "OK")
        
        # 2. Textový report pre používateľa
        text_report = self.recovery_base / "RECOVERY_REPORT.txt"
        
        with open(text_report, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("FILESYSTEM-BASED PHOTO RECOVERY REPORT\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"Case ID: {self.case_id}\n")
            f.write(f"Timestamp: {self.stats['timestamp']}\n")
            f.write(f"Method: {self.stats['method']}\n\n")
            
            f.write("STATISTICS:\n")
            f.write(f"  Total files scanned: {self.stats['total_files_scanned']}\n")
            f.write(f"  Image files found: {self.stats['image_files_found']}\n")
            f.write(f"    - Active: {self.stats['active_images']}\n")
            f.write(f"    - Deleted: {self.stats['deleted_images']}\n\n")
            
            f.write(f"  Images extracted: {self.stats['images_extracted']}\n")
            f.write(f"  Valid images: {self.stats['valid_images']}\n")
            f.write(f"  Corrupted images: {self.stats['corrupted_images']}\n")
            f.write(f"  Invalid images: {self.stats['invalid_images']}\n\n")
            
            if self.stats.get('success_rate'):
                f.write(f"  Success rate: {self.stats['success_rate']}%\n\n")
            
            f.write("BY FORMAT:\n")
            for fmt, count in sorted(self.stats['by_format'].items()):
                f.write(f"  {fmt.upper()}: {count}\n")
            
            f.write("\n" + "="*70 + "\n")
            f.write("RECOVERED FILES:\n")
            f.write("="*70 + "\n\n")
            
            for file_info in self.recovered_files[:100]:  # First 100
                f.write(f"{file_info['filename']}\n")
                f.write(f"  Original: {file_info['original_path']}\n")
                f.write(f"  Recovered: {file_info['recovered_path']}\n")
                f.write(f"  Size: {file_info['size_bytes']} bytes\n")
                if file_info.get('dimensions'):
                    f.write(f"  Dimensions: {file_info['dimensions']}\n")
                f.write(f"  EXIF: {'Yes' if file_info.get('has_exif') else 'No'}\n")
                f.write("\n")
            
            if len(self.recovered_files) > 100:
                f.write(f"... and {len(self.recovered_files) - 100} more files\n")
        
        self._print(f"Text report saved: {text_report}", "OK")
        
        return str(report_file)


def main():
    """
    Hlavná funkcia - entry point pre Penterep platformu
    """
    
    print("\n" + "="*70)
    print("FOR-COL-FS-RECOVERY: Filesystem-Based Photo Recovery")
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
    
    # Spustenie recovery
    recovery = FilesystemRecovery(case_id)
    results = recovery.run_recovery()
    
    # Uloženie reportov
    if results["success"]:
        report_path = recovery.save_reports()
        print(f"\nFilesystem recovery completed successfully")
        print(f"Recovered {results['valid_images']} valid images")
        print(f"Success rate: {results.get('success_rate', 0)}%")
        print(f"Next step: Step 13 (EXIF Analysis)")
        sys.exit(0)
    else:
        print("\nFilesystem recovery failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - KEY FEATURES
================================================================================

FILESYSTEM-BASED RECOVERY
- Uses The Sleuth Kit (fls + icat) for professional forensic recovery
- Preserves original filenames and directory structure
- Extracts both active and deleted files
- Faster than file carving (30min-2hr vs 2-8hr)

SIX-PHASE PROCESS
1. Scan filesystem (fls -r -d -p)
2. Filter image files by extension
3. Extract files using icat (by inode)
4. Validate recovered files (file + ImageMagick)
5. Extract metadata (FS timestamps + EXIF)
6. Organize output (active/deleted/corrupted)

INTEGRATION WITH STEP 10
- Automatically loads partition info from Step 10 analysis
- Checks recommended method (filesystem_scan vs file_carving)
- Uses partition offsets for multi-partition media

SUPPORTED FORMATS
- JPEG/JPG (most common)
- PNG (lossless)
- TIFF (professional)
- BMP, GIF, WebP
- RAW formats: CR2/CR3 (Canon), NEF (Nikon), ARW (Sony), DNG, ORF, RAF, RW2

FILE VALIDATION
- Size check (0 bytes = invalid)
- file command (type detection)
- ImageMagick identify (structure validation)
- Categorization: valid / corrupted / invalid

METADATA EXTRACTION
- FS metadata: size, timestamps (created/modified/accessed)
- EXIF metadata: GPS, camera settings, DateTime
- JSON catalog for each file
- Master metadata catalog

OUTPUT ORGANIZATION
recovered/
  ├─ active/              (active files with original structure)
  │  └─ DCIM/100CANON/IMG_0001.JPG
  ├─ deleted/             (deleted but recovered files)
  │  └─ DCIM/100CANON/IMG_0234.JPG
  ├─ corrupted/           (partially damaged files)
  └─ metadata/            (JSON metadata for each file)

COMPREHENSIVE REPORTING
- JSON report with statistics
- Text report for users
- Per-file metadata in JSON
- Success rate calculation

================================================================================
EXAMPLE OUTPUT - SUCCESSFUL RECOVERY
================================================================================

======================================================================
FILESYSTEM-BASED PHOTO RECOVERY
Case ID: PHOTO-2025-01-26-001
======================================================================

Loading filesystem analysis from Step 10...
[✓] Image path: /mnt/user-data/outputs/PHOTO-2025-01-26-001.dd
[i] Recommended method: filesystem_scan
[i] Partitions to process: 1

Checking required tools...
[✓] fls: Found (The Sleuth Kit - file listing)
[✓] icat: Found (The Sleuth Kit - inode cat)
[✓] file: Found (File type detection)
[✓] identify: Found (ImageMagick - image validation)
[✓] exiftool: Found (EXIF metadata extraction)

Preparing output directories...
[i] Created: active/
[i] Created: deleted/
[i] Created: corrupted/
[i] Created: metadata/

======================================================================
PROCESSING PARTITION 1
======================================================================

Scanning partition at offset 2048...
[i] Running fls (this may take several minutes)...
[✓] Found 1547 file entries

Filtering image files...
[✓] Image files found: 487
[i]   Active: 412
[i]   Deleted: 75

Extracting 487 image files...
[i] Progress: 100/487 (20%)
[i] Progress: 200/487 (41%)
[i] Progress: 300/487 (61%)
[i] Progress: 400/487 (82%)
[i] Progress: 487/487 (100%)

[✓] Extraction completed in 1245 seconds

======================================================================
RECOVERY COMPLETED
======================================================================
[i] Images found: 487
[i] Images extracted: 478
[✓] Valid images: 451
[!] Corrupted images: 18
[✗] Invalid images: 9
[✓] Success rate: 94.4%
======================================================================

[✓] Recovery report saved: /mnt/user-data/outputs/PHOTO-2025-01-26-001_recovery_report.json
[✓] Text report saved: /mnt/user-data/outputs/PHOTO-2025-01-26-001_recovered/RECOVERY_REPORT.txt

Filesystem recovery completed successfully
Recovered 451 valid images
Success rate: 94.4%
Next step: Step 13 (EXIF Analysis)

================================================================================
JSON REPORT FORMAT
================================================================================

{
  "statistics": {
    "case_id": "PHOTO-2025-01-26-001",
    "timestamp": "2025-01-26T22:30:00Z",
    "method": "filesystem_scan",
    "partitions_processed": 1,
    "total_files_scanned": 1547,
    "image_files_found": 487,
    "active_images": 412,
    "deleted_images": 75,
    "images_extracted": 478,
    "valid_images": 451,
    "corrupted_images": 18,
    "invalid_images": 9,
    "with_exif": 423,
    "by_format": {
      "jpg": 429,
      "png": 38,
      "cr2": 12,
      "heic": 8
    },
    "extraction_duration_seconds": 1245,
    "success_rate": 94.4,
    "success": true
  },
  "recovered_files": [
    {
      "filename": "IMG_0001.JPG",
      "original_path": "/DCIM/100CANON/IMG_0001.JPG",
      "recovered_path": "active/DCIM/100CANON/IMG_0001.JPG",
      "inode": 12845,
      "status": "active",
      "size_bytes": 2458624,
      "format": "JPEG",
      "dimensions": "1920x1080",
      "has_exif": true
    }
  ],
  "output_directories": {
    "active": "/mnt/user-data/outputs/PHOTO-2025-01-26-001_recovered/active",
    "deleted": "/mnt/user-data/outputs/PHOTO-2025-01-26-001_recovered/deleted",
    "corrupted": "/mnt/user-data/outputs/PHOTO-2025-01-26-001_recovered/corrupted",
    "metadata": "/mnt/user-data/outputs/PHOTO-2025-01-26-001_recovered/metadata"
  }
}

================================================================================
USAGE
================================================================================

INTERACTIVE MODE:
$ python3 step12a_filesystem_recovery.py
Case ID: PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step12a_filesystem_recovery.py PHOTO-2025-01-26-001

REQUIREMENTS:
- Step 10 (Filesystem Analysis) must be completed first
- The Sleuth Kit: sudo apt-get install sleuthkit
- ImageMagick: sudo apt-get install imagemagick
- ExifTool: sudo apt-get install libimage-exiftool-perl

================================================================================
"""