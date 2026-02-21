#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptfilesystemanalysis - Forensic filesystem analysis tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import sys
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

# Skript je vždy spúšťaný ako nainštalovaný balíček cez Penterep platformu,
# relatívny import _version.py je preto vždy validný.
from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SCRIPTNAME         = "ptfilesystemanalysis"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"
FLS_TIMEOUT        = 600  # 10 minutes for large media

# Supported image file extensions grouped by format family
IMAGE_EXTENSIONS: Dict[str, List[str]] = {
    "jpeg":  [".jpg", ".jpeg"],
    "png":   [".png"],
    "gif":   [".gif"],
    "bmp":   [".bmp"],
    "tiff":  [".tiff", ".tif"],
    "raw":   [".raw", ".cr2", ".nef", ".arw", ".dng", ".orf", ".raf"],
    "heic":  [".heic", ".heif"],
    "webp":  [".webp"],
}

# Filesystem type keyword → canonical name mapping
FS_TYPE_MAP: Dict[str, str] = {
    "FAT32": "FAT32", "FAT16": "FAT16", "FAT12": "FAT12",
    "exFAT": "exFAT", "NTFS": "NTFS",
    "Ext4": "ext4", "ext4": "ext4",
    "Ext3": "ext3", "ext3": "ext3",
    "Ext2": "ext2", "ext2": "ext2",
    "HFS+": "HFS+", "APFS": "APFS",
    "ISO 9660": "ISO9660",
}

# fsstat output field extraction patterns
FS_METADATA_PATTERNS: Dict[str, str] = {
    "label":         r"(?:Volume Label|Label):\s*(.+)",
    "uuid":          r"(?:Serial Number|UUID):\s*(.+)",
    "sectorSize":    r"(?:Sector Size|sector size):\s*(\d+)",
    "clusterSize":   r"(?:Cluster Size|Block Size):\s*(\d+)",
    "totalClusters": r"(?:Total Clusters|Block Count):\s*(\d+)",
    "freeClusters":  r"(?:Free Clusters|Free Blocks):\s*(\d+)",
}

# Recovery strategy lookup: (fs_recognised, dir_readable) → (method, tool, est_minutes, notes)
RECOVERY_STRATEGIES: Dict[Tuple[bool, bool], Tuple[str, str, int, List[str]]] = {
    (True,  True):  ("filesystem_scan", "fls + icat (The Sleuth Kit)", 15,
                     ["Filesystem intact – filesystem-based scan recommended.",
                      "Original filenames and directory structure preserved.",
                      "Fastest recovery method."]),
    (True,  False): ("hybrid",          "fls + photorec",               60,
                     ["Filesystem recognised but directory structure damaged.",
                      "Hybrid: filesystem scan + file carving on unallocated space.",
                      "Some filenames may be lost."]),
    (False, False): ("file_carving",    "photorec / foremost",           90,
                     ["Filesystem not recognised or severely damaged.",
                      "File carving required (signature-based recovery).",
                      "Original filenames and directory structure will be lost."]),
}

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtFilesystemAnalysis:
    """
    Forensic filesystem analysis tool – ptlibs compliant.

    Five-phase analysis:
      1. Partition analysis  (mmls)   – detect partition table and partitions
      2. Filesystem analysis (fsstat) – identify FS type and metadata
      3. Directory test      (fls)    – check if directory structure is readable
      4. Image identification         – count and categorise photo files
      5. Strategy determination       – recommend optimal recovery method

    Output JSON feeds into Step 11 (Recovery Strategy Decision).
    Compliant with ISO/IEC 27037:2012 and NIST SP 800-86.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.image_path:            Optional[Path] = None
        self.partitions:            List[Dict]     = []
        self.filesystem_recognized: bool           = False
        self.directory_readable:    bool           = False

        self.ptjsonlib.add_properties({
            "caseId":                     self.case_id,
            "outputDirectory":            str(self.output_dir),
            "timestamp":                  datetime.now(timezone.utc).isoformat(),
            "scriptVersion":              __version__,
            "imagePath":                  None,
            "partitionTableType":         None,
            "partitionsFound":            0,
            "filesystemRecognized":       False,
            "directoryStructureReadable": False,
            "imageFilesFound": {
                "total": 0, "active": 0, "deleted": 0, "byType": {}
            },
            "recommendedMethod":          None,
            "recommendedTool":            None,
            "estimatedTimeMinutes":       None,
            "dryRun":                     self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}", "INFO", condition=not self.args.json)

    # --- helpers ------------------------------------------------------------

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        """Append a result node to the JSON output."""
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type,
            properties={"success": success, **kwargs},
        ))

    def _check_command(self, cmd: str) -> bool:
        """Check if a shell command is available on PATH."""
        try:
            subprocess.run(["which", cmd], capture_output=True, check=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def _run_command(self, cmd: List[str], timeout: int = 300) -> Dict[str, Any]:
        """Execute command with timeout. Returns dict with success/stdout/stderr/returncode."""
        base = {"success": False, "stdout": "", "stderr": "", "returncode": -1}

        if self.dry_run:
            ptprint(f"[DRY-RUN] {' '.join(cmd)}", "INFO", condition=not self.args.json)
            return {**base, "success": True, "stdout": "[DRY-RUN]"}

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, check=False)
            base.update({"success": proc.returncode == 0, "stdout": proc.stdout.strip(),
                          "stderr": proc.stderr.strip(), "returncode": proc.returncode})
        except subprocess.TimeoutExpired:
            base["stderr"] = f"Timeout after {timeout}s"
        except Exception as exc:
            base["stderr"] = str(exc)

        return base

    # --- steps --------------------------------------------------------------

    def load_image_path(self) -> bool:
        """Step 1: Load forensic image path from Step 6 verification JSON."""
        ptprint("\n[1/4] Loading Image Path from Step 6", "TITLE", condition=not self.args.json)

        # Primary: load from Step 6 verification report
        candidates = sorted(
            self.output_dir.glob(f"{self.case_id}_verification*.json"),
            reverse=True
        )

        for candidate in candidates:
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                image_path = (data.get("result", {})
                                  .get("properties", {})
                                  .get("imagePath"))
                if image_path and Path(image_path).exists():
                    self.image_path = Path(image_path)
                    self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})
                    ptprint(f"Image path loaded from {candidate.name}: {self.image_path.name}",
                            "OK", condition=not self.args.json)
                    self._add_node("imagePathCheck", True, imagePath=str(self.image_path),
                                   sourceFile=str(candidate))
                    return True
            except Exception as exc:
                ptprint(f"Warning: could not read {candidate.name}: {exc}",
                        "WARNING", condition=not self.args.json)

        # Fallback: default image file location
        fallback = self.output_dir / f"{self.case_id}.dd"
        if fallback.exists():
            self.image_path = fallback
            self.ptjsonlib.add_properties({"imagePath": str(fallback)})
            ptprint(f"Image found at default location: {fallback.name}",
                    "OK", condition=not self.args.json)
            self._add_node("imagePathCheck", True, imagePath=str(fallback),
                           sourceFile="default location")
            return True

        ptprint("Cannot find forensic image – run Steps 5 and 6 first.",
                "ERROR", condition=not self.args.json)
        self._add_node("imagePathCheck", False, error="Image not found")
        return False

    def check_tools(self) -> bool:
        """Step 2: Verify The Sleuth Kit tools are available."""
        ptprint("\n[2/4] Checking The Sleuth Kit Tools", "TITLE", condition=not self.args.json)

        missing = [t for t in ("mmls", "fsstat", "fls") if not self._check_command(t)]

        if missing:
            ptprint(f"Missing tools: {', '.join(missing)} – "
                    f"install with: sudo apt-get install sleuthkit",
                    "ERROR", condition=not self.args.json)
            self._add_node("toolsCheck", False, missingTools=missing)
            return False

        ptprint("All TSK tools available (mmls, fsstat, fls).", "OK", condition=not self.args.json)
        self._add_node("toolsCheck", True, toolsChecked=["mmls", "fsstat", "fls"])
        return True

    def analyze_partitions(self) -> bool:
        """Phase 1: Detect partition table and partitions using mmls."""
        ptprint("\n[3/4] Analyzing Partition Structure (mmls)", "TITLE", condition=not self.args.json)

        r = self._run_command(["mmls", str(self.image_path)])

        if not r["success"]:
            # No partition table – superfloppy (whole device is one FS)
            ptprint("No partition table detected – superfloppy format assumed.",
                    "WARNING", condition=not self.args.json)
            self.partitions = [{"number": 0, "offset": 0, "sizeSectors": None,
                                 "type": "whole_device",
                                 "description": "Superfloppy – no partition table"}]
            self.ptjsonlib.add_properties({"partitionTableType": "superfloppy",
                                           "partitionsFound": 1})
            self._add_node("partitionAnalysis", True, partitionTableType="superfloppy",
                           partitionsFound=1, partitions=self.partitions)
            return True

        # Parse mmls output
        table_type = "unknown"
        partitions  = []

        for line in r["stdout"].splitlines():
            if "DOS Partition Table" in line or ("DOS" in line and "Partition" in line):
                table_type = "DOS/MBR"
            elif "GUID Partition Table" in line or "GPT" in line:
                table_type = "GPT"

            # Entry format: 002:  00:00  00001  62521343  62521343  Linux (0x83)
            m = re.match(r"(\d+):\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)", line)
            if m:
                slot, ptype, start, _end, size, desc = (
                    int(m.group(1)), m.group(2),
                    int(m.group(3)), m.group(4),
                    int(m.group(5)), m.group(6).strip()
                )
                if ptype.lower() in ("meta", "-----") or size == 0:
                    continue
                partitions.append({"number": slot, "offset": start,
                                    "sizeSectors": size, "type": ptype,
                                    "description": desc})
                ptprint(f"  Partition {slot}: offset={start} | size={size} sectors | {desc}",
                        "INFO", condition=not self.args.json)

        self.partitions = partitions or [{"number": 0, "offset": 0, "sizeSectors": None,
                                           "type": "whole_device", "description": "Fallback"}]
        ptprint(f"Partition table: {table_type} | {len(self.partitions)} partition(s) found.",
                "OK", condition=not self.args.json)

        self.ptjsonlib.add_properties({"partitionTableType": table_type,
                                       "partitionsFound": len(self.partitions)})
        self._add_node("partitionAnalysis", True, partitionTableType=table_type,
                       partitionsFound=len(self.partitions), partitions=self.partitions)
        return True

    def analyze_filesystem(self, partition: Dict) -> Dict:
        """Phase 2: Identify filesystem type and metadata using fsstat."""
        offset = partition.get("offset", 0)
        ptprint(f"\n  fsstat (offset={offset})", "INFO", condition=not self.args.json)

        fs_info = {"offset": offset, "recognized": False, "type": "unknown",
                   "label": None, "uuid": None, "sectorSize": None,
                   "clusterSize": None, "totalClusters": None, "freeClusters": None}

        r = self._run_command(["fsstat", "-o", str(offset), str(self.image_path)])
        if not r["success"]:
            ptprint(f"  Filesystem not recognised at offset {offset}.",
                    "WARNING", condition=not self.args.json)
            return fs_info

        output = r["stdout"]

        # Identify FS type
        for keyword, canonical in FS_TYPE_MAP.items():
            if keyword in output:
                fs_info["type"] = canonical
                break

        # Extract metadata
        for field, pattern in FS_METADATA_PATTERNS.items():
            m = re.search(pattern, output)
            if m:
                val = m.group(1).strip()
                fs_info[field] = int(val) if field not in ("label", "uuid") else val

        if fs_info["type"] != "unknown":
            fs_info["recognized"] = True
            self.filesystem_recognized = True
            ptprint(f"  Type: {fs_info['type']}"
                    + (f" | Label: {fs_info['label']}" if fs_info["label"] else ""),
                    "OK", condition=not self.args.json)
        else:
            ptprint("  Could not identify filesystem type.", "WARNING", condition=not self.args.json)

        return fs_info

    def test_directory_structure(self, partition: Dict,
                                  fs_info: Dict) -> Tuple[bool, int, int, List[Dict]]:
        """Phase 3: Test directory readability using fls."""
        offset = partition.get("offset", 0)
        ptprint(f"  fls (offset={offset})", "INFO", condition=not self.args.json)

        if not fs_info.get("recognized"):
            ptprint("  Skipping fls – filesystem not recognised.", "WARNING",
                    condition=not self.args.json)
            return False, 0, 0, []

        r = self._run_command(["fls", "-r", "-o", str(offset), str(self.image_path)],
                              timeout=FLS_TIMEOUT)

        if not r["success"] or not r["stdout"]:
            ptprint("  Directory structure not readable.", "ERROR", condition=not self.args.json)
            return False, 0, 0, []

        file_list   = []
        active      = 0
        deleted     = 0

        for line in r["stdout"].splitlines():
            if not line.strip():
                continue
            is_deleted = "*" in line
            m = re.search(r":\s*(.+)$", line)
            if m:
                file_list.append({"filename": m.group(1).strip(), "deleted": is_deleted})
                if is_deleted:
                    deleted += 1
                else:
                    active += 1

        self.directory_readable = True
        ptprint(f"  Directory readable: {active + deleted} entries "
                f"(active: {active}, deleted: {deleted}).",
                "OK", condition=not self.args.json)
        return True, active, deleted, file_list

    def identify_image_files(self, file_list: List[Dict]) -> Dict:
        """Phase 4: Count image files by format and status."""
        counts: Dict = {"total": 0, "active": 0, "deleted": 0, "byType": {
            t: {"active": 0, "deleted": 0} for t in IMAGE_EXTENSIONS
        }}

        for entry in file_list:
            name = entry["filename"].lower()
            for fmt, exts in IMAGE_EXTENSIONS.items():
                if any(name.endswith(e) for e in exts):
                    counts["total"]  += 1
                    key = "deleted" if entry["deleted"] else "active"
                    counts[key]      += 1
                    counts["byType"][fmt][key] += 1
                    break

        if counts["total"] > 0:
            ptprint(f"  Image files: {counts['total']} "
                    f"(active: {counts['active']}, deleted: {counts['deleted']})",
                    "OK", condition=not self.args.json)
            for fmt, c in counts["byType"].items():
                if c["active"] + c["deleted"] > 0:
                    ptprint(f"    {fmt.upper()}: {c['active'] + c['deleted']}", "INFO",
                            condition=not self.args.json)
        else:
            ptprint("  No image files found.", "WARNING", condition=not self.args.json)

        return counts

    def determine_recovery_strategy(self,
                                    total_images: int) -> Tuple[str, str, int, List[str]]:
        """Phase 5: Select optimal recovery strategy based on analysis results."""
        ptprint("\n[4/4] Determining Recovery Strategy", "TITLE", condition=not self.args.json)

        key = (self.filesystem_recognized, self.directory_readable)
        method, tool, est, notes = RECOVERY_STRATEGIES.get(
            key, RECOVERY_STRATEGIES[(False, False)]  # fallback to file_carving
        )

        ptprint(f"Method: {method} | Tool: {tool} | Est. time: ~{est} min",
                "OK" if method == "filesystem_scan" else "WARNING",
                condition=not self.args.json)
        for note in notes:
            ptprint(f"  {note}", "INFO", condition=not self.args.json)

        return method, tool, est, notes

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        """Execute the full filesystem analysis workflow."""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"FILESYSTEM ANALYSIS v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_image_path():
            self.ptjsonlib.set_status("finished"); return
        if not self.check_tools():
            self.ptjsonlib.set_status("finished"); return
        if not self.analyze_partitions():
            self.ptjsonlib.set_status("finished"); return

        # Per-partition analysis (phases 2–4)
        total: Dict = {"total": 0, "active": 0, "deleted": 0, "byType": {}}
        fs_nodes: List[Dict] = []

        for part in self.partitions:
            fs_info = self.analyze_filesystem(part)
            readable, active, deleted, file_list = self.test_directory_structure(part, fs_info)

            img = self.identify_image_files(file_list) if readable else \
                  {"total": 0, "active": 0, "deleted": 0, "byType": {}}

            # Accumulate totals
            total["total"]   += img["total"]
            total["active"]  += img["active"]
            total["deleted"] += img["deleted"]
            for fmt, c in img.get("byType", {}).items():
                if fmt not in total["byType"]:
                    total["byType"][fmt] = {"active": 0, "deleted": 0}
                total["byType"][fmt]["active"]  += c["active"]
                total["byType"][fmt]["deleted"] += c["deleted"]

            fs_nodes.append({
                "partition": part["number"], "offset": part["offset"],
                "filesystemType": fs_info["type"],
                "filesystemRecognized": fs_info["recognized"],
                "directoryReadable": readable,
                "imageFiles": img,
            })

        self._add_node("filesystemAnalysis", True, partitions=fs_nodes)

        # Phase 5: strategy
        method, tool, est, notes = self.determine_recovery_strategy(total["total"])

        self.ptjsonlib.add_properties({
            "filesystemRecognized":       self.filesystem_recognized,
            "directoryStructureReadable": self.directory_readable,
            "imageFilesFound":            total,
            "recommendedMethod":          method,
            "recommendedTool":            tool,
            "estimatedTimeMinutes":       est,
        })
        self._add_node("recoveryStrategy", True, recommendedMethod=method,
                       recommendedTool=tool, estimatedTimeMinutes=est, notes=notes,
                       filesystemRecognized=self.filesystem_recognized,
                       directoryReadable=self.directory_readable,
                       imageFilesFound=total["total"])

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("ANALYSIS COMPLETED", "OK", condition=not self.args.json)
        ptprint(f"FS recognised: {self.filesystem_recognized} | "
                f"Directory readable: {self.directory_readable} | "
                f"Images: {total['total']} | Method: {method}",
                "INFO", condition=not self.args.json)
        ptprint("Next: Step 11 – Recovery Strategy Decision",
                "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        """Output JSON report to stdout (--json) or to file."""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        outfile = self.output_dir / f"{self.case_id}_filesystem_analysis.json"
        outfile.write_text(self.ptjsonlib.get_result_json(), encoding="utf-8")
        ptprint(f"Report saved: {outfile}", "OK", condition=not self.args.json)
        return str(outfile)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_help() -> List[Dict]:
    return [
        {"description": ["Forensic filesystem analysis tool – ptlibs compliant",
                         "Analyses FS structure and recommends optimal recovery strategy"]},
        {"usage": ["ptfilesystemanalysis <case-id> [options]"]},
        {"usage_example": ["ptfilesystemanalysis PHOTO-2025-001",
                           "ptfilesystemanalysis CASE-042 --json",
                           "ptfilesystemanalysis TEST-001 --dry-run"]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate without executing TSK commands"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"notes": [
            "Analysis: mmls (partitions) → fsstat (FS type) → fls (directory) → strategy",
            "Methods:  filesystem_scan (intact FS) | hybrid (damaged dirs) | file_carving (no FS)",
            "Requires Step 6 (ptimageverification) results",
            "Uses The Sleuth Kit: mmls, fsstat, fls",
            "Complies with ISO/IEC 27037:2012 and NIST SP 800-86",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-v", "--verbose",    action="store_true")
    parser.add_argument("-q", "--quiet",      action="store_true")
    parser.add_argument("--dry-run",          action="store_true")
    parser.add_argument("-j", "--json",       action="store_true")
    parser.add_argument("--version", action="version", version=f"{SCRIPTNAME} {__version__}")
    parser.add_argument("--socket-address",   default=None)
    parser.add_argument("--socket-port",      default=None)
    parser.add_argument("--process-ident",    default=None)

    if len(sys.argv) == 1 or {"-h", "--help"} & set(sys.argv):
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    if args.json:
        args.quiet = True
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main() -> int:
    try:
        args = parse_args()

        analyzer = PtFilesystemAnalysis(args)
        analyzer.run()
        analyzer.save_report()

        return 0 if analyzer.ptjsonlib.json_data["result"]["properties"].get(
            "recommendedMethod") else 1

    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())