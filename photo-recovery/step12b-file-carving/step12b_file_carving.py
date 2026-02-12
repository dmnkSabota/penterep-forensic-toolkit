#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-CARVING: File carving recovery obrazových súborov
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript využíva PhotoRec na obnovu obrazových súborov pomocou byte signatures
bez závislosti na súborovom systéme.
"""

import subprocess
import json
import sys
import os
import re
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


class FileCarvingRecovery:
    """
    File carving recovery pre obrazové súbory pomocou PhotoRec.
    
    Proces:
    1. Load image path from Step 10
    2. Configure PhotoRec (formats to search)
    3. Run PhotoRec carving (2-8 hours)
    4. Collect and validate carved files
    5. Deduplicate using SHA-256 hashing
    6. Extract EXIF metadata
    7. Organize and rename files
    8. Generate comprehensive report
    """
    
    # Podporované formáty
    IMAGE_FORMATS = {
        'jpg': 'JPEG images',
        'png': 'PNG images',
        'gif': 'GIF images',
        'bmp': 'Bitmap images',
        'tiff': 'TIFF images',
        'heic': 'HEIC images (Apple)',
        'webp': 'WebP images',
        # RAW formáty
        'cr2': 'Canon RAW',
        'cr3': 'Canon RAW (newer)',
        'nef': 'Nikon RAW',
        'arw': 'Sony RAW',
        'dng': 'Adobe DNG RAW',
        'orf': 'Olympus RAW',
        'raf': 'Fuji RAW',
        'rw2': 'Panasonic RAW',
    }
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Cesty
        self.image_path = None
        self.fs_analysis = None
        
        # Working directories
        self.carving_base = self.output_dir / f"{case_id}_carved"
        self.photorec_work = self.carving_base / "photorec_work"
        self.organized_dir = self.carving_base / "organized"
        self.corrupted_dir = self.carving_base / "corrupted"
        self.quarantine_dir = self.carving_base / "quarantine"
        self.duplicates_dir = self.carving_base / "duplicates"
        self.metadata_dir = self.carving_base / "metadata"
        
        # Štatistiky
        self.stats = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "method": "file_carving",
            "tool": "PhotoRec",
            "total_carved_raw": 0,
            "valid_after_validation": 0,
            "corrupted_files": 0,
            "invalid_files": 0,
            "duplicates_removed": 0,
            "final_unique_files": 0,
            "by_format": {},
            "with_exif": 0,
            "with_gps": 0,
            "carving_duration_seconds": 0,
            "validation_duration_seconds": 0,
            "deduplication_duration_seconds": 0,
            "total_duration_seconds": 0,
            "success": False
        }
        
        # File tracking
        self.carved_files = []
        self.valid_files = []
        self.unique_files = []
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
    
    def _run_command(self, cmd, timeout=None):
        """Spustí príkaz a zachytí výstup"""
        try:
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
        """Načíta výsledky z Kroku 10"""
        self._print("\nLoading filesystem analysis from Step 10...", "TITLE")
        
        analysis_file = self.output_dir / f"{self.case_id}_filesystem_analysis.json"
        
        if not analysis_file.exists():
            self._print(f"ERROR: Filesystem analysis not found: {analysis_file}", "ERROR")
            self._print("Please run Step 10 (Filesystem Analysis) first!", "ERROR")
            return False
        
        try:
            with open(analysis_file, 'r') as f:
                self.fs_analysis = json.load(f)
            
            # Kontrola odporúčanej metódy
            method = self.fs_analysis.get("recommended_method")
            
            if method == "filesystem_scan":
                self._print("WARNING: Step 10 recommended filesystem_scan, not file_carving", "WARNING")
                self._print("File carving is slower. Consider using Step 12A instead.", "WARNING")
                
                confirm = input("Continue with file carving anyway? (yes/no): ").strip().lower()
                if confirm not in ["yes", "y"]:
                    return False
            
            elif method == "hybrid":
                self._print("Step 10 recommended hybrid approach", "INFO")
                self._print("File carving will find additional files not visible via filesystem", "INFO")
            
            # Načítanie image path
            self.image_path = Path(self.fs_analysis.get("image_file"))
            
            if not self.image_path.exists():
                self._print(f"ERROR: Image file not found: {self.image_path}", "ERROR")
                return False
            
            self._print(f"Image path: {self.image_path}", "OK")
            self._print(f"Recommended method: {method}", "INFO")
            
            return True
            
        except Exception as e:
            self._print(f"ERROR reading filesystem analysis: {str(e)}", "ERROR")
            return False
    
    def check_tools(self):
        """Overte dostupnosť potrebných nástrojov"""
        self._print("\nChecking required tools...", "TITLE")
        
        tools = {
            'photorec': 'PhotoRec - file carving',
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
            self._print("  sudo apt-get install testdisk imagemagick libimage-exiftool-perl", "ERROR")
            return False
        
        return True
    
    def prepare_directories(self):
        """Vytvorenie working directories"""
        self._print("\nPreparing output directories...", "TITLE")
        
        for directory in [self.photorec_work, self.organized_dir, self.corrupted_dir, 
                         self.quarantine_dir, self.duplicates_dir, self.metadata_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            self._print(f"Created: {directory.name}/", "INFO")
        
        # Vytvorenie type-specific directories
        for fmt in ['jpg', 'png', 'tiff', 'raw', 'other']:
            (self.organized_dir / fmt).mkdir(exist_ok=True)
        
        return True
    
    def configure_photorec(self):
        """
        FÁZA 1: Konfigurácia PhotoRec.
        Vytvorí batch mode príkazy pre PhotoRec.
        """
        self._print("\nConfiguring PhotoRec...", "TITLE")
        
        # PhotoRec command file
        photorec_cmd_file = self.photorec_work / "photorec.cmd"
        
        commands = []
        
        # Disable all file types first
        commands.append("fileopt,everything,disable")
        
        # Enable only image formats
        for fmt in self.IMAGE_FORMATS.keys():
            commands.append(f"fileopt,{fmt},enable")
        
        # Search options
        commands.append("options,paranoid,enable")  # Paranoid mode - thorough search
        commands.append("options,expert,enable")     # Expert mode - fragment reconstruction
        
        # Start search
        commands.append("search")
        
        with open(photorec_cmd_file, 'w') as f:
            for cmd in commands:
                f.write(cmd + '\n')
        
        self._print(f"PhotoRec configuration saved: {photorec_cmd_file}", "OK")
        self._print(f"Formats enabled: {', '.join(self.IMAGE_FORMATS.keys())}", "INFO")
        
        return str(photorec_cmd_file)
    
    def run_photorec(self):
        """
        FÁZA 2: Spustenie PhotoRec carving.
        VAROVANIE: Tento proces môže trvať 2-8 hodín!
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("RUNNING PHOTOREC FILE CARVING", "TITLE")
        self._print("="*70, "TITLE")
        
        self._print("\nWARNING: This process may take 2-8 hours!", "WARNING")
        self._print("Do not interrupt the process.", "WARNING")
        
        # Confirm before starting
        confirm = input("\nProceed with file carving? (yes/no): ").strip().lower()
        if confirm not in ["yes", "y"]:
            self._print("File carving cancelled", "WARNING")
            return False
        
        # PhotoRec command
        # photorec /log /d output_dir /cmd image_path
        cmd = [
            'photorec',
            '/log',  # Enable logging
            '/d', str(self.photorec_work),  # Output directory
            '/cmd', str(self.image_path),  # Image file
            'search'  # Start search immediately
        ]
        
        self._print(f"\nCommand: {' '.join(cmd)}", "INFO")
        self._print("\nPhotoRec is running (this will take hours)...", "INFO")
        self._print("Progress will be displayed below:\n", "INFO")
        
        start_time = datetime.now()
        
        try:
            # Run PhotoRec with real-time output
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Print output in real-time
            for line in process.stdout:
                print(line, end='')
            
            process.wait()
            
            duration = (datetime.now() - start_time).total_seconds()
            self.stats["carving_duration_seconds"] = round(duration, 2)
            
            if process.returncode == 0:
                self._print(f"\nPhotoRec completed in {duration/60:.1f} minutes ({duration:.0f} seconds)", "OK")
                return True
            else:
                self._print(f"\nPhotoRec failed with return code {process.returncode}", "ERROR")
                return False
                
        except Exception as e:
            self._print(f"\nPhotoRec error: {str(e)}", "ERROR")
            return False
    
    def collect_carved_files(self):
        """
        Kolekcia všetkých súborov z recup_dir.* adresárov.
        PhotoRec vytvára adresáre recup_dir.1, recup_dir.2, ...
        """
        self._print("\nCollecting carved files...", "TITLE")
        
        # Hľadáme všetky recup_dir.* adresáre
        recup_dirs = list(self.photorec_work.glob("recup_dir.*"))
        
        if not recup_dirs:
            self._print("No recup_dir folders found!", "ERROR")
            return []
        
        self._print(f"Found {len(recup_dirs)} recup_dir folders", "OK")
        
        all_files = []
        
        for recup_dir in sorted(recup_dirs):
            files_in_dir = list(recup_dir.glob("f*.*"))
            all_files.extend(files_in_dir)
        
        self.stats["total_carved_raw"] = len(all_files)
        self._print(f"Total carved files: {len(all_files)}", "OK")
        
        return all_files
    
    def validate_file(self, filepath):
        """
        FÁZA 3: Validácia jedného súboru.
        
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
            
            if size < 100:  # Menej ako 100 bajtov
                info["validation_errors"].append("File too small (<100 bytes)")
                return False, 'invalid', info
        except Exception as e:
            info["validation_errors"].append(f"Cannot read file: {str(e)}")
            return False, 'invalid', info
        
        # Test 2: file command
        result = self._run_command(['file', '-b', str(filepath)], timeout=10)
        if result["success"]:
            info["file_type"] = result["stdout"]
            
            # Kontrola, či je to skutočne obrázok
            if not any(img_type in result["stdout"].lower() 
                      for img_type in ['image', 'jpeg', 'png', 'tiff', 'gif', 'bitmap', 'heic']):
                info["validation_errors"].append(f"Not an image: {result['stdout']}")
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
            # identify zlyhalo
            info["validation_errors"].append("ImageMagick identify failed")
            
            # Čiastočne obnoviteľný?
            if size > 10240:  # Viac ako 10KB
                return False, 'corrupted', info
            else:
                return False, 'invalid', info
    
    def calculate_hash(self, filepath):
        """Vypočíta SHA-256 hash súboru"""
        sha256_hash = hashlib.sha256()
        
        try:
            with open(filepath, "rb") as f:
                # Čítaj po 64KB blokoch
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            
            return sha256_hash.hexdigest()
        except Exception as e:
            return None
    
    def validate_and_deduplicate(self, carved_files):
        """
        FÁZA 3 + 4: Validácia a deduplikácia súborov.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("VALIDATION AND DEDUPLICATION", "TITLE")
        self._print("="*70, "TITLE")
        
        start_time = datetime.now()
        
        total = len(carved_files)
        valid_files = []
        
        self._print(f"\nValidating {total} carved files...", "INFO")
        
        for idx, filepath in enumerate(carved_files, 1):
            if idx % 50 == 0 or idx == total:
                self._print(f"Progress: {idx}/{total} ({idx*100//total}%)", "INFO")
            
            # Validácia
            is_valid, status, info = self.validate_file(filepath)
            
            if status == 'valid':
                # Výpočet hashu
                file_hash = self.calculate_hash(filepath)
                
                if file_hash:
                    # Kontrola duplikátu
                    if file_hash in self.hash_database:
                        # Duplikát - presunúť do duplicates
                        dup_path = self.duplicates_dir / filepath.name
                        shutil.move(str(filepath), str(dup_path))
                        self.stats["duplicates_removed"] += 1
                    else:
                        # Unikátny súbor
                        self.hash_database[file_hash] = str(filepath)
                        
                        file_info = {
                            "path": filepath,
                            "hash": file_hash,
                            "size": info["size"],
                            "format": info.get("image_format"),
                            "dimensions": info.get("dimensions")
                        }
                        
                        valid_files.append(file_info)
                        self.stats["valid_after_validation"] += 1
                        
                        # Počítanie podľa formátu
                        ext = filepath.suffix.lstrip('.').lower()
                        self.stats["by_format"][ext] = self.stats["by_format"].get(ext, 0) + 1
                
            elif status == 'corrupted':
                # Presun do corrupted
                corr_path = self.corrupted_dir / filepath.name
                shutil.move(str(filepath), str(corr_path))
                self.stats["corrupted_files"] += 1
                
            else:  # invalid
                # Presun do quarantine
                quar_path = self.quarantine_dir / filepath.name
                shutil.move(str(filepath), str(quar_path))
                self.stats["invalid_files"] += 1
        
        duration = (datetime.now() - start_time).total_seconds()
        self.stats["validation_duration_seconds"] = round(duration, 2)
        
        self.stats["final_unique_files"] = len(valid_files)
        
        self._print(f"\nValidation completed in {duration:.0f} seconds", "OK")
        self._print(f"Valid files: {self.stats['valid_after_validation']}", "OK")
        self._print(f"Duplicates removed: {self.stats['duplicates_removed']}", "INFO")
        self._print(f"Corrupted files: {self.stats['corrupted_files']}", "WARNING")
        self._print(f"Invalid files: {self.stats['invalid_files']}", "WARNING")
        self._print(f"Final unique files: {self.stats['final_unique_files']}", "OK")
        
        return valid_files
    
    def extract_exif(self, filepath):
        """
        FÁZA 5: Extrakcia EXIF metadát.
        """
        result = self._run_command(['exiftool', '-json', str(filepath)], timeout=30)
        
        if result["success"]:
            try:
                exif_data = json.loads(result["stdout"])
                if exif_data and len(exif_data) > 0:
                    metadata = exif_data[0]
                    
                    # Check for important fields
                    has_datetime = any(key in metadata for key in ['DateTimeOriginal', 'CreateDate'])
                    has_gps = 'GPSLatitude' in metadata
                    
                    if has_datetime or has_gps or len(metadata) > 5:
                        if has_gps:
                            self.stats["with_gps"] += 1
                        self.stats["with_exif"] += 1
                        
                        return metadata
            except:
                pass
        
        return None
    
    def organize_and_rename(self, valid_files):
        """
        FÁZA 6: Organizácia a premenovanie súborov.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("ORGANIZING AND RENAMING FILES", "TITLE")
        self._print("="*70, "TITLE")
        
        # Počítadlá pre každý formát
        format_counters = defaultdict(int)
        
        organized_files = []
        
        for file_info in valid_files:
            filepath = file_info["path"]
            ext = filepath.suffix.lstrip('.').lower()
            
            # Určenie target adresára
            if ext in ['jpg', 'jpeg']:
                target_dir = self.organized_dir / 'jpg'
                format_key = 'jpg'
            elif ext == 'png':
                target_dir = self.organized_dir / 'png'
                format_key = 'png'
            elif ext in ['tif', 'tiff']:
                target_dir = self.organized_dir / 'tiff'
                format_key = 'tiff'
            elif ext in ['cr2', 'cr3', 'nef', 'arw', 'dng', 'orf', 'raf', 'rw2']:
                target_dir = self.organized_dir / 'raw'
                format_key = 'raw'
            else:
                target_dir = self.organized_dir / 'other'
                format_key = 'other'
            
            # Increment counter
            format_counters[format_key] += 1
            sequence = format_counters[format_key]
            
            # Nový názov
            new_name = f"{self.case_id}_{format_key}_{sequence:06d}.{ext}"
            new_path = target_dir / new_name
            
            # Presun súboru
            shutil.move(str(filepath), str(new_path))
            
            # Extrakcia EXIF
            exif_data = self.extract_exif(new_path)
            
            # Uloženie metadát
            if exif_data:
                metadata_file = self.metadata_dir / f"{new_name}_metadata.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(exif_data, f, indent=2, ensure_ascii=False)
            
            # Pridanie do zoznamu
            organized_info = {
                "new_filename": new_name,
                "original_photorec_name": filepath.name,
                "path": str(new_path.relative_to(self.carving_base)),
                "hash": file_info["hash"],
                "size_bytes": file_info["size"],
                "format": format_key,
                "dimensions": file_info.get("dimensions"),
                "has_exif": exif_data is not None,
                "has_gps": exif_data.get("GPSLatitude") is not None if exif_data else False
            }
            
            organized_files.append(organized_info)
        
        self._print(f"\nOrganized {len(organized_files)} files", "OK")
        
        return organized_files
    
    def run_carving(self):
        """Hlavná funkcia - spustí celý carving proces"""
        
        overall_start = datetime.now()
        
        self._print("="*70, "TITLE")
        self._print("FILE CARVING PHOTO RECOVERY", "TITLE")
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
        
        # 4. Konfigurácia PhotoRec
        self.configure_photorec()
        
        # 5. Spustenie PhotoRec
        if not self.run_photorec():
            self.stats["success"] = False
            return self.stats
        
        # 6. Kolekcia carved súborov
        carved_files = self.collect_carved_files()
        
        if not carved_files:
            self._print("No files were carved - PhotoRec found nothing", "ERROR")
            self.stats["success"] = False
            return self.stats
        
        # 7. Validácia a deduplikácia
        valid_files = self.validate_and_deduplicate(carved_files)
        
        if not valid_files:
            self._print("No valid files after validation", "ERROR")
            self.stats["success"] = False
            return self.stats
        
        # 8. Organizácia a premenovanie
        self.unique_files = self.organize_and_rename(valid_files)
        
        # 9. Finalizácia
        overall_duration = (datetime.now() - overall_start).total_seconds()
        self.stats["total_duration_seconds"] = round(overall_duration, 2)
        
        if self.stats["total_carved_raw"] > 0:
            success_rate = (self.stats["final_unique_files"] / self.stats["total_carved_raw"]) * 100
            self.stats["success_rate_percent"] = round(success_rate, 2)
        
        self._print("\n" + "="*70, "TITLE")
        self._print("FILE CARVING COMPLETED", "OK")
        self._print("="*70, "TITLE")
        
        self._print(f"Total carved: {self.stats['total_carved_raw']}", "INFO")
        self._print(f"Valid files: {self.stats['valid_after_validation']}", "OK")
        self._print(f"Final unique: {self.stats['final_unique_files']}", "OK")
        self._print(f"Success rate: {self.stats.get('success_rate_percent', 0):.1f}%", "OK")
        self._print(f"Total time: {overall_duration/60:.1f} minutes", "INFO")
        self._print("="*70 + "\n", "TITLE")
        
        self.stats["success"] = True
        
        return self.stats
    
    def save_reports(self):
        """Uloženie reportov"""
        
        # 1. Hlavný carving report
        report_file = self.output_dir / f"{self.case_id}_carving_report.json"
        
        report = {
            "statistics": self.stats,
            "recovered_files": self.unique_files,
            "hash_database": self.hash_database,
            "output_directories": {
                "organized": str(self.organized_dir),
                "corrupted": str(self.corrupted_dir),
                "quarantine": str(self.quarantine_dir),
                "duplicates": str(self.duplicates_dir),
                "metadata": str(self.metadata_dir)
            }
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self._print(f"Carving report saved: {report_file}", "OK")
        
        # 2. Textový report
        text_report = self.carving_base / "CARVING_REPORT.txt"
        
        with open(text_report, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("FILE CARVING PHOTO RECOVERY REPORT\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"Case ID: {self.case_id}\n")
            f.write(f"Timestamp: {self.stats['timestamp']}\n")
            f.write(f"Method: {self.stats['method']}\n")
            f.write(f"Tool: {self.stats['tool']}\n\n")
            
            f.write("STATISTICS:\n")
            f.write(f"  Total carved (raw): {self.stats['total_carved_raw']}\n")
            f.write(f"  Valid after validation: {self.stats['valid_after_validation']}\n")
            f.write(f"  Corrupted files: {self.stats['corrupted_files']}\n")
            f.write(f"  Invalid files: {self.stats['invalid_files']}\n")
            f.write(f"  Duplicates removed: {self.stats['duplicates_removed']}\n")
            f.write(f"  Final unique files: {self.stats['final_unique_files']}\n\n")
            
            if self.stats.get('success_rate_percent'):
                f.write(f"  Success rate: {self.stats['success_rate_percent']}%\n\n")
            
            f.write("BY FORMAT:\n")
            for fmt, count in sorted(self.stats['by_format'].items()):
                f.write(f"  {fmt.upper()}: {count}\n")
            
            f.write(f"\n  Files with EXIF: {self.stats['with_exif']}\n")
            f.write(f"  Files with GPS: {self.stats['with_gps']}\n\n")
            
            f.write("TIMING:\n")
            f.write(f"  Carving: {self.stats['carving_duration_seconds']/60:.1f} minutes\n")
            f.write(f"  Validation: {self.stats['validation_duration_seconds']/60:.1f} minutes\n")
            f.write(f"  Total: {self.stats['total_duration_seconds']/60:.1f} minutes\n\n")
            
            f.write("="*70 + "\n")
            f.write("RECOVERED FILES (first 100):\n")
            f.write("="*70 + "\n\n")
            
            for file_info in self.unique_files[:100]:
                f.write(f"{file_info['new_filename']}\n")
                f.write(f"  Original: {file_info['original_photorec_name']}\n")
                f.write(f"  Path: {file_info['path']}\n")
                f.write(f"  Size: {file_info['size_bytes']} bytes\n")
                if file_info.get('dimensions'):
                    f.write(f"  Dimensions: {file_info['dimensions']}\n")
                f.write(f"  EXIF: {'Yes' if file_info.get('has_exif') else 'No'}\n")
                if file_info.get('has_gps'):
                    f.write(f"  GPS: Yes\n")
                f.write("\n")
            
            if len(self.unique_files) > 100:
                f.write(f"... and {len(self.unique_files) - 100} more files\n")
        
        self._print(f"Text report saved: {text_report}", "OK")
        
        return str(report_file)


def main():
    """
    Hlavná funkcia - entry point pre Penterep platformu
    """
    
    print("\n" + "="*70)
    print("FOR-COL-CARVING: File Carving Photo Recovery")
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
    
    print("\nWARNING: File carving is a VERY SLOW process!")
    print("Expected time: 2-8 hours for 64GB media")
    print("This process should run uninterrupted.\n")
    
    # Spustenie carving
    carving = FileCarvingRecovery(case_id)
    results = carving.run_carving()
    
    # Uloženie reportov
    if results["success"]:
        report_path = carving.save_reports()
        print(f"\nFile carving completed successfully")
        print(f"Recovered {results['final_unique_files']} unique files")
        print(f"Success rate: {results.get('success_rate_percent', 0)}%")
        print(f"Total time: {results['total_duration_seconds']/60:.1f} minutes")
        print(f"Next step: Step 13 (EXIF Analysis)")
        sys.exit(0)
    else:
        print("\nFile carving failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - KEY FEATURES
================================================================================

FILE CARVING RECOVERY
- Uses PhotoRec for signature-based file recovery
- Works without filesystem dependency
- Finds files even after formatting
- Slower but more thorough than filesystem-based recovery

SIX-PHASE PROCESS
1. Configure PhotoRec (select image formats)
2. Run PhotoRec carving (2-8 hours)
3. Collect files from recup_dir.* folders
4. Validate with ImageMagick (valid/corrupted/invalid)
5. Deduplicate using SHA-256 hashing (20-30% duplicates)
6. Extract EXIF and organize by type

INTEGRATION WITH STEP 10
- Reads recommended method from filesystem analysis
- Warns if filesystem_scan would be better
- Supports hybrid approach (12A + 12B)

VALIDATION SYSTEM
- Size check (minimum 100 bytes)
- file command (type detection)
- ImageMagick identify (structure validation)
- Three categories: valid / corrupted / invalid

DEDUPLICATION
- SHA-256 hash for each file
- Removes 20-30% duplicates typical
- Keeps best quality copy
- Moves duplicates to separate folder

OUTPUT ORGANIZATION
carved/
  ├─ organized/
  │  ├─ jpg/          (CASE-001_jpg_000001.jpg)
  │  ├─ png/
  │  ├─ tiff/
  │  ├─ raw/          (CR2, NEF, ARW, DNG...)
  │  └─ other/
  ├─ corrupted/       (partially damaged files)
  ├─ quarantine/      (false positives)
  ├─ duplicates/      (removed duplicates)
  └─ metadata/        (EXIF JSON files)

COMPREHENSIVE REPORTING
- JSON report with all statistics
- Text report for users
- Hash database (SHA-256 of all files)
- File mapping (PhotoRec names → organized names)

================================================================================
EXAMPLE OUTPUT
================================================================================

======================================================================
FILE CARVING PHOTO RECOVERY
Case ID: PHOTO-2025-01-26-001
======================================================================

WARNING: This process may take 2-8 hours!

[PhotoRec runs for several hours...]

Collecting carved files...
[✓] Found 3 recup_dir folders
[✓] Total carved files: 523

======================================================================
VALIDATION AND DEDUPLICATION
======================================================================

Validating 523 carved files...
[i] Progress: 523/523 (100%)

[✓] Validation completed in 145 seconds
[✓] Valid files: 412
[i] Duplicates removed: 98
[!] Corrupted files: 8
[!] Invalid files: 5
[✓] Final unique files: 314

======================================================================
ORGANIZING AND RENAMING FILES
======================================================================

[✓] Organized 314 files

======================================================================
FILE CARVING COMPLETED
======================================================================
[i] Total carved: 523
[✓] Valid files: 412
[✓] Final unique: 314
[✓] Success rate: 60.0%
[i] Total time: 187.3 minutes
======================================================================

File carving completed successfully
Recovered 314 unique files
Success rate: 60.0%
Total time: 187.3 minutes

================================================================================
USAGE
================================================================================

INTERACTIVE MODE:
$ python3 step12b_file_carving.py
Case ID: PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step12b_file_carving.py PHOTO-2025-01-26-001

REQUIREMENTS:
- PhotoRec: sudo apt-get install testdisk
- ImageMagick: sudo apt-get install imagemagick
- ExifTool: sudo apt-get install libimage-exiftool-perl

TIME ESTIMATES:
- 64GB HDD via USB 3.0: 2-4 hours
- 64GB SSD via USB 3.0: 1-2 hours
- Damaged media with bad sectors: 4-8 hours

================================================================================
"""