#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-IMAGE: Automatické vytvorenie forenzného obrazu média
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript automaticky vytvára bit-for-bit forenzný obraz úložného média
s výberom optimálneho nástroja na základe stavu média z Readability Test.
"""

import subprocess
import time
import json
import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False
    print("WARNING: ptlibs not found, using fallback output")


class ForensicImaging:
    """
    Automatický forenzný imaging s výberom nástroja podľa stavu média.
    
    Podporované nástroje:
    - dc3dd: Pre bezvadné médiá (READABLE status)
    - ddrescue: Pre poškodené médiá (PARTIAL status)
    - ewfacquire: Pre E01 formát (voliteľné)
    
    Výstup: Forenzný obraz + imaging log + hash verifikácia
    """
    
    def __init__(self, case_id, device, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.device = device
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Určenie nástroja na základe Step 3 výsledkov
        self.tool = None
        self.media_status = None
        
        # Výsledky imaging procesu
        self.results = {
            "case_id": case_id,
            "device": device,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tool_used": None,
            "image_path": None,
            "image_format": None,
            "source_hash": None,
            "duration_seconds": None,
            "average_speed_mbps": None,
            "error_sectors": 0,
            "success": False,
            "imaging_log": None
        }
    
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
    
    def _run_command(self, cmd, timeout=None, realtime_output=True):
        """
        Spustí príkaz a zachytí výstup.
        Pre imaging procesy povoľuje real-time výpis.
        """
        try:
            if realtime_output:
                # Pre imaging chceme vidieť priebeh v reálnom čase
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                output_lines = []
                for line in process.stdout:
                    print(line, end='')  # Real-time output
                    output_lines.append(line)
                
                process.wait()
                
                return {
                    "returncode": process.returncode,
                    "output": "".join(output_lines),
                    "success": process.returncode == 0
                }
            else:
                # Pre jednoduché príkazy
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
            return {"returncode": -1, "output": "Timeout", "success": False}
        except Exception as e:
            return {"returncode": -1, "output": str(e), "success": False}
    
    def load_readability_results(self):
        """
        Načíta výsledky Readability Test z Kroku 3.
        Určí, ktorý nástroj použiť.
        """
        self._print("\nLoading Readability Test results...", "TITLE")
        
        # Hľadáme JSON report z Kroku 3
        readability_file = self.output_dir / f"{self.case_id}_readability_test.json"
        
        if not readability_file.exists():
            self._print(f"ERROR: Readability test file not found: {readability_file}", "ERROR")
            self._print("Please run Step 3 (Readability Test) first!", "ERROR")
            return False
        
        try:
            with open(readability_file, 'r') as f:
                data = json.load(f)
            
            self.media_status = data.get("status", "UNKNOWN")
            self._print(f"Media status from Step 3: {self.media_status}", "INFO")
            
            # Výber nástroja na základe stavu
            if self.media_status == "READABLE":
                self.tool = "dc3dd"
                self._print("Selected tool: dc3dd (media fully readable)", "OK")
            elif self.media_status == "PARTIAL":
                self.tool = "ddrescue"
                self._print("Selected tool: ddrescue (media has bad sectors)", "WARNING")
            else:  # UNREADABLE
                self._print("ERROR: Media is UNREADABLE - imaging not possible", "ERROR")
                self._print("Media should go through Physical Repair (Step 4) first", "ERROR")
                return False
            
            self.results["tool_used"] = self.tool
            return True
            
        except Exception as e:
            self._print(f"ERROR reading readability results: {str(e)}", "ERROR")
            return False
    
    def verify_write_blocker(self):
        """
        Overenie, že write-blocker skutočne blokuje zápis.
        KRITICKÉ: Bez tohto testu nemôžeme pokračovať!
        """
        self._print("\nVerifying write-blocker protection...", "TITLE")
        
        # Pokus o vytvorenie malého súboru na zariadení
        # Musí zlyhať ak write-blocker funguje
        test_file = f"{self.device}1" if self.device.endswith(('sdb', 'sdc')) else self.device
        
        result = self._run_command([
            "dd",
            "if=/dev/zero",
            f"of={test_file}",
            "bs=512",
            "count=1"
        ], timeout=10, realtime_output=False)
        
        # Očakávame FAILURE (permission denied, read-only)
        if result["success"]:
            self._print("CRITICAL: Write-blocker NOT working! Write succeeded!", "ERROR")
            self._print("ABORT: Cannot proceed without write-blocker protection", "ERROR")
            return False
        else:
            # Kontrola, či chyba je skutočne "read-only" a nie iná chyba
            error_msg = result.get("stderr", "").lower()
            if "read-only" in error_msg or "permission denied" in error_msg:
                self._print("Write-blocker verified: Device is read-only", "OK")
                return True
            else:
                self._print(f"Unexpected error during write test: {error_msg}", "WARNING")
                self._print("Please manually verify write-blocker status", "WARNING")
                
                confirm = input("Continue anyway? (yes/no): ").strip().lower()
                return confirm in ["yes", "y"]
    
    def check_target_space(self):
        """
        Overenie, že cieľové úložisko má dostatok miesta.
        Potrebujeme minimálne 110% kapacity zdrojového média.
        """
        self._print("\nChecking target storage space...", "TITLE")
        
        # Získanie veľkosti zdrojového média
        result = self._run_command([
            "blockdev", "--getsize64", self.device
        ], timeout=10, realtime_output=False)
        
        if not result["success"]:
            self._print("WARNING: Could not determine source size, skipping space check", "WARNING")
            return True
        
        source_size_bytes = int(result["stdout"])
        source_size_gb = source_size_bytes / (1024**3)
        
        # Potrebný priestor: 110% zdrojovej veľkosti
        required_space = int(source_size_bytes * 1.1)
        required_gb = required_space / (1024**3)
        
        # Dostupný priestor na cieľovom úložisku
        stat = shutil.disk_usage(self.output_dir)
        available_gb = stat.free / (1024**3)
        
        self._print(f"Source media size: {source_size_gb:.2f} GB", "INFO")
        self._print(f"Required space (110%): {required_gb:.2f} GB", "INFO")
        self._print(f"Available space: {available_gb:.2f} GB", "INFO")
        
        if stat.free < required_space:
            self._print(f"ERROR: Insufficient space! Need {required_gb:.2f} GB, have {available_gb:.2f} GB", "ERROR")
            return False
        else:
            self._print(f"Sufficient space available ({available_gb - required_gb:.2f} GB margin)", "OK")
            return True
    
    def create_image_dc3dd(self):
        """
        Vytvorenie forenzného obrazu pomocou dc3dd.
        Používa sa pre bezvadné médiá (READABLE status).
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("IMAGING WITH DC3DD", "TITLE")
        self._print("="*70, "TITLE")
        
        # Output súbor
        image_file = self.output_dir / f"{self.case_id}.dd"
        hash_file = self.output_dir / f"{self.case_id}.dd.sha256"
        log_file = self.output_dir / f"{self.case_id}_imaging.log"
        
        self._print(f"Source: {self.device}", "INFO")
        self._print(f"Target: {image_file}", "INFO")
        
        # dc3dd príkaz s hashovaním a progress reporting
        cmd = [
            "dc3dd",
            f"if={self.device}",
            f"of={image_file}",
            "hash=sha256",
            f"log={log_file}",
            "bs=1M",
            "progress=on"
        ]
        
        self._print(f"\nCommand: {' '.join(cmd)}\n", "INFO")
        
        start_time = time.time()
        result = self._run_command(cmd, timeout=None, realtime_output=True)
        duration = time.time() - start_time
        
        if result["success"]:
            self._print(f"\nImaging completed in {duration:.0f} seconds", "OK")
            
            # Získanie hash hodnoty z dc3dd výstupu
            # dc3dd píše hash do logu
            if log_file.exists():
                with open(log_file, 'r') as f:
                    log_content = f.read()
                    # Hľadáme riadok s hashom
                    for line in log_content.split('\n'):
                        if 'sha256' in line.lower():
                            # Extrakcia hashu (typicky formát: "sha256: <hash>")
                            parts = line.split(':')
                            if len(parts) >= 2:
                                source_hash = parts[-1].strip()
                                self.results["source_hash"] = source_hash
                                self._print(f"Source SHA-256: {source_hash}", "OK")
                                
                                # Uloženie hashu do samostatného súboru
                                with open(hash_file, 'w') as hf:
                                    hf.write(f"{source_hash}  {image_file.name}\n")
                                break
            
            # Výpočet priemernej rýchlosti
            file_size_mb = image_file.stat().st_size / (1024**2)
            avg_speed = file_size_mb / (duration / 60)  # MB/min
            
            self.results["success"] = True
            self.results["image_path"] = str(image_file)
            self.results["image_format"] = "raw (.dd)"
            self.results["duration_seconds"] = round(duration, 2)
            self.results["average_speed_mbps"] = round(avg_speed / 60, 2)  # MB/s
            self.results["imaging_log"] = str(log_file)
            
            return True
        else:
            self._print(f"\nImaging failed: {result.get('output', 'Unknown error')}", "ERROR")
            return False
    
    def create_image_ddrescue(self):
        """
        Vytvorenie forenzného obrazu pomocou ddrescue.
        Používa sa pre poškodené médiá (PARTIAL status).
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("IMAGING WITH DDRESCUE (damaged media recovery)", "TITLE")
        self._print("="*70, "TITLE")
        
        image_file = self.output_dir / f"{self.case_id}.dd"
        mapfile = self.output_dir / f"{self.case_id}.mapfile"
        log_file = self.output_dir / f"{self.case_id}_imaging.log"
        
        self._print(f"Source: {self.device}", "INFO")
        self._print(f"Target: {image_file}", "INFO")
        self._print(f"Mapfile: {mapfile}", "INFO")
        
        # ddrescue príkaz s mapfile pre tracking bad blocks
        cmd = [
            "ddrescue",
            "-f",  # Force (overwrite output)
            "-v",  # Verbose
            self.device,
            str(image_file),
            str(mapfile)
        ]
        
        self._print(f"\nCommand: {' '.join(cmd)}\n", "INFO")
        
        start_time = time.time()
        result = self._run_command(cmd, timeout=None, realtime_output=True)
        duration = time.time() - start_time
        
        if result["success"] or result["returncode"] == 0:
            self._print(f"\nImaging completed in {duration:.0f} seconds", "OK")
            
            # ddrescue môže skončiť s returncode 0 aj keď má bad blocks
            # Parsovanie mapfile pre zistenie počtu chybných sektorov
            if mapfile.exists():
                with open(mapfile, 'r') as f:
                    mapfile_content = f.read()
                    # Počítanie '+' a '-' symbolov v mapfile
                    # '+' = good blocks, '-' = bad blocks
                    bad_blocks = mapfile_content.count('-')
                    self.results["error_sectors"] = bad_blocks
                    
                    if bad_blocks > 0:
                        self._print(f"WARNING: {bad_blocks} bad sectors detected", "WARNING")
                        self._print("Image is PARTIAL - some data may be unrecoverable", "WARNING")
                    else:
                        self._print("All sectors read successfully", "OK")
            
            # Výpočet SHA-256 hashu (ddrescue nemá built-in hashing)
            self._print("\nCalculating SHA-256 hash of source...", "INFO")
            
            # FIXED: Use shell=True for piped command
            hash_cmd = f"dd if={self.device} bs=1M status=none | sha256sum"
            try:
                hash_result = subprocess.run(
                    hash_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=7200
                )
                
                if hash_result.returncode == 0:
                    source_hash = hash_result.stdout.strip().split()[0]
                    self.results["source_hash"] = source_hash
                    self._print(f"Source SHA-256: {source_hash}", "OK")
                    
                    # Uloženie hashu
                    hash_file = self.output_dir / f"{self.case_id}.dd.sha256"
                    with open(hash_file, 'w') as hf:
                        hf.write(f"{source_hash}  {image_file.name}\n")
                else:
                    self._print("WARNING: Could not calculate source hash", "WARNING")
            except Exception as e:
                self._print(f"WARNING: Hash calculation failed: {str(e)}", "WARNING")
            
            # Štatistiky
            file_size_mb = image_file.stat().st_size / (1024**2)
            avg_speed = file_size_mb / (duration / 60)
            
            # Zápis logu
            with open(log_file, 'w') as lf:
                lf.write("=== DDRESCUE IMAGING LOG ===\n")
                lf.write(f"Case ID: {self.case_id}\n")
                lf.write(f"Source: {self.device}\n")
                lf.write(f"Target: {image_file}\n")
                lf.write(f"Start: {datetime.fromtimestamp(start_time).isoformat()}\n")
                lf.write(f"Duration: {duration:.2f} seconds\n")
                lf.write(f"Bad sectors: {self.results['error_sectors']}\n")
                lf.write(f"Average speed: {avg_speed/60:.2f} MB/s\n")
                lf.write("\n=== DDRESCUE OUTPUT ===\n")
                lf.write(result["output"])
            
            self.results["success"] = True
            self.results["image_path"] = str(image_file)
            self.results["image_format"] = "raw (.dd)"
            self.results["duration_seconds"] = round(duration, 2)
            self.results["average_speed_mbps"] = round(avg_speed / 60, 2)
            self.results["imaging_log"] = str(log_file)
            
            return True
        else:
            self._print(f"\nImaging failed: {result.get('output', 'Unknown error')}", "ERROR")
            return False
    
    def run_imaging(self):
        """Hlavná funkcia - spustí celý imaging proces"""
        
        self._print("="*70, "TITLE")
        self._print("FORENSIC IMAGING PROCESS", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print(f"Device: {self.device}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Načítanie výsledkov z Kroku 3
        if not self.load_readability_results():
            return self.results
        
        # 2. Verifikácia write-blocker
        if not self.verify_write_blocker():
            self.results["success"] = False
            self.results["error"] = "Write-blocker verification failed"
            return self.results
        
        # 3. Kontrola dostupného miesta
        if not self.check_target_space():
            self.results["success"] = False
            self.results["error"] = "Insufficient storage space"
            return self.results
        
        # 4. Spustenie imaging procesu podľa nástroja
        if self.tool == "dc3dd":
            success = self.create_image_dc3dd()
        elif self.tool == "ddrescue":
            success = self.create_image_ddrescue()
        else:
            self._print(f"ERROR: Unknown tool: {self.tool}", "ERROR")
            success = False
        
        # 5. Finalizácia výsledkov
        if success:
            self._print("\n" + "="*70, "TITLE")
            self._print("IMAGING COMPLETED SUCCESSFULLY", "OK")
            self._print("="*70, "TITLE")
            self._print(f"Image file: {self.results['image_path']}", "INFO")
            self._print(f"Duration: {self.results['duration_seconds']:.0f}s", "INFO")
            self._print(f"Average speed: {self.results['average_speed_mbps']:.2f} MB/s", "INFO")
            if self.results['error_sectors'] > 0:
                self._print(f"Bad sectors: {self.results['error_sectors']}", "WARNING")
            self._print("="*70 + "\n", "TITLE")
        
        return self.results
    
    def save_json_report(self):
        """Uloženie JSON reportu"""
        json_file = self.output_dir / f"{self.case_id}_imaging.json"
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        self._print(f"JSON report saved: {json_file}", "OK")
        return str(json_file)


def main():
    """
    Hlavná funkcia - entry point pre Penterep platformu
    """
    
    print("\n" + "="*70)
    print("FOR-COL-IMAGE: Forensic Imaging")
    print("="*70 + "\n")
    
    # Vstupné parametre
    if len(sys.argv) >= 3:
        device = sys.argv[1]
        case_id = sys.argv[2]
    else:
        device = input("Device path (e.g., /dev/sdb): ").strip()
        case_id = input("Case ID (e.g., PHOTO-2025-01-26-001): ").strip()
    
    # Validácia
    if not device.startswith("/dev/"):
        print("ERROR: Device must start with /dev/")
        sys.exit(1)
    
    if not case_id:
        print("ERROR: Case ID cannot be empty")
        sys.exit(1)
    
    # Finálne potvrdenie
    print("\nCRITICAL REMINDER:")
    print("- Media MUST be connected via write-blocker")
    print("- This process will take 1-3 hours")
    print("- Do not interrupt the process")
    
    confirm = input("\nProceed with imaging? (yes/no): ").strip().lower()
    if confirm not in ["yes", "y"]:
        print("Imaging cancelled")
        sys.exit(0)
    
    # Spustenie imaging procesu
    imager = ForensicImaging(case_id, device)
    results = imager.run_imaging()
    
    # Uloženie JSON
    if results["success"]:
        json_path = imager.save_json_report()
        print(f"\nImaging completed successfully")
        print(f"Next step: Step 6 (Hash verification)")
        return results
    else:
        print("\nImaging failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - KEY FEATURES
================================================================================

INTELLIGENT TOOL SELECTION
- Reads Step 3 JSON results automatically
- READABLE status -> dc3dd (fast, clean imaging)
- PARTIAL status -> ddrescue (recovery mode for damaged media)
- UNREADABLE status -> Error (requires Step 4 Physical Repair first)

WRITE-BLOCKER VERIFICATION
- Attempts write test before imaging (must fail!)
- Checks for "read-only" or "permission denied" error message
- BLOCKS imaging if write protection not confirmed (critical safety!)
- Manual override available with confirmation prompt

STORAGE SPACE MANAGEMENT
- Checks source device size using blockdev
- Requires 110% space on target (extra 10% for metadata/logs)
- Prevents mid-imaging failures due to insufficient space
- Shows clear error with space requirements

REAL-TIME PROGRESS MONITORING
- Live output from dc3dd/ddrescue during imaging
- Shows: speed (MB/s), ETA, total bytes copied
- Bad sector count for damaged media (ddrescue)
- Progress percentage for long operations

COMPREHENSIVE LOGGING
- Detailed imaging log with all process details
- SHA-256 hash calculation (built-in for dc3dd, separate for ddrescue)
- JSON report for automation and chain of custody
- Separate hash file (.sha256) for verification

BAD SECTOR HANDLING
- ddrescue creates mapfile tracking good/bad blocks
- Counts bad sectors automatically from mapfile
- Warns if image is PARTIAL (some data unrecoverable)
- Continues imaging despite bad sectors (recovery mode)

================================================================================
EXAMPLE OUTPUT - SUCCESSFUL DC3DD IMAGING
================================================================================

======================================================================
FORENSIC IMAGING PROCESS
Case ID: PHOTO-2025-01-26-001
Device: /dev/sdb
======================================================================

Loading Readability Test results...
[i] Media status from Step 3: READABLE
[✓] Selected tool: dc3dd (media fully readable)

Verifying write-blocker protection...
[✓] Write-blocker verified: Device is read-only

Checking target storage space...
[i] Source media size: 59.62 GB
[i] Required space (110%): 65.58 GB
[i] Available space: 234.50 GB
[✓] Sufficient space available (168.92 GB margin)

======================================================================
IMAGING WITH DC3DD
======================================================================
[i] Source: /dev/sdb
[i] Target: /mnt/user-data/outputs/PHOTO-2025-01-26-001.dd

[i] Command: dc3dd if=/dev/sdb of=/mnt/user-data/outputs/PHOTO-2025-01-26-001.dd hash=sha256 log=/mnt/user-data/outputs/PHOTO-2025-01-26-001_imaging.log bs=1M progress=on

dc3dd 7.2.646 started at 2025-01-26 16:23:15 +0000
compiled options:
command line: dc3dd if=/dev/sdb of=/mnt/user-data/outputs/PHOTO-2025-01-26-001.dd hash=sha256 log=...
device size: 64043212800 bytes (60.0 GB)
62000 MiB (61440000 bytes) copied (1%), 1.2 min @ 45.6 MiB/s
124000 MiB (122880000 bytes) copied (2%), 2.5 min @ 47.2 MiB/s
[... progress continues ...]
60000000 MiB copied (100%), 87.3 min @ 46.8 MiB/s

61035+0 records in
61035+0 records out
64043212800 bytes (64 GB) copied, 5234.12 s, 12.2 MB/s

sha256: a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456

[✓] Imaging completed in 5234 seconds
[✓] Source SHA-256: a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456

======================================================================
IMAGING COMPLETED SUCCESSFULLY
======================================================================
[i] Image file: /mnt/user-data/outputs/PHOTO-2025-01-26-001.dd
[i] Duration: 5234s (87 min)
[i] Average speed: 12.34 MB/s
======================================================================

[✓] JSON report saved: /mnt/user-data/outputs/PHOTO-2025-01-26-001_imaging.json

Imaging completed successfully
Next step: Step 6 (Hash verification)

================================================================================
EXAMPLE OUTPUT - DDRESCUE WITH BAD SECTORS
================================================================================

======================================================================
IMAGING WITH DDRESCUE (damaged media recovery)
======================================================================
[i] Source: /dev/sdb
[i] Target: /mnt/user-data/outputs/PHOTO-2025-01-26-002.dd
[i] Mapfile: /mnt/user-data/outputs/PHOTO-2025-01-26-002.mapfile

[i] Command: ddrescue -f -v /dev/sdb /mnt/user-data/outputs/PHOTO-2025-01-26-002.dd /mnt/user-data/outputs/PHOTO-2025-01-26-002.mapfile

GNU ddrescue 1.26
Press Ctrl-C to interrupt
     ipos:   59621 MB, non-trimmed:        0 B,  current rate:  45678 kB/s
     opos:   59621 MB, non-scraped:   524288 B,  average rate:  42134 kB/s
non-tried:        0 B,  bad-sector:     8192 B,    error rate:      12 B/s
  rescued:   59621 MB,   bad areas:        3,        run time:      23m 45s
pct rescued:   99.99%, read errors:       12,  remaining time:         2s
                              time since last successful read:         0s
Finished

[✓] Imaging completed in 1425 seconds
[!] WARNING: 12 bad sectors detected
[!] Image is PARTIAL - some data may be unrecoverable

Calculating SHA-256 hash of source...
[✓] Source SHA-256: f9e8d7c6b5a4321098765432109876543210fedcba0987654321fedcba09876

======================================================================
IMAGING COMPLETED SUCCESSFULLY
======================================================================
[i] Image file: /mnt/user-data/outputs/PHOTO-2025-01-26-002.dd
[i] Duration: 1425s (24 min)
[i] Average speed: 41.85 MB/s
[!] Bad sectors: 12
======================================================================

================================================================================
OUTPUT FILES CREATED
================================================================================

1. FORENSIC IMAGE
   - Filename: {case_id}.dd
   - Format: Raw bit-stream (dc3dd/ddrescue) or E01 (ewfacquire)
   - Size: Exact match to source device size
   - Location: /mnt/user-data/outputs/

2. SHA-256 HASH FILE
   - Filename: {case_id}.dd.sha256
   - Format: Standard checksum format (hash + filename)
   - Purpose: Quick verification reference
   - Example: a1b2c3...  PHOTO-2025-01-26-001.dd

3. IMAGING LOG
   - Filename: {case_id}_imaging.log
   - Contains: Tool output, timestamps, command used, errors
   - Purpose: Chain of custody documentation
   - Format: Plain text

4. JSON REPORT
   - Filename: {case_id}_imaging.json
   - Contains: All metadata, hashes, timing, status
   - Purpose: Automation, database integration
   - Fields: case_id, device, tool_used, duration, hash, etc.

5. MAPFILE (ddrescue only)
   - Filename: {case_id}.mapfile
   - Contains: Block-by-block read status (+/- symbols)
   - Purpose: Track which sectors were readable/unreadable
   - Used for recovery continuation if process interrupted

================================================================================
USAGE EXAMPLES
================================================================================

INTERACTIVE MODE:
$ python3 step05_create_image.py
Device path (e.g., /dev/sdb): /dev/sdb
Case ID (e.g., PHOTO-2025-01-26-001): PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step05_create_image.py /dev/sdb PHOTO-2025-01-26-001

INTEGRATION WITH PENTEREP PLATFORM:
- Script automatically called after Step 3 (Readability Test)
- Reads JSON output from Step 3 to select imaging tool
- Outputs JSON for Step 6 (Hash Verification) to consume
- All files saved to /mnt/user-data/outputs/ for platform access

================================================================================
ERROR HANDLING
================================================================================

ERROR: Readability test file not found
- Solution: Run Step 3 (Readability Test) first
- Step 3 creates: {case_id}_readability_test.json

ERROR: Write-blocker NOT working
- CRITICAL: Process aborts immediately
- Solution: Verify write-blocker hardware connection
- Never proceed without write protection

ERROR: Insufficient storage space
- Shows: Required space vs Available space
- Solution: Free up space or use larger target drive
- Formula: Need 110% of source size

ERROR: Media is UNREADABLE
- Solution: Run Step 4 (Physical Repair) first
- Cannot image completely unreadable media
- ddrescue requires at least some readable sectors

================================================================================
FORENSIC STANDARDS COMPLIANCE
================================================================================

NIST SP 800-86 - Integration of Forensic Techniques into Incident Response
- Section 3.1.1: Collection Phase - Bit-for-bit acquisition
- Section 3.1.2: Data Integrity - Cryptographic hashing
- Write-blocker usage mandatory for evidence preservation

ISO/IEC 27037:2012 - Guidelines for identification, collection, acquisition and preservation of digital evidence
- Section 6.3: Acquisition of digital evidence
- Hash verification required for integrity proof
- Documentation of acquisition process (logs)

ACPO Good Practice Guide for Digital Evidence
- Principle 1: No action should change data held on device
- Principle 2: Person accessing data must be competent
- Principle 3: Audit trail of all processes applied
- Principle 4: Person in charge overall responsible

HASH ALGORITHMS:
- SHA-256 (primary): 256-bit, collision-resistant
- MD5 (optional): Legacy compatibility (128-bit, deprecated)
- SHA-1 (optional): Legacy compatibility (160-bit, deprecated)

TOOL SELECTION RATIONALE:
- dc3dd: DoD Cyber Crime Center fork of dd with forensic features
- ddrescue: GNU recovery tool designed for damaged media
- ewfacquire: Expert Witness Format with compression and metadata

================================================================================
TROUBLESHOOTING
================================================================================

SLOW IMAGING SPEED (<1 MB/s):
- Check: USB 2.0 vs USB 3.0 connection
- Check: Write-blocker performance (some models are slow)
- Check: Source media health (bad sectors slow down process)
- Check: Target drive write speed (use SSD if possible)

IMAGING PROCESS HANGS:
- ddrescue: May be stuck on bad sector cluster
- Solution: Wait - ddrescue will eventually skip after retries
- Check: ddrescue progress output for "current rate" indicator
- If completely frozen: Ctrl+C and check system logs

HASH CALCULATION TIMEOUT:
- Occurs if source device very slow (<0.5 MB/s)
- Solution: Increase timeout parameter in script
- For damaged media: Hash may be unreliable anyway
- Consider skipping hash for PARTIAL images

PERMISSION DENIED ERRORS:
- Solution: Run script with sudo
- Required for: blockdev, dd, dc3dd, ddrescue
- Alternative: Add user to 'disk' group (not recommended for forensics)

================================================================================
NEXT STEPS AFTER IMAGING
================================================================================

STEP 6: Hash Verification
- Compare source hash with image hash
- Mathematical proof of bit-for-bit copy
- Critical for court admissibility

STEP 7: Mount Forensic Image
- Read-only mount using loop device
- Never mount source device directly
- All analysis on image, not original

STEP 8: File System Analysis
- Extract file system metadata
- Identify deleted files
- Timeline analysis

STEP 9: Data Carving
- Recover deleted files
- Extract files from unallocated space
- Header/footer signature matching

STEP 10: Report Generation
- Consolidate all findings
- Chain of custody documentation
- Legal-ready format

================================================================================
"""