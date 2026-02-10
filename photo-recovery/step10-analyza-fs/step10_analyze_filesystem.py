#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-FS-ANALYSIS: Automatická analýza súborového systému forenzného obrazu
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript analyzuje forenzný obraz média pomocí The Sleuth Kit nástrojov
a určuje optimálnu stratégiu obnovy fotografií na základe stavu súborového systému.
"""

import subprocess
import json
import sys
import re
from pathlib import Path
from datetime import datetime

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False
    print("WARNING: ptlibs not found, using fallback output")


class FilesystemAnalyzer:
    """
    Automatická analýza súborového systému forenzného obrazu.
    
    Fázy analýzy:
    1. Načítanie cesty k obrazu z Step 6
    2. Analýza partícií (mmls)
    3. Analýza súborového systému (fsstat)
    4. Test adresárovej štruktúry (fls)
    5. Identifikácia obrazových súborov
    6. Vyhodnotenie stratégie obnovy
    
    Výstup: JSON report s odporúčanou metódou recovery
    """
    
    # Podporované obrazové formáty
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
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Cesta k obrazu (načíta sa z Step 6)
        self.image_path = None
        
        # Výsledky analýzy
        self.results = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "image_file": None,
            "partition_table_type": None,
            "partitions": [],
            "filesystem_recognized": False,
            "directory_structure_readable": False,
            "image_files_found": {
                "total": 0,
                "active": 0,
                "deleted": 0,
                "by_type": {}
            },
            "recommended_method": None,
            "recommended_tool": None,
            "estimated_time_minutes": None,
            "notes": [],
            "success": False
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
    
    def load_image_path(self):
        """
        Načíta cestu k forenznom obrazu zo Step 6 výstupu.
        """
        self._print("\nLoading image path from Step 6...", "TITLE")
        
        # Pokus 1: Načítať z Step 6 hash verification
        hash_verification_file = self.output_dir / f"{self.case_id}_hash_verification.json"
        
        if hash_verification_file.exists():
            try:
                with open(hash_verification_file, 'r') as f:
                    data = json.load(f)
                
                # Hľadáme image path - môže byť uložený rôzne
                image_path = data.get("image_path")
                
                if image_path and Path(image_path).exists():
                    self.image_path = Path(image_path)
                    self.results["image_file"] = str(self.image_path)
                    self._print(f"Image path loaded: {self.image_path}", "OK")
                    return True
            except Exception as e:
                self._print(f"Warning: Could not read hash verification: {str(e)}", "WARNING")
        
        # Pokus 2: Načítať z Step 5 imaging
        imaging_file = self.output_dir / f"{self.case_id}_imaging.json"
        
        if imaging_file.exists():
            try:
                with open(imaging_file, 'r') as f:
                    data = json.load(f)
                
                image_path = data.get("image_path")
                
                if image_path and Path(image_path).exists():
                    self.image_path = Path(image_path)
                    self.results["image_file"] = str(self.image_path)
                    self._print(f"Image path loaded from Step 5: {self.image_path}", "OK")
                    return True
            except Exception as e:
                self._print(f"Warning: Could not read imaging file: {str(e)}", "WARNING")
        
        # Pokus 3: Hľadať štandardné umiestnenie
        default_image = self.output_dir / f"{self.case_id}.dd"
        
        if default_image.exists():
            self.image_path = default_image
            self.results["image_file"] = str(self.image_path)
            self._print(f"Using default image path: {self.image_path}", "OK")
            return True
        
        # Ak nič nefungovalo
        self._print("ERROR: Cannot find forensic image", "ERROR")
        self._print("Please ensure Steps 5 and 6 have been completed", "ERROR")
        return False
    
    def check_tools(self):
        """Overte dostupnosť The Sleuth Kit nástrojov"""
        self._print("\nChecking The Sleuth Kit tools...", "TITLE")
        
        tools = ['mmls', 'fsstat', 'fls']
        missing_tools = []
        
        for tool in tools:
            result = self._run_command(['which', tool], timeout=5)
            if result["success"]:
                self._print(f"{tool}: Found", "OK")
            else:
                self._print(f"{tool}: NOT FOUND", "ERROR")
                missing_tools.append(tool)
        
        if missing_tools:
            self._print(f"\nERROR: Missing tools: {', '.join(missing_tools)}", "ERROR")
            self._print("Install: sudo apt-get install sleuthkit", "ERROR")
            return False
        
        return True
    
    def analyze_partitions(self):
        """
        FÁZA 1: Analýza partícií pomocou mmls.
        Identifikuje partičnú tabuľku a všetky partície.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("PHASE 1: PARTITION ANALYSIS", "TITLE")
        self._print("="*70, "TITLE")
        
        cmd = ['mmls', str(self.image_path)]
        result = self._run_command(cmd)
        
        if not result["success"]:
            self._print("No partition table detected (superfloppy format)", "WARNING")
            self._print("Entire device is likely a single filesystem", "INFO")
            self.results["partition_table_type"] = "superfloppy"
            
            # Pridáme celé médium ako jednu "partíciu"
            self.results["partitions"].append({
                "number": 0,
                "offset": 0,
                "size_sectors": None,
                "type": "whole_device",
                "description": "No partition table - superfloppy format"
            })
            return True
        
        # Parsovanie mmls výstupu
        self._print("\nPartition table found:", "OK")
        
        lines = result["stdout"].split('\n')
        partition_table_type = None
        
        for line in lines:
            # Detekcia typu partition table
            if 'DOS Partition Table' in line:
                partition_table_type = "DOS/MBR"
            elif 'GPT' in line:
                partition_table_type = "GPT"
            
            # Parsovanie partition entries
            # Formát: 000:  Meta  00000  00000  00000  Primary Table (#0)
            # Formát: 002:  00:00  00001  62521343  62521343  Linux (0x83)
            match = re.match(r'(\d+):\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)', line)
            if match:
                slot = int(match.group(1))
                part_type = match.group(2)
                start = int(match.group(3))
                end = int(match.group(4))
                size = int(match.group(5))
                description = match.group(6).strip()
                
                # Preskočiť meta entries a tabuľky
                if part_type.lower() in ['meta', '-----']:
                    continue
                
                # Len skutočné partície
                if size > 0:
                    partition = {
                        "number": slot,
                        "offset": start,
                        "size_sectors": size,
                        "type": part_type,
                        "description": description
                    }
                    
                    self.results["partitions"].append(partition)
                    self._print(f"Partition {slot}: offset={start}, size={size} sectors", "INFO")
        
        self.results["partition_table_type"] = partition_table_type or "unknown"
        self._print(f"\nPartition table type: {self.results['partition_table_type']}", "OK")
        self._print(f"Found {len(self.results['partitions'])} partition(s)", "OK")
        
        return True
    
    def analyze_filesystem(self, partition):
        """
        FÁZA 2: Analýza súborového systému pomocou fsstat.
        
        Args:
            partition: Dictionary s informáciami o partícii
        
        Returns:
            Dictionary s filesystem informáciami
        """
        offset = partition.get("offset", 0)
        
        self._print(f"\nAnalyzing filesystem at offset {offset}...", "INFO")
        
        cmd = ['fsstat', '-o', str(offset), str(self.image_path)]
        result = self._run_command(cmd)
        
        fs_info = {
            "offset": offset,
            "recognized": False,
            "type": "unknown",
            "state": "unrecognized",
            "label": None,
            "uuid": None,
            "sector_size": None,
            "cluster_size": None,
            "total_clusters": None,
            "free_clusters": None
        }
        
        if not result["success"]:
            self._print(f"Filesystem not recognized at offset {offset}", "ERROR")
            return fs_info
        
        # Parsovanie fsstat výstupu
        output = result["stdout"]
        
        # Detekcia typu FS
        if 'FAT32' in output:
            fs_info["type"] = "FAT32"
        elif 'FAT16' in output:
            fs_info["type"] = "FAT16"
        elif 'FAT12' in output:
            fs_info["type"] = "FAT12"
        elif 'exFAT' in output:
            fs_info["type"] = "exFAT"
        elif 'NTFS' in output:
            fs_info["type"] = "NTFS"
        elif 'Ext4' in output or 'ext4' in output:
            fs_info["type"] = "ext4"
        elif 'Ext3' in output or 'ext3' in output:
            fs_info["type"] = "ext3"
        elif 'Ext2' in output or 'ext2' in output:
            fs_info["type"] = "ext2"
        elif 'HFS+' in output:
            fs_info["type"] = "HFS+"
        elif 'APFS' in output:
            fs_info["type"] = "APFS"
        elif 'ISO 9660' in output:
            fs_info["type"] = "ISO9660"
        
        # Extrakcia metadát
        for line in output.split('\n'):
            # Volume label
            if 'Volume Label' in line or 'Label' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    fs_info["label"] = match.group(1).strip()
            
            # UUID/Serial
            if 'Serial Number' in line or 'UUID' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    fs_info["uuid"] = match.group(1).strip()
            
            # Sector size
            if 'Sector Size' in line or 'sector size' in line:
                match = re.search(r'(\d+)', line)
                if match:
                    fs_info["sector_size"] = int(match.group(1))
            
            # Cluster/Block size
            if 'Cluster Size' in line or 'Block Size' in line:
                match = re.search(r'(\d+)', line)
                if match:
                    fs_info["cluster_size"] = int(match.group(1))
            
            # Total clusters/blocks
            if 'Total Clusters' in line or 'Block Count' in line:
                match = re.search(r'(\d+)', line)
                if match:
                    fs_info["total_clusters"] = int(match.group(1))
            
            # Free clusters/blocks
            if 'Free Clusters' in line or 'Free Blocks' in line:
                match = re.search(r'(\d+)', line)
                if match:
                    fs_info["free_clusters"] = int(match.group(1))
        
        if fs_info["type"] != "unknown":
            fs_info["recognized"] = True
            fs_info["state"] = "recognized"
            self._print(f"Filesystem type: {fs_info['type']}", "OK")
            if fs_info["label"]:
                self._print(f"Volume label: {fs_info['label']}", "INFO")
        else:
            self._print("Could not identify filesystem type", "WARNING")
        
        return fs_info
    
    def test_directory_structure(self, partition, fs_info):
        """
        FÁZA 3: Test čitateľnosti adresárovej štruktúry pomocou fls.
        
        Args:
            partition: Dictionary s informáciami o partícii
            fs_info: Dictionary s filesystem informáciami
        
        Returns:
            Tuple (readable, active_count, deleted_count, file_list)
        """
        offset = partition.get("offset", 0)
        
        self._print(f"\nTesting directory structure at offset {offset}...", "INFO")
        
        # Ak FS nie je rozpoznaný, preskočíme fls
        if not fs_info.get("recognized"):
            self._print("Skipping fls (filesystem not recognized)", "WARNING")
            return False, 0, 0, []
        
        cmd = ['fls', '-r', '-o', str(offset), str(self.image_path)]
        result = self._run_command(cmd, timeout=600)  # 10 min timeout pre veľké médiá
        
        if not result["success"] or not result["stdout"]:
            self._print("Directory structure not readable", "ERROR")
            return False, 0, 0, []
        
        # Parsovanie fls výstupu
        lines = result["stdout"].split('\n')
        file_list = []
        active_count = 0
        deleted_count = 0
        
        for line in lines:
            if not line.strip():
                continue
            
            # fls formát: r/r * 12345: filename.jpg
            # r = regular file, * = deleted
            is_deleted = '*' in line
            
            # Extrakcia názvu súboru
            match = re.search(r':\s*(.+)$', line)
            if match:
                filename = match.group(1).strip()
                
                file_entry = {
                    "filename": filename,
                    "deleted": is_deleted,
                    "full_line": line
                }
                
                file_list.append(file_entry)
                
                if is_deleted:
                    deleted_count += 1
                else:
                    active_count += 1
        
        total = active_count + deleted_count
        
        self._print(f"Directory structure readable: {total} entries found", "OK")
        self._print(f"Active files: {active_count}", "INFO")
        self._print(f"Deleted files: {deleted_count}", "INFO")
        
        return True, active_count, deleted_count, file_list
    
    def identify_image_files(self, file_list):
        """
        FÁZA 4: Identifikácia obrazových súborov.
        
        Args:
            file_list: Zoznam súborov z fls
        
        Returns:
            Dictionary s počtami obrazových súborov
        """
        self._print("\nIdentifying image files...", "TITLE")
        
        image_files = {
            "total": 0,
            "active": 0,
            "deleted": 0,
            "by_type": {}
        }
        
        # Inicializácia počítadiel pre každý typ
        for img_type in self.IMAGE_EXTENSIONS.keys():
            image_files["by_type"][img_type] = {"active": 0, "deleted": 0}
        
        for file_entry in file_list:
            filename = file_entry["filename"].lower()
            is_deleted = file_entry["deleted"]
            
            # Kontrola, či má obrazovú príponu
            for img_type, extensions in self.IMAGE_EXTENSIONS.items():
                if any(filename.endswith(ext) for ext in extensions):
                    image_files["total"] += 1
                    
                    if is_deleted:
                        image_files["deleted"] += 1
                        image_files["by_type"][img_type]["deleted"] += 1
                    else:
                        image_files["active"] += 1
                        image_files["by_type"][img_type]["active"] += 1
                    
                    break  # Každý súbor počítame len raz
        
        self._print(f"Total image files found: {image_files['total']}", "OK")
        self._print(f"Active: {image_files['active']}, Deleted: {image_files['deleted']}", "INFO")
        
        # Zobrazenie rozdelenia podľa typu
        for img_type, counts in image_files["by_type"].items():
            total_type = counts["active"] + counts["deleted"]
            if total_type > 0:
                self._print(f"  {img_type.upper()}: {total_type} (active: {counts['active']}, deleted: {counts['deleted']})", "INFO")
        
        return image_files
    
    def determine_recovery_strategy(self):
        """
        FÁZA 5: Vyhodnotenie optimálnej stratégie obnovy.
        
        Returns:
            Tuple (method, tool, estimated_time_minutes, notes)
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("RECOVERY STRATEGY DETERMINATION", "TITLE")
        self._print("="*70, "TITLE")
        
        fs_recognized = self.results["filesystem_recognized"]
        dir_readable = self.results["directory_structure_readable"]
        image_count = self.results["image_files_found"]["total"]
        
        method = None
        tool = None
        estimated_time = None
        notes = []
        
        # Rozhodovacia logika
        if fs_recognized and dir_readable:
            # Ideálny scenár - FS rozpoznaný a adresáre čitateľné
            method = "filesystem_scan"
            tool = "fls + icat (The Sleuth Kit)"
            estimated_time = max(15, image_count * 0.1)  # ~0.1 min per file, min 15 min
            notes.append("Filesystem structure intact - can use filesystem-based recovery")
            notes.append("Original filenames and directory structure will be preserved")
            notes.append("Fast recovery method - recommended approach")
            self._print("Recommended method: FILESYSTEM SCAN", "OK")
            
        elif fs_recognized and not dir_readable:
            # FS rozpoznaný ale adresáre poškodené
            method = "hybrid"
            tool = "fls + photorec (combined approach)"
            estimated_time = max(45, image_count * 0.3)
            notes.append("Filesystem recognized but directory structure damaged")
            notes.append("Use hybrid approach: filesystem scan + file carving")
            notes.append("Some filenames may be lost")
            self._print("Recommended method: HYBRID (FS scan + carving)", "WARNING")
            
        else:
            # FS nerozpoznaný alebo vážne poškodený
            method = "file_carving"
            tool = "photorec / foremost"
            estimated_time = max(90, image_count * 0.5)
            notes.append("Filesystem not recognized or severely damaged")
            notes.append("Must use file carving (signature-based recovery)")
            notes.append("Original filenames and directory structure will be lost")
            notes.append("Files will be recovered with generic names")
            notes.append("Slower recovery method but more thorough")
            self._print("Recommended method: FILE CARVING", "WARNING")
        
        self._print(f"Recommended tool: {tool}", "INFO")
        self._print(f"Estimated time: ~{estimated_time:.0f} minutes", "INFO")
        
        return method, tool, estimated_time, notes
    
    def run_analysis(self):
        """Hlavná funkcia - spustí celý analytický proces"""
        
        self._print("="*70, "TITLE")
        self._print("FILESYSTEM ANALYSIS", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Načítanie cesty k obrazu
        if not self.load_image_path():
            self.results["success"] = False
            return self.results
        
        # 2. Kontrola nástrojov
        if not self.check_tools():
            self.results["success"] = False
            return self.results
        
        # 3. Analýza partícií
        if not self.analyze_partitions():
            self.results["success"] = False
            return self.results
        
        # 4. Pre každú partíciu: analýza FS + directory structure
        for partition in self.results["partitions"]:
            # Analýza FS
            fs_info = self.analyze_filesystem(partition)
            partition["filesystem"] = fs_info
            
            # Ak je FS rozpoznaný, nastavíme flag
            if fs_info["recognized"]:
                self.results["filesystem_recognized"] = True
            
            # Test directory structure
            readable, active, deleted, file_list = self.test_directory_structure(partition, fs_info)
            
            partition["directory_readable"] = readable
            partition["file_counts"] = {
                "active": active,
                "deleted": deleted,
                "total": active + deleted
            }
            
            if readable:
                self.results["directory_structure_readable"] = True
                
                # Identifikácia obrazových súborov
                image_files = self.identify_image_files(file_list)
                partition["image_files"] = image_files
                
                # Akumulácia do celkových výsledkov
                self.results["image_files_found"]["total"] += image_files["total"]
                self.results["image_files_found"]["active"] += image_files["active"]
                self.results["image_files_found"]["deleted"] += image_files["deleted"]
                
                # Akumulácia podľa typu
                for img_type, counts in image_files["by_type"].items():
                    if img_type not in self.results["image_files_found"]["by_type"]:
                        self.results["image_files_found"]["by_type"][img_type] = {"active": 0, "deleted": 0}
                    
                    self.results["image_files_found"]["by_type"][img_type]["active"] += counts["active"]
                    self.results["image_files_found"]["by_type"][img_type]["deleted"] += counts["deleted"]
        
        # 5. Vyhodnotenie stratégie
        method, tool, estimated_time, notes = self.determine_recovery_strategy()
        
        self.results["recommended_method"] = method
        self.results["recommended_tool"] = tool
        self.results["estimated_time_minutes"] = estimated_time
        self.results["notes"] = notes
        self.results["success"] = True
        
        # 6. Finálny výpis
        self._print("\n" + "="*70, "TITLE")
        self._print("ANALYSIS COMPLETED", "OK")
        self._print("="*70, "TITLE")
        self._print(f"Filesystem recognized: {self.results['filesystem_recognized']}", "INFO")
        self._print(f"Directory structure readable: {self.results['directory_structure_readable']}", "INFO")
        self._print(f"Image files found: {self.results['image_files_found']['total']}", "INFO")
        self._print(f"Recovery method: {method}", "INFO")
        self._print("="*70 + "\n", "TITLE")
        
        return self.results
    
    def save_json_report(self):
        """Uloženie JSON reportu"""
        json_file = self.output_dir / f"{self.case_id}_filesystem_analysis.json"
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        self._print(f"Analysis report saved: {json_file}", "OK")
        return str(json_file)


def main():
    """
    Hlavná funkcia - entry point pre Penterep platformu
    """
    
    print("\n" + "="*70)
    print("FOR-COL-FS-ANALYSIS: Filesystem Analysis")
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
    analyzer = FilesystemAnalyzer(case_id)
    results = analyzer.run_analysis()
    
    # Uloženie JSON
    if results["success"]:
        json_path = analyzer.save_json_report()
        print(f"\nFilesystem analysis completed successfully")
        print(f"Recommended method: {results['recommended_method']}")
        print(f"Next step: Step 11 (Recovery Strategy Decision)")
        sys.exit(0)
    else:
        print("\nFilesystem analysis failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - KEY FEATURES
================================================================================

FIVE-PHASE ANALYSIS PROCESS
1. Partition analysis (mmls) - Detects partition table type and all partitions
2. Filesystem analysis (fsstat) - Identifies FS type and metadata
3. Directory structure test (fls) - Checks if directory entries are readable
4. Image file identification - Counts and categorizes image files
5. Recovery strategy determination - Recommends optimal recovery method

INTELLIGENT TOOL INTEGRATION
- Automatically loads image path from Step 6 verification output
- Uses The Sleuth Kit (TSK) tools for professional forensic analysis
- Handles multiple partitions and partition table types
- Supports superfloppy format (no partition table)

COMPREHENSIVE FILESYSTEM SUPPORT
- FAT12/16/32 (most common on USB/SD cards)
- exFAT (modern flash media)
- NTFS (Windows drives)
- ext2/3/4 (Linux)
- HFS+/APFS (macOS)
- ISO 9660 (CD/DVD)

IMAGE FILE DETECTION
Supports all major photo formats:
- JPEG/JPG (compressed)
- PNG (lossless)
- GIF (animated)
- BMP (bitmap)
- TIFF/TIF (high quality)
- RAW formats (CR2, NEF, ARW, DNG, ORF, RAF)
- HEIC/HEIF (Apple)
- WebP (Google)

RECOVERY STRATEGY LOGIC
1. FILESYSTEM SCAN (fastest, best quality):
   - Condition: FS recognized AND directory structure readable
   - Tool: fls + icat
   - Preserves: Original filenames, directory structure, timestamps
   - Time: ~0.1 min per file

2. HYBRID APPROACH (medium speed, good quality):
   - Condition: FS recognized BUT directory structure damaged
   - Tool: fls + photorec
   - Preserves: Some filenames may be lost
   - Time: ~0.3 min per file

3. FILE CARVING (slowest, most thorough):
   - Condition: FS not recognized OR severely damaged
   - Tool: photorec / foremost
   - Preserves: Nothing - generic filenames assigned
   - Time: ~0.5 min per file
   - Note: Finds files by signature, not filesystem metadata

AUTOMATIC DECISION MAKING
- No manual intervention needed
- Clear recommendations for Step 11
- Estimated time calculations
- Detailed notes explaining the choice

================================================================================
EXAMPLE OUTPUT - HEALTHY FAT32 SD CARD
================================================================================

======================================================================
FILESYSTEM ANALYSIS
Case ID: PHOTO-2025-01-26-001
======================================================================

Loading image path from Step 6...
[✓] Image path loaded: /mnt/user-data/outputs/PHOTO-2025-01-26-001.dd

Checking The Sleuth Kit tools...
[✓] mmls: Found
[✓] fsstat: Found
[✓] fls: Found

======================================================================
PHASE 1: PARTITION ANALYSIS
======================================================================

[✓] Partition table found:
[i] Partition 1: offset=2048, size=62521344 sectors

[✓] Partition table type: DOS/MBR
[✓] Found 1 partition(s)

[i] Analyzing filesystem at offset 2048...
[✓] Filesystem type: FAT32
[i] Volume label: SDCARD

[i] Testing directory structure at offset 2048...
[✓] Directory structure readable: 1547 entries found
[i] Active files: 1432
[i] Deleted files: 115

Identifying image files...
[✓] Total image files found: 487
[i] Active: 412, Deleted: 75
[i]   JPEG: 452 (active: 389, deleted: 63)
[i]   PNG: 28 (active: 20, deleted: 8)
[i]   RAW: 7 (active: 3, deleted: 4)

======================================================================
RECOVERY STRATEGY DETERMINATION
======================================================================
[✓] Recommended method: FILESYSTEM SCAN
[i] Recommended tool: fls + icat (The Sleuth Kit)
[i] Estimated time: ~49 minutes

======================================================================
ANALYSIS COMPLETED
======================================================================
[i] Filesystem recognized: True
[i] Directory structure readable: True
[i] Image files found: 487
[i] Recovery method: filesystem_scan
======================================================================

[✓] Analysis report saved: /mnt/user-data/outputs/PHOTO-2025-01-26-001_filesystem_analysis.json

Filesystem analysis completed successfully
Recommended method: filesystem_scan
Next step: Step 11 (Recovery Strategy Decision)

================================================================================
EXAMPLE OUTPUT - DAMAGED FILESYSTEM
================================================================================

======================================================================
PHASE 1: PARTITION ANALYSIS
======================================================================

[!] No partition table detected (superfloppy format)
[i] Entire device is likely a single filesystem

[i] Analyzing filesystem at offset 0...
[✗] Filesystem not recognized at offset 0

[i] Testing directory structure at offset 0...
[!] Skipping fls (filesystem not recognized)

======================================================================
RECOVERY STRATEGY DETERMINATION
======================================================================
[!] Recommended method: FILE CARVING
[i] Recommended tool: photorec / foremost
[i] Estimated time: ~90 minutes

======================================================================
ANALYSIS COMPLETED
======================================================================
[i] Filesystem recognized: False
[i] Directory structure readable: False
[i] Image files found: 0
[i] Recovery method: file_carving
======================================================================

================================================================================
JSON OUTPUT FORMAT
================================================================================

{
  "case_id": "PHOTO-2025-01-26-001",
  "timestamp": "2025-01-26T20:15:00Z",
  "image_file": "/mnt/user-data/outputs/PHOTO-2025-01-26-001.dd",
  "partition_table_type": "DOS/MBR",
  "partitions": [
    {
      "number": 1,
      "offset": 2048,
      "size_sectors": 62521344,
      "type": "00:00",
      "description": "Linux (0x83)",
      "filesystem": {
        "offset": 2048,
        "recognized": true,
        "type": "FAT32",
        "state": "recognized",
        "label": "SDCARD",
        "uuid": "1234-5678",
        "sector_size": 512,
        "cluster_size": 4096,
        "total_clusters": 7815168,
        "free_clusters": 2341234
      },
      "directory_readable": true,
      "file_counts": {
        "active": 1432,
        "deleted": 115,
        "total": 1547
      },
      "image_files": {
        "total": 487,
        "active": 412,
        "deleted": 75,
        "by_type": {
          "jpeg": {"active": 389, "deleted": 63},
          "png": {"active": 20, "deleted": 8},
          "raw": {"active": 3, "deleted": 4}
        }
      }
    }
  ],
  "filesystem_recognized": true,
  "directory_structure_readable": true,
  "image_files_found": {
    "total": 487,
    "active": 412,
    "deleted": 75,
    "by_type": {
      "jpeg": {"active": 389, "deleted": 63},
      "png": {"active": 20, "deleted": 8},
      "raw": {"active": 3, "deleted": 4}
    }
  },
  "recommended_method": "filesystem_scan",
  "recommended_tool": "fls + icat (The Sleuth Kit)",
  "estimated_time_minutes": 49,
  "notes": [
    "Filesystem structure intact - can use filesystem-based recovery",
    "Original filenames and directory structure will be preserved",
    "Fast recovery method - recommended approach"
  ],
  "success": true
}

================================================================================
USAGE EXAMPLES
================================================================================

INTERACTIVE MODE:
$ python3 step10_analyze_filesystem.py
Case ID (e.g., PHOTO-2025-01-26-001): PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step10_analyze_filesystem.py PHOTO-2025-01-26-001

INTEGRATION WITH PENTEREP PLATFORM:
- Automatically called after Step 6 (Hash Verification)
- Reads image path from Step 6 JSON output
- Outputs JSON for Step 11 to consume
- All files saved to /mnt/user-data/outputs/

================================================================================
TROUBLESHOOTING
================================================================================

ERROR: Cannot find forensic image
- Solution: Run Steps 5 and 6 first
- Check that image file exists in /mnt/user-data/outputs/

ERROR: Missing tools (mmls, fsstat, fls)
- Solution: Install The Sleuth Kit
- Ubuntu/Debian: sudo apt-get install sleuthkit
- Verify: mmls --version

WARNING: No partition table detected
- Not necessarily an error
- Many USB/SD cards use superfloppy format
- Script will analyze entire device as single filesystem

ERROR: Filesystem not recognized
- May indicate damaged or exotic filesystem
- Script will recommend file carving approach
- This is expected for severely damaged media

TIMEOUT during fls
- Large media may take >10 minutes to scan
- Timeout set to 600 seconds (10 min)
- Can be increased in script if needed

================================================================================
NEXT STEPS AFTER ANALYSIS
================================================================================

STEP 11: Recovery Strategy Decision
- Reads JSON output from this step
- Makes final decision based on:
  * Filesystem recognition status
  * Directory structure readability
  * Number of image files found
  * User preferences (speed vs completeness)
- Branches to either:
  * Step 12A: Filesystem-based scan (if FS recognized)
  * Step 12B: File carving (if FS damaged/unknown)

STEP 12A: Filesystem-based Recovery
- Uses fls to list files
- Uses icat to extract files
- Preserves original filenames
- Faster than carving
- Only works with recognized filesystems

STEP 12B: File Carving
- Uses photorec or foremost
- Searches for file signatures
- Slower but more thorough
- Assigns generic filenames
- Works on any media regardless of FS

================================================================================
"""