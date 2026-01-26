#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-READ: Automatický test čítateľnosti média
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript vykonáva sériu diagnostických testov na určenie,
či je forenzné médium čitateľné a vhodné pre imaging.
"""

import subprocess
import time
import json
import sys
from pathlib import Path
from datetime import datetime

# Ptlibs je Penterep knižnica pre forenzné nástroje
try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False
    print("WARNING: ptlibs not found, using fallback output")


class MediaReadabilityTest:
    """
    Automatický test pre overenie čítateľnosti úložného média.
    
    Test vykoná 5 kontrol:
    1. OS detekcia (lsblk)
    2. Prvý sektor (dd 512B)
    3. Sekvenčné čítanie (dd 1MB)
    4. Náhodné čítanie (3 pozície)
    5. Meranie rýchlosti (dd 10MB)
    
    Výstup: READABLE / PARTIAL / UNREADABLE
    """
    
    def __init__(self, device_path, case_id):
        self.device = device_path
        self.case_id = case_id
        self.results = {
            "case_id": case_id,
            "device": device_path,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tests": [],
            "status": "UNKNOWN",
            "recommendation": "",
            "next_step": None
        }
        
    def _print(self, message, level="INFO"):
        """Helper pre výpis s farbami ak je ptlibs dostupný"""
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
        """
        Spustí shell príkaz a vráti výsledok.
        Používa subprocess pre bezpečnosť.
        """
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
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Command timeout",
                "success": False
            }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
    
    def test_1_os_detection(self):
        """Test 1: Overenie, či OS detekuje médium"""
        self._print("\nTest 1/5: OS Detection (lsblk)", "TITLE")
        
        result = self._run_command(["lsblk", "-d", "-n", "-o", "NAME,SIZE,TYPE", self.device])
        
        test_result = {
            "test_id": 1,
            "name": "OS Detection",
            "command": f"lsblk -d -n -o NAME,SIZE,TYPE {self.device}",
            "success": result["success"],
            "output": result["stdout"] if result["success"] else result["stderr"]
        }
        
        self.results["tests"].append(test_result)
        
        if result["success"]:
            self._print(f"Device detected: {result['stdout']}", "OK")
        else:
            self._print("Device NOT detected by OS", "ERROR")
            
        return result["success"]
    
    def test_2_first_sector(self):
        """Test 2: Čítanie prvého sektora (512 bajtov)"""
        self._print("\nTest 2/5: First Sector Read (512B)", "TITLE")
        
        # dd píše progress do stderr, preto ho zachytávame
        result = self._run_command([
            "dd",
            f"if={self.device}",
            "of=/dev/null",
            "bs=512",
            "count=1",
            "status=none"  # Potlačí verbose output
        ])
        
        test_result = {
            "test_id": 2,
            "name": "First Sector Read",
            "command": f"dd if={self.device} of=/dev/null bs=512 count=1",
            "success": result["success"],
            "stderr": result["stderr"]
        }
        
        self.results["tests"].append(test_result)
        
        if result["success"]:
            self._print("First sector readable", "OK")
        else:
            self._print(f"Failed to read first sector: {result['stderr']}", "ERROR")
            
        return result["success"]
    
    def test_3_sequential_read(self):
        """Test 3: Sekvenčné čítanie 1MB"""
        self._print("\nTest 3/5: Sequential Read (1MB)", "TITLE")
        
        start = time.time()
        result = self._run_command([
            "dd",
            f"if={self.device}",
            "of=/dev/null",
            "bs=1M",
            "count=1",
            "status=none"
        ], timeout=60)
        elapsed = time.time() - start
        
        test_result = {
            "test_id": 3,
            "name": "Sequential Read 1MB",
            "command": f"dd if={self.device} of=/dev/null bs=1M count=1",
            "success": result["success"],
            "elapsed_seconds": round(elapsed, 3)
        }
        
        self.results["tests"].append(test_result)
        
        if result["success"]:
            self._print(f"1MB read in {elapsed:.2f}s", "OK")
        else:
            self._print("Sequential read failed", "ERROR")
            
        return result["success"]
    
    def test_4_random_read(self):
        """Test 4: Náhodné čítanie z rôznych offsetov"""
        self._print("\nTest 4/5: Random Read (3 samples)", "TITLE")
        
        # Testujem na začiatku, v strede a blízko konca
        # (pre 64GB SD kartu to je 0, ~30GB, ~60GB)
        test_offsets = [
            ("start", 0),
            ("middle", 1024 * 1024 * 1024),  # 1GB
            ("late", 2 * 1024 * 1024 * 1024)  # 2GB
        ]
        
        failures = 0
        reads = []
        
        for label, offset in test_offsets:
            # skip= potrebuje počet blokov, nie bajtov
            # pre bs=512 je skip=offset/512
            skip_blocks = offset // 512
            
            result = self._run_command([
                "dd",
                f"if={self.device}",
                "of=/dev/null",
                "bs=512",
                "count=1",
                f"skip={skip_blocks}",
                "status=none"
            ])
            
            reads.append({
                "position": label,
                "offset_bytes": offset,
                "success": result["success"]
            })
            
            if result["success"]:
                self._print(f"  {label} (offset {offset}): OK", "OK")
            else:
                self._print(f"  {label} (offset {offset}): FAIL", "ERROR")
                failures += 1
        
        success = failures == 0
        partial = 0 < failures < len(test_offsets)
        
        test_result = {
            "test_id": 4,
            "name": "Random Read Test",
            "samples": reads,
            "failures": failures,
            "success": success,
            "partial": partial
        }
        
        self.results["tests"].append(test_result)
        
        if success:
            self._print("All random reads successful", "OK")
        elif partial:
            self._print(f"Partial success ({failures} failures)", "WARNING")
        else:
            self._print("All random reads failed", "ERROR")
            
        return success or partial
    
    def test_5_speed_measurement(self):
        """Test 5: Meranie rýchlosti čítania"""
        self._print("\nTest 5/5: Speed Measurement (10MB)", "TITLE")
        
        start = time.time()
        result = self._run_command([
            "dd",
            f"if={self.device}",
            "of=/dev/null",
            "bs=1M",
            "count=10",
            "status=none"
        ], timeout=120)
        elapsed = time.time() - start
        
        if result["success"] and elapsed > 0:
            speed_mbps = 10.0 / elapsed
            
            test_result = {
                "test_id": 5,
                "name": "Speed Measurement",
                "command": f"dd if={self.device} of=/dev/null bs=1M count=10",
                "success": True,
                "elapsed_seconds": round(elapsed, 3),
                "speed_mb_per_second": round(speed_mbps, 2)
            }
            
            self._print(f"Speed: {speed_mbps:.2f} MB/s", "OK")
            
            # Varovanie pri veľmi pomalej rýchlosti
            if speed_mbps < 1.0:
                self._print("WARNING: Very slow speed, possible hardware damage", "WARNING")
                
        else:
            test_result = {
                "test_id": 5,
                "name": "Speed Measurement",
                "success": False,
                "error": result["stderr"]
            }
            self._print("Speed measurement failed", "ERROR")
        
        self.results["tests"].append(test_result)
        return result["success"]
    
    def determine_final_status(self):
        """
        Vyhodnotenie konečného stavu média na základe výsledkov testov.
        
        Logika:
        - Ak Test 1 (OS detection) zlyhal → UNREADABLE
        - Ak Test 2 (first sector) zlyhal → UNREADABLE
        - Ak všetky testy OK → READABLE
        - Ak niektoré OK, niektoré nie → PARTIAL
        - Inak → UNREADABLE
        """
        
        # Zoznam success hodnôt
        successes = [t.get("success", False) for t in self.results["tests"]]
        
        # Test 1 je kritický
        if len(successes) > 0 and not successes[0]:
            status = "UNREADABLE"
            recommendation = "Device not detected by OS. Proceed to Step 4 (Physical Repair)."
            next_step = 4
            
        # Test 2 je tiež kritický
        elif len(successes) > 1 and not successes[1]:
            status = "UNREADABLE"
            recommendation = "Cannot read first sector. Proceed to Step 4 (Physical Repair)."
            next_step = 4
            
        # Všetko OK
        elif all(successes):
            status = "READABLE"
            recommendation = "Media fully readable. Proceed to Step 5 (Imaging with dd)."
            next_step = 5
            
        # Čiastočný úspech - niektoré testy OK
        elif any(successes):
            status = "PARTIAL"
            recommendation = "Media partially readable, bad sectors detected. Proceed to Step 5 (Imaging with ddrescue instead of dd)."
            next_step = 5
            
        # Všetko zlyhalo
        else:
            status = "UNREADABLE"
            recommendation = "All tests failed. Proceed to Step 4 (Physical Repair)."
            next_step = 4
        
        self.results["status"] = status
        self.results["recommendation"] = recommendation
        self.results["next_step"] = next_step
        
        return status
    
    def run_full_test(self):
        """Hlavná funkcia - spustí všetkých 5 testov"""
        
        self._print("=" * 70, "TITLE")
        self._print("AUTOMATED MEDIA READABILITY TEST", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print(f"Device: {self.device}", "TITLE")
        self._print("=" * 70, "TITLE")
        
        # Test 1: OS detection
        if not self.test_1_os_detection():
            self._print("\nOS detection failed, aborting further tests", "ERROR")
            self.determine_final_status()
            return self.results
        
        # Test 2: First sector
        if not self.test_2_first_sector():
            self._print("\nFirst sector read failed, aborting further tests", "ERROR")
            self.determine_final_status()
            return self.results
        
        # Testy 3-5 pokračujú aj pri čiastočnom zlyhaní
        self.test_3_sequential_read()
        self.test_4_random_read()
        self.test_5_speed_measurement()
        
        # Vyhodnotenie konečného stavu
        status = self.determine_final_status()
        
        # Výpis výsledku
        self._print("\n" + "=" * 70, "TITLE")
        self._print("TEST RESULTS", "TITLE")
        self._print("=" * 70, "TITLE")
        
        if status == "READABLE":
            self._print(f"Status: {status}", "OK")
        elif status == "PARTIAL":
            self._print(f"Status: {status}", "WARNING")
        else:
            self._print(f"Status: {status}", "ERROR")
        
        self._print(f"Recommendation: {self.results['recommendation']}", "INFO")
        self._print(f"Next Step: {self.results['next_step']}", "INFO")
        self._print("=" * 70 + "\n", "TITLE")
        
        return self.results
    
    def save_json_report(self, output_dir="/mnt/user-data/outputs"):
        """Uloženie JSON reportu do outputs priečinka"""
        
        # Vytvorenie output priečinka ak neexistuje
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Filename: CASE-ID_readability_test.json
        filename = f"{self.case_id}_readability_test.json"
        filepath = Path(output_dir) / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        self._print(f"JSON report saved: {filepath}", "OK")
        return str(filepath)


def main():
    """
    Hlavná funkcia - entry point pre Penterep platformu
    """
    
    print("\n" + "=" * 70)
    print("FOR-COL-READ: Media Readability Test")
    print("=" * 70 + "\n")
    
    # Získanie vstupných parametrov
    if len(sys.argv) >= 3:
        device = sys.argv[1]
        case_id = sys.argv[2]
    else:
        device = input("Device path (e.g., /dev/sdb): ").strip()
        case_id = input("Case ID (e.g., PHOTO-2025-01-26-001): ").strip()
    
    # Validácia vstupu
    if not device.startswith("/dev/"):
        print("ERROR: Device must start with /dev/")
        sys.exit(1)
    
    if not case_id:
        print("ERROR: Case ID cannot be empty")
        sys.exit(1)
    
    # KRITICKÉ: Write-blocker check
    print("\n⚠ CRITICAL: Ensure media is connected via WRITE-BLOCKER!")
    confirm = input("Confirm write-blocker in use (yes/no): ").strip().lower()
    
    if confirm not in ["yes", "y", "áno", "a"]:
        print("\n✗ Test aborted - write-blocker is MANDATORY!")
        sys.exit(1)
    
    # Spustenie testu
    test = MediaReadabilityTest(device, case_id)
    results = test.run_full_test()
    
    # Uloženie JSON
    json_path = test.save_json_report()
    
    # Return pre Penterep integráciu
    print(f"\nTest completed: {results['status']}")
    print(f"Next step: {results['next_step']}")
    
    return results


if __name__ == "__main__":
    main()