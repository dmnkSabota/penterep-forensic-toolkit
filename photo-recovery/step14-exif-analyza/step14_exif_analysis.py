#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-EXIF: EXIF metadát analýza obnovených fotografií
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript extrahuje a analyzuje EXIF metadáta zo všetkých obnovených fotografií
na vytvorenie timeline, identifikáciu zariadení a detekciu úprav.
"""

import subprocess
import json
import sys
import os
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False
    print("WARNING: ptlibs not found, using fallback output")


class EXIFAnalyzer:
    """
    EXIF analýza pre obnovené fotografie.
    
    Proces:
    1. Load master catalog from Step 13
    2. Extract EXIF data using ExifTool
    3. Analyze time information (DateTimeOriginal)
    4. Analyze cameras (Make, Model, SerialNumber)
    5. Analyze settings (ISO, aperture, focal length)
    6. Extract GPS coordinates
    7. Detect edited photos (Software tag)
    8. Detect anomalies
    9. Create timeline
    10. Generate comprehensive reports
    """
    
    # Software známe pre úpravy fotografií
    EDITING_SOFTWARE = {
        'photoshop', 'lightroom', 'gimp', 'affinity', 'capture one',
        'instagram', 'snapseed', 'vsco', 'facetune', 'pixelmator'
    }
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Načítanie master katalógu
        self.catalog = None
        self.catalog_path = self.output_dir / f"{case_id}_consolidated" / "master_catalog.json"
        
        # EXIF databáza
        self.exif_database = []
        
        # Štatistiky
        self.stats = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_files": 0,
            "files_with_exif": 0,
            "files_without_exif": 0,
            "with_datetime": 0,
            "with_gps": 0,
            "edited_photos": 0,
            "anomalies": 0,
            "unique_cameras": 0,
            "date_range": {
                "earliest": None,
                "latest": None,
                "span_days": 0
            },
            "cameras": {},
            "settings_range": {
                "iso": {"min": None, "max": None, "avg": None},
                "aperture": {"min": None, "max": None, "avg": None},
                "focal_length": {"min": None, "max": None, "avg": None}
            },
            "quality_score": None,
            "success": False
        }
        
        # Timeline
        self.timeline = defaultdict(list)
        
        # GPS coordinates
        self.gps_locations = []
    
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
    
    def _run_command(self, cmd, timeout=300):
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
    
    def load_master_catalog(self):
        """Načítanie master katalógu z Kroku 13"""
        self._print("\nLoading master catalog from Step 13...", "TITLE")
        
        if not self.catalog_path.exists():
            self._print(f"ERROR: Master catalog not found: {self.catalog_path}", "ERROR")
            self._print("Please run Step 13 (Consolidation) first!", "ERROR")
            return False
        
        try:
            with open(self.catalog_path, 'r', encoding='utf-8') as f:
                self.catalog = json.load(f)
            
            self.stats["total_files"] = self.catalog["summary"]["total_files"]
            
            self._print(f"Catalog loaded: {self.catalog_path.name}", "OK")
            self._print(f"Total files to analyze: {self.stats['total_files']}", "INFO")
            
            return True
            
        except Exception as e:
            self._print(f"ERROR loading catalog: {str(e)}", "ERROR")
            return False
    
    def check_exiftool(self):
        """Overte dostupnosť ExifTool"""
        self._print("\nChecking ExifTool...", "INFO")
        
        result = self._run_command(['which', 'exiftool'], timeout=5)
        
        if result["success"]:
            # Get version
            version_result = self._run_command(['exiftool', '-ver'], timeout=5)
            if version_result["success"]:
                self._print(f"ExifTool found: v{version_result['stdout']}", "OK")
            else:
                self._print("ExifTool found", "OK")
            return True
        else:
            self._print("ERROR: ExifTool not found", "ERROR")
            self._print("Install: sudo apt-get install libimage-exiftool-perl", "ERROR")
            return False
    
    def extract_exif_for_file(self, filepath):
        """
        Extrakcia EXIF pre jeden súbor pomocou ExifTool.
        
        Args:
            filepath: Path to image file
        
        Returns:
            Dictionary with EXIF data or None
        """
        # ExifTool command:
        # -j = JSON output
        # -G = group names
        # -a = allow duplicate tags
        # -s = short output
        # -n = numeric output (for GPS)
        cmd = ['exiftool', '-j', '-G', '-a', '-s', '-n', str(filepath)]
        
        result = self._run_command(cmd, timeout=30)
        
        if not result["success"]:
            return None
        
        try:
            exif_data = json.loads(result["stdout"])
            
            if exif_data and len(exif_data) > 0:
                return exif_data[0]
            else:
                return None
                
        except Exception as e:
            return None
    
    def parse_exif_data(self, raw_exif, file_info):
        """
        Parsovanie relevantných EXIF polí.
        
        Args:
            raw_exif: Raw EXIF dictionary from ExifTool
            file_info: File info from catalog
        
        Returns:
            Parsed EXIF dictionary
        """
        if not raw_exif:
            return None
        
        parsed = {
            "file_id": file_info["id"],
            "filename": file_info["filename"],
            "path": file_info["path"],
            
            # Camera identification
            "make": raw_exif.get("EXIF:Make") or raw_exif.get("IFD0:Make"),
            "model": raw_exif.get("EXIF:Model") or raw_exif.get("IFD0:Model"),
            "serial_number": raw_exif.get("EXIF:SerialNumber") or raw_exif.get("MakerNotes:SerialNumber"),
            
            # Date/Time
            "datetime_original": raw_exif.get("EXIF:DateTimeOriginal"),
            "create_date": raw_exif.get("EXIF:CreateDate"),
            "modify_date": raw_exif.get("EXIF:ModifyDate") or raw_exif.get("IFD0:ModifyDate"),
            
            # Camera settings
            "iso": raw_exif.get("EXIF:ISO"),
            "exposure_time": raw_exif.get("EXIF:ExposureTime"),
            "f_number": raw_exif.get("EXIF:FNumber") or raw_exif.get("EXIF:ApertureValue"),
            "focal_length": raw_exif.get("EXIF:FocalLength"),
            "flash": raw_exif.get("EXIF:Flash"),
            
            # Image properties
            "width": raw_exif.get("EXIF:ExifImageWidth") or raw_exif.get("File:ImageWidth"),
            "height": raw_exif.get("EXIF:ExifImageHeight") or raw_exif.get("File:ImageHeight"),
            "orientation": raw_exif.get("EXIF:Orientation") or raw_exif.get("IFD0:Orientation"),
            
            # GPS
            "gps_latitude": raw_exif.get("EXIF:GPSLatitude"),
            "gps_longitude": raw_exif.get("EXIF:GPSLongitude"),
            "gps_altitude": raw_exif.get("EXIF:GPSAltitude"),
            
            # Software
            "software": raw_exif.get("EXIF:Software") or raw_exif.get("IFD0:Software"),
            
            # Recovery metadata
            "recovery_method": file_info.get("recovery_method")
        }
        
        # Filter out None values
        return {k: v for k, v in parsed.items() if v is not None}
    
    def extract_all_exif(self):
        """
        FÁZA 1: Extrakcia EXIF pre všetky súbory.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("EXIF EXTRACTION PHASE", "TITLE")
        self._print("="*70, "TITLE")
        
        total = len(self.catalog["files"])
        
        self._print(f"\nExtracting EXIF from {total} files...", "INFO")
        
        for idx, file_info in enumerate(self.catalog["files"], 1):
            if idx % 50 == 0 or idx == total:
                self._print(f"Progress: {idx}/{total} ({idx*100//total}%)", "INFO")
            
            # Construct full path
            consolidated_dir = self.output_dir / f"{self.case_id}_consolidated"
            filepath = consolidated_dir / file_info["path"]
            
            if not filepath.exists():
                self._print(f"File not found: {filepath}", "WARNING")
                continue
            
            # Extract EXIF
            raw_exif = self.extract_exif_for_file(filepath)
            
            if raw_exif:
                parsed = self.parse_exif_data(raw_exif, file_info)
                
                if parsed and len(parsed) > 4:  # More than just file_id, filename, path, recovery_method
                    self.exif_database.append(parsed)
                    self.stats["files_with_exif"] += 1
                else:
                    self.stats["files_without_exif"] += 1
            else:
                self.stats["files_without_exif"] += 1
        
        self._print(f"\nEXIF extraction completed", "OK")
        self._print(f"Files with EXIF: {self.stats['files_with_exif']}", "OK")
        self._print(f"Files without EXIF: {self.stats['files_without_exif']}", "WARNING")
        
        if self.stats["files_with_exif"] == 0:
            self._print("ERROR: No EXIF data found!", "ERROR")
            return False
        
        return True
    
    def analyze_time_information(self):
        """
        FÁZA 2: Analýza časových informácií.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("TIME ANALYSIS", "TITLE")
        self._print("="*70, "TITLE")
        
        dates = []
        
        for exif in self.exif_database:
            datetime_str = exif.get("datetime_original") or exif.get("create_date")
            
            if datetime_str:
                try:
                    # EXIF format: "2025:01:15 14:30:22"
                    dt = datetime.strptime(datetime_str, "%Y:%m:%d %H:%M:%S")
                    dates.append(dt)
                    
                    # Add to timeline
                    date_key = dt.strftime("%Y-%m-%d")
                    self.timeline[date_key].append({
                        "filename": exif["filename"],
                        "time": dt.strftime("%H:%M:%S"),
                        "camera": f"{exif.get('make', 'Unknown')} {exif.get('model', '')}"
                    })
                    
                    exif["parsed_datetime"] = dt.isoformat()
                    self.stats["with_datetime"] += 1
                    
                except Exception as e:
                    pass
        
        if dates:
            earliest = min(dates)
            latest = max(dates)
            span = (latest - earliest).days
            
            self.stats["date_range"]["earliest"] = earliest.strftime("%Y-%m-%d %H:%M:%S")
            self.stats["date_range"]["latest"] = latest.strftime("%Y-%m-%d %H:%M:%S")
            self.stats["date_range"]["span_days"] = span
            
            self._print(f"Photos with datetime: {self.stats['with_datetime']}", "OK")
            self._print(f"Date range: {earliest.strftime('%Y-%m-%d')} to {latest.strftime('%Y-%m-%d')}", "INFO")
            self._print(f"Time span: {span} days", "INFO")
        else:
            self._print("No datetime information found", "WARNING")
    
    def analyze_cameras(self):
        """
        FÁZA 3: Analýza fotoaparátov a zariadení.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("CAMERA ANALYSIS", "TITLE")
        self._print("="*70, "TITLE")
        
        cameras = Counter()
        
        for exif in self.exif_database:
            make = exif.get("make", "Unknown")
            model = exif.get("model", "Unknown")
            
            camera_key = f"{make} {model}".strip()
            cameras[camera_key] += 1
        
        self.stats["unique_cameras"] = len(cameras)
        self.stats["cameras"] = dict(cameras.most_common())
        
        self._print(f"Unique cameras: {len(cameras)}", "OK")
        self._print("Top cameras:", "INFO")
        
        for camera, count in cameras.most_common(5):
            percentage = (count / self.stats["files_with_exif"]) * 100
            self._print(f"  {camera}: {count} ({percentage:.1f}%)", "INFO")
    
    def analyze_settings(self):
        """
        FÁZA 4: Analýza nastavení fotoaparátu a GPS.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("SETTINGS AND GPS ANALYSIS", "TITLE")
        self._print("="*70, "TITLE")
        
        iso_values = []
        aperture_values = []
        focal_length_values = []
        
        for exif in self.exif_database:
            # ISO
            if "iso" in exif:
                try:
                    iso = int(exif["iso"])
                    iso_values.append(iso)
                except:
                    pass
            
            # Aperture (F-number)
            if "f_number" in exif:
                try:
                    aperture = float(exif["f_number"])
                    aperture_values.append(aperture)
                except:
                    pass
            
            # Focal length
            if "focal_length" in exif:
                try:
                    # Може být "85 mm" nebo jen "85"
                    focal_str = str(exif["focal_length"]).replace("mm", "").strip()
                    focal = float(focal_str)
                    focal_length_values.append(focal)
                except:
                    pass
            
            # GPS
            if "gps_latitude" in exif and "gps_longitude" in exif:
                try:
                    lat = float(exif["gps_latitude"])
                    lon = float(exif["gps_longitude"])
                    
                    self.gps_locations.append({
                        "filename": exif["filename"],
                        "latitude": lat,
                        "longitude": lon,
                        "altitude": exif.get("gps_altitude")
                    })
                    
                    self.stats["with_gps"] += 1
                except:
                    pass
        
        # Calculate statistics
        if iso_values:
            self.stats["settings_range"]["iso"] = {
                "min": min(iso_values),
                "max": max(iso_values),
                "avg": round(sum(iso_values) / len(iso_values), 1)
            }
        
        if aperture_values:
            self.stats["settings_range"]["aperture"] = {
                "min": round(min(aperture_values), 1),
                "max": round(max(aperture_values), 1),
                "avg": round(sum(aperture_values) / len(aperture_values), 1)
            }
        
        if focal_length_values:
            self.stats["settings_range"]["focal_length"] = {
                "min": round(min(focal_length_values), 1),
                "max": round(max(focal_length_values), 1),
                "avg": round(sum(focal_length_values) / len(focal_length_values), 1)
            }
        
        self._print(f"Photos with GPS: {self.stats['with_gps']}", "OK" if self.stats['with_gps'] > 0 else "INFO")
        
        if iso_values:
            self._print(f"ISO range: {min(iso_values)} - {max(iso_values)}", "INFO")
        if aperture_values:
            self._print(f"Aperture range: f/{min(aperture_values)} - f/{max(aperture_values)}", "INFO")
        if focal_length_values:
            self._print(f"Focal length range: {min(focal_length_values)}mm - {max(focal_length_values)}mm", "INFO")
    
    def detect_edits_and_anomalies(self):
        """
        FÁZA 5: Detekcia upravených fotografií a anomálií.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("EDIT DETECTION AND ANOMALY ANALYSIS", "TITLE")
        self._print("="*70, "TITLE")
        
        edited_photos = []
        anomalies = []
        
        for exif in self.exif_database:
            # Check for editing software
            software = exif.get("software", "").lower()
            
            if software and any(edit_sw in software for edit_sw in self.EDITING_SOFTWARE):
                edited_photos.append({
                    "filename": exif["filename"],
                    "software": exif["software"]
                })
                self.stats["edited_photos"] += 1
                exif["edited"] = True
            
            # Check for anomalies
            
            # Anomaly 1: Future date
            if "parsed_datetime" in exif:
                try:
                    photo_date = datetime.fromisoformat(exif["parsed_datetime"])
                    if photo_date > datetime.now():
                        anomalies.append({
                            "filename": exif["filename"],
                            "type": "future_date",
                            "detail": f"Date in future: {photo_date.strftime('%Y-%m-%d')}"
                        })
                        self.stats["anomalies"] += 1
                except:
                    pass
            
            # Anomaly 2: Unusual ISO (>25600)
            if "iso" in exif:
                try:
                    iso = int(exif["iso"])
                    if iso > 25600:
                        anomalies.append({
                            "filename": exif["filename"],
                            "type": "unusual_iso",
                            "detail": f"ISO {iso} (unusually high)"
                        })
                        self.stats["anomalies"] += 1
                except:
                    pass
        
        self._print(f"Edited photos detected: {self.stats['edited_photos']}", "INFO")
        self._print(f"Anomalies detected: {self.stats['anomalies']}", "WARNING" if self.stats['anomalies'] > 0 else "INFO")
        
        # Store for report
        self.edited_photos = edited_photos
        self.anomalies = anomalies
    
    def calculate_quality_score(self):
        """
        Výpočet EXIF quality score.
        """
        if self.stats["total_files"] == 0:
            return
        
        datetime_percentage = (self.stats["with_datetime"] / self.stats["total_files"]) * 100
        
        if datetime_percentage >= 90:
            quality = "excellent"
        elif datetime_percentage >= 70:
            quality = "good"
        elif datetime_percentage >= 50:
            quality = "fair"
        else:
            quality = "poor"
        
        self.stats["quality_score"] = {
            "score": quality,
            "datetime_percentage": round(datetime_percentage, 1)
        }
    
    def run_analysis(self):
        """Hlavná funkcia - spustí celú EXIF analýzu"""
        
        self._print("="*70, "TITLE")
        self._print("EXIF METADATA ANALYSIS", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Load master catalog
        if not self.load_master_catalog():
            self.stats["success"] = False
            return self.stats
        
        # 2. Check ExifTool
        if not self.check_exiftool():
            self.stats["success"] = False
            return self.stats
        
        # 3. Extract EXIF
        if not self.extract_all_exif():
            self.stats["success"] = False
            return self.stats
        
        # 4. Analyze time information
        self.analyze_time_information()
        
        # 5. Analyze cameras
        self.analyze_cameras()
        
        # 6. Analyze settings and GPS
        self.analyze_settings()
        
        # 7. Detect edits and anomalies
        self.detect_edits_and_anomalies()
        
        # 8. Calculate quality score
        self.calculate_quality_score()
        
        # 9. Summary
        self._print("\n" + "="*70, "TITLE")
        self._print("EXIF ANALYSIS COMPLETED", "OK")
        self._print("="*70, "TITLE")
        
        self._print(f"Total files analyzed: {self.stats['total_files']}", "INFO")
        self._print(f"Files with EXIF: {self.stats['files_with_exif']}", "OK")
        self._print(f"Files with datetime: {self.stats['with_datetime']}", "OK")
        self._print(f"Files with GPS: {self.stats['with_gps']}", "INFO")
        self._print(f"Quality score: {self.stats['quality_score']['score'].upper()} ({self.stats['quality_score']['datetime_percentage']}%)", "OK")
        
        self._print("="*70 + "\n", "TITLE")
        
        self.stats["success"] = True
        
        return self.stats
    
    def save_reports(self):
        """Uloženie reportov"""
        
        output_base = self.output_dir / f"{self.case_id}_exif_analysis"
        output_base.mkdir(parents=True, exist_ok=True)
        
        # 1. JSON database
        json_file = output_base / "exif_database.json"
        
        database = {
            "case_id": self.case_id,
            "timestamp": self.stats["timestamp"],
            "statistics": self.stats,
            "exif_data": self.exif_database,
            "timeline": dict(self.timeline),
            "gps_locations": self.gps_locations
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(database, f, indent=2, ensure_ascii=False)
        
        self._print(f"JSON database saved: {json_file.name}", "OK")
        
        # 2. CSV export
        csv_file = output_base / "exif_data.csv"
        
        if self.exif_database:
            # Get all possible keys
            all_keys = set()
            for exif in self.exif_database:
                all_keys.update(exif.keys())
            
            fieldnames = sorted(all_keys)
            
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.exif_database)
            
            self._print(f"CSV export saved: {csv_file.name}", "OK")
        
        # 3. Text report
        text_report = output_base / "EXIF_REPORT.txt"
        
        with open(text_report, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("EXIF METADATA ANALYSIS REPORT\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"Case ID: {self.case_id}\n")
            f.write(f"Timestamp: {self.stats['timestamp']}\n\n")
            
            f.write("SUMMARY:\n")
            f.write(f"  Total files: {self.stats['total_files']}\n")
            f.write(f"  Files with EXIF: {self.stats['files_with_exif']}\n")
            f.write(f"  Files without EXIF: {self.stats['files_without_exif']}\n")
            f.write(f"  Files with datetime: {self.stats['with_datetime']}\n")
            f.write(f"  Files with GPS: {self.stats['with_gps']}\n\n")
            
            f.write("QUALITY SCORE:\n")
            f.write(f"  Score: {self.stats['quality_score']['score'].upper()}\n")
            f.write(f"  DateTime coverage: {self.stats['quality_score']['datetime_percentage']}%\n\n")
            
            if self.stats["date_range"]["earliest"]:
                f.write("DATE RANGE:\n")
                f.write(f"  Earliest: {self.stats['date_range']['earliest']}\n")
                f.write(f"  Latest: {self.stats['date_range']['latest']}\n")
                f.write(f"  Span: {self.stats['date_range']['span_days']} days\n\n")
            
            f.write("CAMERAS:\n")
            f.write(f"  Unique cameras: {self.stats['unique_cameras']}\n")
            for camera, count in list(self.stats['cameras'].items())[:10]:
                percentage = (count / self.stats['files_with_exif']) * 100
                f.write(f"  {camera}: {count} ({percentage:.1f}%)\n")
            f.write("\n")
            
            if self.stats["settings_range"]["iso"]["min"]:
                f.write("CAMERA SETTINGS:\n")
                iso = self.stats["settings_range"]["iso"]
                f.write(f"  ISO: {iso['min']} - {iso['max']} (avg: {iso['avg']})\n")
                
                if self.stats["settings_range"]["aperture"]["min"]:
                    aperture = self.stats["settings_range"]["aperture"]
                    f.write(f"  Aperture: f/{aperture['min']} - f/{aperture['max']} (avg: f/{aperture['avg']})\n")
                
                if self.stats["settings_range"]["focal_length"]["min"]:
                    focal = self.stats["settings_range"]["focal_length"]
                    f.write(f"  Focal length: {focal['min']}mm - {focal['max']}mm (avg: {focal['avg']}mm)\n")
                f.write("\n")
            
            f.write(f"EDITED PHOTOS: {self.stats['edited_photos']}\n")
            f.write(f"ANOMALIES: {self.stats['anomalies']}\n\n")
            
            if self.timeline:
                f.write("TIMELINE (by date):\n")
                for date in sorted(self.timeline.keys())[:20]:  # First 20 days
                    count = len(self.timeline[date])
                    f.write(f"  {date}: {count} photos\n")
                f.write("\n")
            
            if self.gps_locations:
                f.write(f"GPS LOCATIONS: {len(self.gps_locations)} photos\n")
                for loc in self.gps_locations[:10]:  # First 10
                    f.write(f"  {loc['filename']}: {loc['latitude']:.6f}, {loc['longitude']:.6f}\n")
        
        self._print(f"Text report saved: {text_report.name}", "OK")
        
        return str(json_file)


def main():
    """
    Hlavná funkcia - entry point pre Penterep platformu
    """
    
    print("\n" + "="*70)
    print("FOR-COL-EXIF: EXIF Metadata Analysis")
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
    
    # Spustenie analýzy
    analyzer = EXIFAnalyzer(case_id)
    results = analyzer.run_analysis()
    
    # Uloženie reportov
    if results["success"]:
        report_path = analyzer.save_reports()
        print(f"\nEXIF analysis completed successfully")
        print(f"Quality score: {results['quality_score']['score'].upper()} ({results['quality_score']['datetime_percentage']}%)")
        print(f"Files with datetime: {results['with_datetime']}/{results['total_files']}")
        print(f"Files with GPS: {results['with_gps']}")
        print(f"Next step: Step 15 (Validation)")
        sys.exit(0)
    else:
        print("\nEXIF analysis failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - KEY FEATURES
================================================================================

EXIF METADATA ANALYSIS
- Extracts EXIF data using ExifTool (most comprehensive tool)
- Analyzes 7 categories of metadata
- Creates timeline and GPS location list
- Detects edited photos and anomalies
- Generates quality score

SEVEN ANALYSIS CATEGORIES
1. Time Information
   - DateTimeOriginal / CreateDate
   - Date range (earliest to latest)
   - Timeline by date
   
2. Camera Identification
   - Make and Model
   - Serial numbers
   - Device distribution
   
3. Camera Settings
   - ISO range
   - Aperture (F-number) range
   - Focal length range
   
4. GPS Coordinates
   - Latitude/Longitude extraction
   - Location list for mapping
   - Altitude if available
   
5. Edit Detection
   - Software tags (Photoshop, Lightroom, etc.)
   - Modified photos identification
   
6. Anomaly Detection
   - Future dates
   - Unusual ISO values (>25600)
   - Missing critical EXIF
   
7. Quality Scoring
   - Excellent: >90% with DateTime
   - Good: 70-90%
   - Fair: 50-70%
   - Poor: <50%

INTEGRATION WITH STEP 13
- Reads master_catalog.json automatically
- Analyzes all consolidated files
- No manual file path input needed

OUTPUT FORMATS
1. JSON database (complete EXIF data)
2. CSV export (for Excel analysis)
3. Text report (human-readable summary)
4. Timeline data (organized by date)
5. GPS locations list (for mapping)

================================================================================
EXAMPLE OUTPUT
================================================================================

======================================================================
EXIF METADATA ANALYSIS
Case ID: PHOTO-2025-01-26-001
======================================================================

Loading master catalog from Step 13...
[✓] Catalog loaded: master_catalog.json
[i] Total files to analyze: 692

Checking ExifTool...
[✓] ExifTool found: v12.40

======================================================================
EXIF EXTRACTION PHASE
======================================================================

Extracting EXIF from 692 files...
[i] Progress: 692/692 (100%)

[✓] EXIF extraction completed
[✓] Files with EXIF: 623
[!] Files without EXIF: 69

======================================================================
TIME ANALYSIS
======================================================================

[✓] Photos with datetime: 589
[i] Date range: 2024-03-12 to 2026-01-18
[i] Time span: 312 days

======================================================================
CAMERA ANALYSIS
======================================================================

[✓] Unique cameras: 7
Top cameras:
[i]   Canon EOS 5D Mark IV: 234 (37.6%)
[i]   iPhone 13 Pro: 189 (30.3%)
[i]   Samsung Galaxy S21: 134 (21.5%)
[i]   Nikon D850: 45 (7.2%)
[i]   Unknown Unknown: 21 (3.4%)

======================================================================
SETTINGS AND GPS ANALYSIS
======================================================================

[✓] Photos with GPS: 312
[i] ISO range: 100 - 6400
[i] Aperture range: f/1.8 - f/22.0
[i] Focal length range: 24.0mm - 200.0mm

======================================================================
EDIT DETECTION AND ANOMALY ANALYSIS
======================================================================

[i] Edited photos detected: 67
[i] Anomalies detected: 3

======================================================================
EXIF ANALYSIS COMPLETED
======================================================================
[i] Total files analyzed: 692
[✓] Files with EXIF: 623
[✓] Files with datetime: 589
[i] Files with GPS: 312
[✓] Quality score: EXCELLENT (85.1%)
======================================================================

EXIF analysis completed successfully
Quality score: EXCELLENT (85.1%)
Files with datetime: 589/692
Files with GPS: 312

================================================================================
USAGE
================================================================================

INTERACTIVE MODE:
$ python3 step14_exif_analysis.py
Case ID: PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step14_exif_analysis.py PHOTO-2025-01-26-001

REQUIREMENTS:
- Step 13 (Consolidation) must be completed
- ExifTool: sudo apt-get install libimage-exiftool-perl
- Python 3 with json, csv modules

TIME ESTIMATE:
- ~5-30 minutes depending on number of files
- ExifTool is fast (~100 files/second)

================================================================================
QUALITY SCORE INTERPRETATION
================================================================================

EXCELLENT (>90%):
- Most photos have datetime information
- Successful recovery with good metadata preservation
- Ready for detailed timeline analysis

GOOD (70-90%):
- Majority have datetime
- Some metadata loss (expected with file carving)
- Still useful for analysis

FAIR (50-70%):
- Partial datetime coverage
- Significant metadata loss
- Limited timeline analysis possible

POOR (<50%):
- Most photos missing datetime
- Heavy metadata loss
- File carving from badly damaged media

================================================================================
"""