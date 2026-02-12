#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-VALIDATE: Validácia integrity obnovených fotografií
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript validuje fyzickú integritu všetkých obnovených fotografií
a kategorizuje ich na validné, poškodené (opraviteľné) a neopraviteľné.
"""

import subprocess
import json
import sys
import os
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: PIL/Pillow not found")

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False
    print("WARNING: ptlibs not found, using fallback output")


class IntegrityValidator:
    """
    Validácia integrity obnovených fotografií.
    
    Proces:
    1. Load master catalog from Step 13
    2. Validate magic bytes (file signatures)
    3. Run multi-tool validation (file, identify, PIL)
    4. Detect corruption types
    5. Assess repairability
    6. Categorize files (valid/corrupted/unrecoverable)
    7. Organize into directories
    8. Generate comprehensive reports
    """
    
    # Magic bytes pre obrazové formáty
    MAGIC_BYTES = {
        'JPEG': [b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1', b'\xff\xd8\xff\xe2', b'\xff\xd8\xff\xe8'],
        'PNG': [b'\x89\x50\x4e\x47\x0d\x0a\x1a\x0a'],
        'GIF': [b'GIF87a', b'GIF89a'],
        'TIFF': [b'\x49\x49\x2a\x00', b'\x4d\x4d\x00\x2a'],
        'BMP': [b'BM'],
        'WEBP': [b'RIFF']
    }
    
    # Corruption types a ich opraviteľnosť
    CORRUPTION_TYPES = {
        'truncated': {'level': 1, 'repairable': True, 'technique': 'Add missing footer'},
        'invalid_header': {'level': 2, 'repairable': True, 'technique': 'Fix header bytes'},
        'corrupt_segments': {'level': 2, 'repairable': True, 'technique': 'Remove corrupt segments'},
        'corrupt_data': {'level': 3, 'repairable': 'partial', 'technique': 'Partial recovery possible'},
        'fragmented': {'level': 4, 'repairable': False, 'technique': 'Defragmentation needed'},
        'false_positive': {'level': 5, 'repairable': False, 'technique': 'Not an image file'}
    }
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Katalóg
        self.catalog = None
        self.catalog_path = self.output_dir / f"{case_id}_consolidated" / "master_catalog.json"
        
        # Výstupné adresáre
        self.validation_base = self.output_dir / f"{case_id}_validation"
        self.valid_dir = self.validation_base / "valid"
        self.corrupted_dir = self.validation_base / "corrupted"
        self.unrecoverable_dir = self.validation_base / "unrecoverable"
        
        # Štatistiky
        self.stats = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_files": 0,
            "valid_files": 0,
            "corrupted_files": 0,
            "unrecoverable_files": 0,
            "integrity_score": 0.0,
            "by_format": {},
            "by_source": {},
            "corruption_types": {},
            "success": False
        }
        
        # Validation results
        self.validation_results = []
        self.files_needing_repair = []
    
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
    
    def _run_command(self, cmd, timeout=30):
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
            self._print(f"Total files to validate: {self.stats['total_files']}", "INFO")
            
            return True
            
        except Exception as e:
            self._print(f"ERROR loading catalog: {str(e)}", "ERROR")
            return False
    
    def check_tools(self):
        """Overte dostupnosť validačných nástrojov"""
        self._print("\nChecking validation tools...", "INFO")
        
        tools_status = {}
        
        # ImageMagick identify
        result = self._run_command(['which', 'identify'], timeout=5)
        if result["success"]:
            self._print("ImageMagick identify: Found", "OK")
            tools_status['imagemagick'] = True
        else:
            self._print("ImageMagick identify: NOT FOUND (optional)", "WARNING")
            tools_status['imagemagick'] = False
        
        # PIL/Pillow
        if PIL_AVAILABLE:
            self._print("PIL/Pillow: Found", "OK")
            tools_status['pil'] = True
        else:
            self._print("PIL/Pillow: NOT FOUND", "ERROR")
            self._print("Install: pip install Pillow --break-system-packages", "ERROR")
            tools_status['pil'] = False
            return False
        
        # file command
        result = self._run_command(['which', 'file'], timeout=5)
        if result["success"]:
            self._print("file command: Found", "OK")
            tools_status['file'] = True
        else:
            self._print("file command: NOT FOUND (optional)", "WARNING")
            tools_status['file'] = False
        
        self.tools_status = tools_status
        return True
    
    def prepare_directories(self):
        """Vytvorenie výstupných adresárov"""
        self._print("\nPreparing validation directories...", "INFO")
        
        for directory in [self.valid_dir, self.corrupted_dir, self.unrecoverable_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        return True
    
    def check_magic_bytes(self, filepath, expected_format):
        """
        Kontrola magic bytes (file signature).
        
        Args:
            filepath: Path to file
            expected_format: Expected format (JPEG, PNG, etc.)
        
        Returns:
            Boolean
        """
        try:
            with open(filepath, 'rb') as f:
                header = f.read(16)  # Read first 16 bytes
            
            if expected_format.upper() in self.MAGIC_BYTES:
                valid_signatures = self.MAGIC_BYTES[expected_format.upper()]
                
                for signature in valid_signatures:
                    if header.startswith(signature):
                        return True
            
            return False
            
        except Exception:
            return False
    
    def validate_with_file_command(self, filepath):
        """Validácia pomocou file command"""
        if not self.tools_status.get('file'):
            return None
        
        result = self._run_command(['file', '-b', '--mime-type', str(filepath)], timeout=10)
        
        if result["success"]:
            mime_type = result["stdout"]
            
            if mime_type.startswith('image/'):
                return {'success': True, 'mime_type': mime_type}
            else:
                return {'success': False, 'error': f'Not an image: {mime_type}'}
        
        return None
    
    def validate_with_imagemagick(self, filepath):
        """Validácia pomocou ImageMagick identify"""
        if not self.tools_status.get('imagemagick'):
            return None
        
        result = self._run_command(['identify', '-verbose', str(filepath)], timeout=30)
        
        if result["success"]:
            # Extract dimensions
            try:
                output = result["stdout"]
                
                # Look for Geometry or dimensions
                for line in output.split('\n'):
                    if 'Geometry:' in line:
                        return {'success': True, 'tool': 'imagemagick'}
                
                return {'success': True, 'tool': 'imagemagick'}
                
            except:
                return {'success': True, 'tool': 'imagemagick'}
        else:
            error_msg = result["stderr"]
            return {'success': False, 'error': error_msg, 'tool': 'imagemagick'}
    
    def validate_with_pil(self, filepath):
        """Validácia pomocou PIL/Pillow"""
        try:
            # Open and verify
            img = Image.open(filepath)
            img.verify()
            
            # Reopen after verify (verify closes the file)
            img = Image.open(filepath)
            
            # Try to load all data
            img.load()
            
            width, height = img.size
            
            if width == 0 or height == 0:
                return {
                    'success': False,
                    'error': 'Invalid dimensions (0x0)',
                    'tool': 'pil'
                }
            
            return {
                'success': True,
                'tool': 'pil',
                'width': width,
                'height': height,
                'mode': img.mode
            }
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Detect corruption type from error message
            if 'truncated' in error_str or 'premature end' in error_str:
                corruption_type = 'truncated'
            elif 'cannot identify' in error_str or 'cannot decode' in error_str:
                corruption_type = 'invalid_header'
            elif 'corrupt' in error_str or 'broken' in error_str:
                corruption_type = 'corrupt_data'
            else:
                corruption_type = 'unknown'
            
            return {
                'success': False,
                'error': str(e),
                'corruption_type': corruption_type,
                'tool': 'pil'
            }
    
    def validate_single_file(self, file_info):
        """
        Validácia jedného súboru s multi-tool approach.
        
        Args:
            file_info: File info from catalog
        
        Returns:
            Validation result dictionary
        """
        # Construct full path
        consolidated_dir = self.output_dir / f"{self.case_id}_consolidated"
        filepath = consolidated_dir / file_info["path"]
        
        if not filepath.exists():
            return {
                'status': 'unrecoverable',
                'error': 'File not found',
                'tools_passed': 0,
                'tools_failed': 3
            }
        
        # Get file size
        file_size = filepath.stat().st_size
        
        if file_size == 0:
            return {
                'status': 'unrecoverable',
                'error': 'Empty file (0 bytes)',
                'tools_passed': 0,
                'tools_failed': 3
            }
        
        # Check magic bytes
        format_key = file_info.get('format', '').upper()
        magic_valid = self.check_magic_bytes(filepath, format_key)
        
        # Run validators
        tools_results = []
        
        # 1. file command
        file_result = self.validate_with_file_command(filepath)
        if file_result:
            tools_results.append(file_result)
        
        # 2. ImageMagick
        im_result = self.validate_with_imagemagick(filepath)
        if im_result:
            tools_results.append(im_result)
        
        # 3. PIL (always run)
        pil_result = self.validate_with_pil(filepath)
        tools_results.append(pil_result)
        
        # Count successes
        tools_passed = sum(1 for r in tools_results if r.get('success'))
        tools_total = len(tools_results)
        
        # Decision logic
        validation_result = {
            'file_size': file_size,
            'magic_bytes_valid': magic_valid,
            'tools_passed': tools_passed,
            'tools_total': tools_total,
            'tools_results': tools_results
        }
        
        if tools_passed == tools_total and magic_valid:
            # All tools passed
            validation_result['status'] = 'valid'
            
            # Extract details from PIL
            if pil_result.get('success'):
                validation_result['width'] = pil_result.get('width')
                validation_result['height'] = pil_result.get('height')
                validation_result['mode'] = pil_result.get('mode')
        
        elif tools_passed > 0:
            # At least one tool passed - corrupted but potentially repairable
            validation_result['status'] = 'corrupted'
            
            # Detect corruption type
            for result in tools_results:
                if not result.get('success') and 'corruption_type' in result:
                    validation_result['corruption_type'] = result['corruption_type']
                    break
            
            if 'corruption_type' not in validation_result:
                validation_result['corruption_type'] = 'unknown'
            
            # Check if magic bytes are invalid
            if not magic_valid:
                validation_result['corruption_type'] = 'invalid_header'
            
            # Get error messages
            errors = [r.get('error', '') for r in tools_results if not r.get('success')]
            validation_result['errors'] = errors
        
        else:
            # All tools failed - unrecoverable
            validation_result['status'] = 'unrecoverable'
            validation_result['corruption_type'] = 'false_positive'
            
            errors = [r.get('error', '') for r in tools_results if not r.get('success')]
            validation_result['errors'] = errors
        
        return validation_result
    
    def assess_repairability(self, validation_result):
        """Posúdenie opraviteľnosti poškodeného súboru"""
        if validation_result['status'] == 'valid':
            return None
        
        corruption_type = validation_result.get('corruption_type', 'unknown')
        
        if corruption_type in self.CORRUPTION_TYPES:
            repair_info = self.CORRUPTION_TYPES[corruption_type]
            
            return {
                'corruption_type': corruption_type,
                'level': repair_info['level'],
                'repairable': repair_info['repairable'],
                'technique': repair_info['technique']
            }
        else:
            return {
                'corruption_type': corruption_type,
                'level': 3,
                'repairable': 'unknown',
                'technique': 'Manual inspection needed'
            }
    
    def validate_all_files(self):
        """
        Validácia všetkých súborov z katalógu.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("FILE VALIDATION PHASE", "TITLE")
        self._print("="*70, "TITLE")
        
        total = len(self.catalog["files"])
        
        self._print(f"\nValidating {total} files...", "INFO")
        
        for idx, file_info in enumerate(self.catalog["files"], 1):
            if idx % 50 == 0 or idx == total:
                self._print(f"Progress: {idx}/{total} ({idx*100//total}%)", "INFO")
            
            # Validate file
            validation = self.validate_single_file(file_info)
            
            # Build result entry
            result_entry = {
                'file_id': file_info['id'],
                'filename': file_info['filename'],
                'path': file_info['path'],
                'format': file_info.get('format'),
                'recovery_method': file_info.get('recovery_method'),
                'status': validation['status'],
                'file_size': validation.get('file_size'),
                'magic_bytes_valid': validation.get('magic_bytes_valid'),
                'tools_passed': validation.get('tools_passed'),
                'tools_total': validation.get('tools_total')
            }
            
            # Add details based on status
            if validation['status'] == 'valid':
                result_entry['width'] = validation.get('width')
                result_entry['height'] = validation.get('height')
                result_entry['mode'] = validation.get('mode')
                
                self.stats['valid_files'] += 1
            
            elif validation['status'] == 'corrupted':
                result_entry['corruption_type'] = validation.get('corruption_type')
                result_entry['errors'] = validation.get('errors')
                
                # Assess repairability
                repair_info = self.assess_repairability(validation)
                if repair_info:
                    result_entry['repair_info'] = repair_info
                    
                    if repair_info['repairable']:
                        self.files_needing_repair.append({
                            'file_id': file_info['id'],
                            'filename': file_info['filename'],
                            'corruption_type': repair_info['corruption_type'],
                            'technique': repair_info['technique']
                        })
                
                self.stats['corrupted_files'] += 1
                
                # Track corruption types
                corruption_type = validation.get('corruption_type', 'unknown')
                self.stats['corruption_types'][corruption_type] = \
                    self.stats['corruption_types'].get(corruption_type, 0) + 1
            
            else:  # unrecoverable
                result_entry['errors'] = validation.get('errors')
                
                self.stats['unrecoverable_files'] += 1
            
            # Track by format and source
            fmt = file_info.get('format', 'unknown')
            source = file_info.get('recovery_method', 'unknown')
            
            if fmt not in self.stats['by_format']:
                self.stats['by_format'][fmt] = {'total': 0, 'valid': 0, 'corrupted': 0}
            
            self.stats['by_format'][fmt]['total'] += 1
            if validation['status'] == 'valid':
                self.stats['by_format'][fmt]['valid'] += 1
            elif validation['status'] == 'corrupted':
                self.stats['by_format'][fmt]['corrupted'] += 1
            
            if source not in self.stats['by_source']:
                self.stats['by_source'][source] = {'total': 0, 'valid': 0, 'corrupted': 0}
            
            self.stats['by_source'][source]['total'] += 1
            if validation['status'] == 'valid':
                self.stats['by_source'][source]['valid'] += 1
            elif validation['status'] == 'corrupted':
                self.stats['by_source'][source]['corrupted'] += 1
            
            self.validation_results.append(result_entry)
        
        # Calculate integrity score
        if self.stats['total_files'] > 0:
            self.stats['integrity_score'] = round(
                (self.stats['valid_files'] / self.stats['total_files']) * 100, 2
            )
        
        self._print(f"\nValidation completed", "OK")
        self._print(f"Valid files: {self.stats['valid_files']}", "OK")
        self._print(f"Corrupted files: {self.stats['corrupted_files']}", "WARNING")
        self._print(f"Unrecoverable files: {self.stats['unrecoverable_files']}", "ERROR")
        self._print(f"Integrity score: {self.stats['integrity_score']}%", "OK")
    
    def organize_files(self):
        """
        Organizácia súborov do kategórií.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("ORGANIZING FILES BY STATUS", "TITLE")
        self._print("="*70, "TITLE")
        
        consolidated_dir = self.output_dir / f"{self.case_id}_consolidated"
        
        for result in self.validation_results:
            source_path = consolidated_dir / result['path']
            
            if not source_path.exists():
                continue
            
            # Determine target directory
            if result['status'] == 'valid':
                target_dir = self.valid_dir
            elif result['status'] == 'corrupted':
                target_dir = self.corrupted_dir
            else:
                target_dir = self.unrecoverable_dir
            
            # Copy file
            target_path = target_dir / result['filename']
            
            # Handle name collisions
            if target_path.exists():
                stem = target_path.stem
                suffix = target_path.suffix
                counter = 1
                while target_path.exists():
                    target_path = target_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            
            try:
                shutil.copy2(source_path, target_path)
            except Exception as e:
                self._print(f"Error copying {result['filename']}: {str(e)}", "WARNING")
        
        self._print(f"Files organized into validation directories", "OK")
    
    def run_validation(self):
        """Hlavná funkcia - spustí celú validáciu"""
        
        self._print("="*70, "TITLE")
        self._print("PHOTO INTEGRITY VALIDATION", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Load catalog
        if not self.load_master_catalog():
            self.stats["success"] = False
            return self.stats
        
        # 2. Check tools
        if not self.check_tools():
            self.stats["success"] = False
            return self.stats
        
        # 3. Prepare directories
        self.prepare_directories()
        
        # 4. Validate all files
        self.validate_all_files()
        
        # 5. Organize files
        self.organize_files()
        
        # 6. Summary
        self._print("\n" + "="*70, "TITLE")
        self._print("VALIDATION COMPLETED", "OK")
        self._print("="*70, "TITLE")
        
        self._print(f"Total files: {self.stats['total_files']}", "INFO")
        self._print(f"Valid: {self.stats['valid_files']}", "OK")
        self._print(f"Corrupted: {self.stats['corrupted_files']}", "WARNING")
        self._print(f"Unrecoverable: {self.stats['unrecoverable_files']}", "ERROR")
        self._print(f"Integrity score: {self.stats['integrity_score']}%", "OK")
        
        if self.files_needing_repair:
            self._print(f"Files needing repair: {len(self.files_needing_repair)}", "INFO")
        
        self._print("="*70 + "\n", "TITLE")
        
        self.stats["success"] = True
        
        return self.stats
    
    def save_reports(self):
        """Uloženie reportov"""
        
        # 1. JSON report
        report_file = self.output_dir / f"{self.case_id}_validation_report.json"
        
        report = {
            "statistics": self.stats,
            "validation_results": self.validation_results,
            "files_needing_repair": self.files_needing_repair
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self._print(f"Validation report saved: {report_file}", "OK")
        
        # 2. Text report
        text_report = self.validation_base / "VALIDATION_REPORT.txt"
        
        with open(text_report, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("PHOTO INTEGRITY VALIDATION REPORT\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"Case ID: {self.case_id}\n")
            f.write(f"Timestamp: {self.stats['timestamp']}\n\n")
            
            f.write("SUMMARY:\n")
            f.write(f"  Total files: {self.stats['total_files']}\n")
            f.write(f"  Valid: {self.stats['valid_files']} ({self.stats['integrity_score']}%)\n")
            f.write(f"  Corrupted: {self.stats['corrupted_files']}\n")
            f.write(f"  Unrecoverable: {self.stats['unrecoverable_files']}\n\n")
            
            f.write("BY FORMAT:\n")
            for fmt, data in sorted(self.stats['by_format'].items()):
                f.write(f"  {fmt}: {data['valid']}/{data['total']} valid ({data['valid']/data['total']*100:.1f}%)\n")
            f.write("\n")
            
            f.write("BY SOURCE:\n")
            for source, data in sorted(self.stats['by_source'].items()):
                f.write(f"  {source}: {data['valid']}/{data['total']} valid ({data['valid']/data['total']*100:.1f}%)\n")
            f.write("\n")
            
            if self.stats['corruption_types']:
                f.write("CORRUPTION TYPES:\n")
                for ctype, count in sorted(self.stats['corruption_types'].items()):
                    f.write(f"  {ctype}: {count}\n")
                f.write("\n")
            
            if self.files_needing_repair:
                f.write(f"FILES NEEDING REPAIR: {len(self.files_needing_repair)}\n")
                for file_info in self.files_needing_repair[:20]:  # First 20
                    f.write(f"  {file_info['filename']}: {file_info['corruption_type']} - {file_info['technique']}\n")
        
        self._print(f"Text report saved: {text_report}", "OK")
        
        return str(report_file)


def main():
    """
    Hlavná funkcia - entry point pre Penterep platformu
    """
    
    print("\n" + "="*70)
    print("FOR-COL-VALIDATE: Photo Integrity Validation")
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
    
    # Spustenie validácie
    validator = IntegrityValidator(case_id)
    results = validator.run_validation()
    
    # Uloženie reportov
    if results["success"]:
        report_path = validator.save_reports()
        print(f"\nValidation completed successfully")
        print(f"Integrity score: {results['integrity_score']}%")
        print(f"Valid files: {results['valid_files']}/{results['total_files']}")
        print(f"Files needing repair: {len(validator.files_needing_repair)}")
        print(f"Next step: Step 16 (Final Report)")
        sys.exit(0)
    else:
        print("\nValidation failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - KEY FEATURES
================================================================================

INTEGRITY VALIDATION
- Multi-tool validation approach
- Magic bytes checking
- Corruption type detection
- Repairability assessment
- Comprehensive categorization

VALIDATION TOOLS
1. Magic bytes check (file signatures)
2. file command (MIME type detection)
3. ImageMagick identify (structure validation)
4. PIL/Pillow (decode + load test)

DECISION LOGIC
- All tools pass + valid magic bytes = VALID
- At least one tool passes = CORRUPTED (repairable)
- All tools fail = UNRECOVERABLE (false positive)

CORRUPTION TYPES
1. truncated - Missing footer (Level 1, easily repairable)
2. invalid_header - Corrupt header bytes (Level 2, repairable)
3. corrupt_segments - Invalid segments (Level 2, repairable)
4. corrupt_data - Pixel data corruption (Level 3, partial recovery)
5. fragmented - File fragments (Level 4, difficult)
6. false_positive - Not an image (Level 5, impossible)

OUTPUT ORGANIZATION
validation/
  ├─ valid/            (100% functional photos)
  ├─ corrupted/        (repairable - go to Step 17)
  └─ unrecoverable/    (false positives - discard)

EXPECTED RESULTS
- FS-based recovery: >95% valid
- File carving: 70-85% valid
- Active files: ~99% valid
- Deleted files: ~78% valid (partial overwrites)

================================================================================
EXAMPLE OUTPUT
================================================================================

======================================================================
PHOTO INTEGRITY VALIDATION
Case ID: PHOTO-2025-01-26-001
======================================================================

Loading master catalog from Step 13...
[✓] Catalog loaded: master_catalog.json
[i] Total files to validate: 692

Checking validation tools...
[✓] ImageMagick identify: Found
[✓] PIL/Pillow: Found
[✓] file command: Found

======================================================================
FILE VALIDATION PHASE
======================================================================

Validating 692 files...
[i] Progress: 692/692 (100%)

[✓] Validation completed
[✓] Valid files: 623
[!] Corrupted files: 54
[✗] Unrecoverable files: 15
[✓] Integrity score: 90.03%

======================================================================
ORGANIZING FILES BY STATUS
======================================================================

[✓] Files organized into validation directories

======================================================================
VALIDATION COMPLETED
======================================================================
[i] Total files: 692
[✓] Valid: 623
[!] Corrupted: 54
[✗] Unrecoverable: 15
[✓] Integrity score: 90.03%
[i] Files needing repair: 38
======================================================================

Validation completed successfully
Integrity score: 90.03%
Valid files: 623/692
Files needing repair: 38

================================================================================
USAGE
================================================================================

INTERACTIVE MODE:
$ python3 step15_integrity_validation.py
Case ID: PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step15_integrity_validation.py PHOTO-2025-01-26-001

REQUIREMENTS:
- Step 13 (Consolidation) must be completed
- PIL/Pillow: pip install Pillow --break-system-packages
- ImageMagick (optional): sudo apt-get install imagemagick
- file command (usually pre-installed)

TIME ESTIMATE:
- ~5-30 minutes depending on number of files
- Validation is I/O intensive

================================================================================
INTERPRETATION GUIDE
================================================================================

INTEGRITY SCORE >95%:
- Excellent recovery
- Most photos fully functional
- Ready for delivery

INTEGRITY SCORE 85-95%:
- Good recovery
- Some corruption (expected with file carving)
- Most photos usable

INTEGRITY SCORE 70-85%:
- Fair recovery
- Significant corruption
- Many photos need repair

INTEGRITY SCORE <70%:
- Poor recovery
- Heavy corruption
- Source media was badly damaged

================================================================================
"""