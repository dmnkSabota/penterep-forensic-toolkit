#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptfilesystemanalysis - Forensic filesystem analysis tool
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import (
        DEFAULT_OUTPUT_DIR, IMAGE_EXTENSIONS, FORMAT_GROUP_MAP, FS_TYPE_MAP,
        RECOVERY_STRATEGIES, MMLS_TIMEOUT, FSSTAT_TIMEOUT, FLS_TIMEOUT,
    )
except ImportError:
    from _constants import (
        DEFAULT_OUTPUT_DIR, IMAGE_EXTENSIONS, FORMAT_GROUP_MAP, FS_TYPE_MAP,
        RECOVERY_STRATEGIES, MMLS_TIMEOUT, FSSTAT_TIMEOUT, FLS_TIMEOUT,
    )

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptfilesystemanalysis"


class PtFilesystemAnalysis(ForensicToolBase):
    """Filesystem analysis — mmls/fsstat/fls (The Sleuth Kit), NIST SP 800-86 §2.2, ISO/IEC 27042:2015 §5."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.image_path = Path(args.image)
        self.output_dir = Path(args.output_dir)

        self.image_size: Optional[int] = None
        self.partition_table_type: Optional[str] = None
        self.partitions: List[Dict] = []
        self.partition_details: List[Dict] = []
        self.filesystem_recognized: bool = False
        self.directory_readable: bool = False
        self.total_images: int = 0

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({"imagePath": str(self.image_path)})

    def check_tools(self) -> bool:
        ptprint("\n[1/2] Checking Sleuth Kit tools", "TITLE", condition=self._out())
        tools = {"mmls": "partition table parser", "fsstat": "filesystem statistics", "fls": "file listing"}
        missing = [t for t in tools if not self._check_command(t)]

        for t, desc in tools.items():
            ptprint(f"  [{'OK' if t not in missing else 'ERROR'}] {t}: {desc}",
                    "OK" if t not in missing else "ERROR", condition=self._out())

        if missing:
            ptprint(f"Missing tools: {', '.join(missing)} - sudo apt install sleuthkit",
                    "ERROR", condition=self._out())
            self._add_node("toolsCheck", False, missingTools=missing)
            return False

        self._add_node("toolsCheck", True, toolsChecked=list(tools))
        return True

    def analyse_partitions(self) -> bool:
        ptprint("\n[2/2] Analysing partition table", "TITLE", condition=self._out())

        r = self._run_command(["mmls", str(self.image_path)], timeout=MMLS_TIMEOUT)

        if not r["success"] or self.dry_run:
            ptprint("  No partition table detected - superfloppy assumed.", "INFO", condition=self._out())
            self.partition_table_type = "superfloppy"
            self.partitions = [{"number": 0, "offset": 0, "sizeSectors": None,
                                 "type": "whole_device", "description": "Superfloppy - no partition table"}]
            self._add_node("partitionScan", True, tableType=self.partition_table_type, partitionsFound=1)
            return True

        table_type, partitions = "unknown", []
        for line in r["stdout"].splitlines():
            if "DOS Partition Table" in line or ("DOS" in line and "Partition" in line):
                table_type = "DOS/MBR"
            elif "GUID Partition Table" in line or "GPT" in line:
                table_type = "GPT"
            m = re.match(r"(\d+):\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)", line)
            if m:
                slot, ptype = int(m.group(1)), m.group(2)
                start, size, desc = int(m.group(3)), int(m.group(5)), m.group(6).strip()
                if ptype.lower() == "meta" or ptype.startswith("-") or size == 0:
                    continue
                partitions.append({"number": slot, "offset": start, "sizeSectors": size,
                                    "type": ptype, "description": desc})
                ptprint(f"  Partition {slot}: offset={start}  {size} sectors  {desc}",
                        "INFO", condition=self._out())

        if not partitions:
            partitions = [{"number": 0, "offset": 0, "sizeSectors": None,
                            "type": "whole_device", "description": "Fallback"}]

        self.partition_table_type, self.partitions = table_type, partitions
        ptprint(f"  Table type: {table_type}  |  {len(partitions)} partition(s) found",
                "OK", condition=self._out())
        self._add_node("partitionScan", True, tableType=table_type, partitionsFound=len(partitions))
        return True

    def _analyse_filesystem(self, partition: Dict) -> Dict:
        offset = partition["offset"]
        ptprint(f"  fsstat (offset={offset}) ...", "INFO", condition=self._out())

        fs_info: Dict = {"offset": offset, "recognized": False, "type": "unknown",
                          "label": None, "uuid": None, "sectorSize": None, "clusterSize": None}

        r = self._run_command(["fsstat", "-o", str(offset), str(self.image_path)],
                               timeout=FSSTAT_TIMEOUT)

        if not r["success"] or not r["stdout"]:
            if not self.dry_run:
                ptprint(f"  Filesystem not recognised at offset {offset}.", "WARNING", condition=self._out())
            return fs_info

        for keyword, canonical in FS_TYPE_MAP.items():
            if keyword in r["stdout"]:
                fs_info["type"] = canonical
                break

        for field, pattern in {
            "label": r"Volume Label.*?:\s*([^\n]+)",
            "uuid": r"(?:Serial Number|UUID):\s*(.+)",
            "sectorSize": r"(?:Sector Size|sector size):\s*(\d+)",
            "clusterSize": r"(?:Cluster Size|Block Size):\s*(\d+)",
        }.items():
            m = re.search(pattern, r["stdout"])
            if m:
                val = m.group(1).strip()
                fs_info[field] = int(val) if field not in ("label", "uuid") else val

        if fs_info["type"] != "unknown":
            fs_info["recognized"] = True
            self.filesystem_recognized = True
            label_str = f"  |  Label: {fs_info['label']}" if fs_info["label"] else ""
            ptprint(f"  ✓ Type: {fs_info['type']}{label_str}", "OK", condition=self._out())

        return fs_info

    def _test_directory_structure(self, partition: Dict, fs_info: Dict) -> Tuple[bool, int, int, List[Dict]]:
        offset = partition["offset"]
        ptprint(f"  fls (offset={offset}) ...", "INFO", condition=self._out())

        if not fs_info.get("recognized"):
            ptprint("  Skipping fls - filesystem not recognised.", "INFO", condition=self._out())
            return False, 0, 0, []

        r = self._run_command(["fls", "-r", "-o", str(offset), str(self.image_path)],
                               timeout=FLS_TIMEOUT)

        if not r["success"] or not r["stdout"]:
            if not self.dry_run:
                ptprint("  Directory structure not readable.", "WARNING", condition=self._out())
            return False, 0, 0, []

        file_list, active, deleted = [], 0, 0
        for line in r["stdout"].splitlines():
            if not line.strip():
                continue
            is_deleted = "*" in line
            m = re.search(r":\s*(.+)$", line)
            if m:
                file_list.append({"filename": m.group(1).strip(), "deleted": is_deleted})
                deleted += is_deleted
                active += not is_deleted

        self.directory_readable = True
        ptprint(f"  ✓ {active + deleted} entries  (active: {active}, deleted: {deleted})",
                "OK", condition=self._out())
        return True, active, deleted, file_list

    def _identify_image_files(self, file_list: List[Dict]) -> Dict:
        counts: Dict = {
            "total": 0, "active": 0, "deleted": 0,
            "byFormat": {g: {"active": 0, "deleted": 0} for g in set(FORMAT_GROUP_MAP.values())},
        }
        for entry in file_list:
            ext = Path(entry["filename"]).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                continue
            group = FORMAT_GROUP_MAP.get(ext.lstrip("."), "other")
            counts["total"] += 1
            sk = "deleted" if entry["deleted"] else "active"
            counts[sk] += 1
            counts["byFormat"].setdefault(group, {"active": 0, "deleted": 0})
            counts["byFormat"][group][sk] += 1

        if counts["total"]:
            ptprint(f"  Image files: {counts['total']}  "
                    f"(active: {counts['active']}, deleted: {counts['deleted']})",
                    "INFO", condition=self._out())
        else:
            ptprint("  No image files found.", "INFO", condition=self._out())

        return counts

    def _determine_strategy(self) -> Tuple[str, str, int, List[str]]:
        return RECOVERY_STRATEGIES.get(
            (self.filesystem_recognized, self.directory_readable),
            RECOVERY_STRATEGIES[(False, False)]
        )

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"FILESYSTEM ANALYSIS v{__version__}  |  Case: {self.case_id}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.image_path.exists() and not self.dry_run:
            ptprint(f"Image not found: {self.image_path}", "ERROR", condition=True)
            self.ptjsonlib.set_status("finished")
            return

        self.image_size = self.image_path.stat().st_size if not self.dry_run else 0

        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return
        if not self.analyse_partitions():
            self.ptjsonlib.set_status("finished")
            return

        for part in self.partitions:
            ptprint(f"\n  -- Partition {part['number']} (offset={part['offset']}) --",
                    "INFO", condition=self._out())
            fs_info = self._analyse_filesystem(part)
            readable, active, deleted, file_list = self._test_directory_structure(part, fs_info)
            img_counts = (self._identify_image_files(file_list) if readable
                          else {"total": 0, "active": 0, "deleted": 0, "byFormat": {}})
            self.total_images += img_counts["total"]
            self.partition_details.append({
                "partitionNumber": part["number"],
                "offset": part["offset"],
                "filesystemType": fs_info["type"],
                "filesystemRecognized": fs_info["recognized"],
                "volumeLabel": fs_info.get("label"),
                "uuid": fs_info.get("uuid"),
                "sectorSize": fs_info.get("sectorSize"),
                "clusterSize": fs_info.get("clusterSize"),
                "directoryReadable": readable,
                "imageFiles": img_counts,
            })

        method, tool, est, notes = self._determine_strategy()

        ptprint("\n" + "-" * 70, "TITLE", condition=self._out())
        ptprint("Recovery strategy", "TITLE", condition=self._out())
        ptprint("-" * 70, "TITLE", condition=self._out())
        ptprint(f"  Method: {method}  |  Tool: {tool}  |  Est. ~{est} min",
                "OK", condition=self._out())
        for note in notes:
            ptprint(f"  {note}", "INFO", condition=self._out())

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27042:2015"],
            "imageSizeBytes": self.image_size,
            "partitionTableType": self.partition_table_type,
            "partitionsFound": len(self.partitions),
            "filesystemRecognized": self.filesystem_recognized,
            "directoryReadable": self.directory_readable,
            "totalImageFiles": self.total_images,
            "recommendedMethod": method,
            "recommendedTool": tool,
            "estimatedTimeMinutes": est,
        })
        self._add_node("partitionAnalysis", True, partitions=self.partition_details)
        self._add_node("strategyDecision", True,
                       recommendedMethod=method, recommendedTool=tool,
                       estimatedTimeMinutes=est, notes=notes)
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": (f"Filesystem analysis complete - "
                           f"{self.partition_table_type}, {self.total_images} image files identified"),
                "result": "SUCCESS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": f"Strategy: {method}, tool: {tool}, est. {est} min",
            }
        ))

        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint("ANALYSIS COMPLETE", "OK", condition=self._out())
        ptprint(f"FS recognised: {self.filesystem_recognized}  |  "
                f"Dir readable: {self.directory_readable}  |  Images: {self.total_images}",
                "INFO", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())
        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        if not self.args.json_out:
            return None
        raw = self.ptjsonlib.get_result_json()
        Path(self.args.json_out).write_text(raw, encoding="utf-8")
        ptprint(f"\n✓ JSON report saved: {self.args.json_out}", "OK", condition=True)
        return self.args.json_out


def get_help() -> List[Dict]:
    return [
        {"description": [
            "Forensic filesystem analysis - ptlibs compliant",
            "Analyses partition table and filesystem structure, recommends recovery strategy",
            "Compliant with NIST SP 800-86 §2.2 and ISO/IEC 27042:2015 §5",
        ]},
        {"usage": ["ptfilesystemanalysis <case-id> <image> [options]"]},
        {"usage_example": [
            "ptfilesystemanalysis CASE-001 /var/forensics/images/CASE-001.dd",
            "ptfilesystemanalysis CASE-001 /path/to/image.dd --analyst 'Jane' --json-out step7.json",
            "ptfilesystemanalysis CASE-001 /path/to/image.dd --dry-run",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["image", "", "Path to forensic image (.dd) - REQUIRED"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without running TSK tools"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "Requires: mmls, fsstat, fls  (sudo apt install sleuthkit)",
            "Strategy: filesystem_scan | hybrid | file_carving",
            "Exit 0 = success | Exit 1 = error | Exit 130 = Ctrl+C",
            "Compliant with NIST SP 800-86 §2.2 and ISO/IEC 27042:2015 §5",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("image")
    parser.add_argument("-a", "--analyst", default="Analyst")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-j", "--json-out", default=None)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--version", action="version",
                        version=f"{SCRIPTNAME} {__version__}")

    if len(sys.argv) == 1 or {"-h", "--help"} & set(sys.argv):
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    args.json = bool(args.json_out)
    ptprinthelper.print_banner(SCRIPTNAME, __version__, False)
    return args


def main() -> int:
    try:
        args = parse_args()
        tool = PtFilesystemAnalysis(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if props.get("recommendedMethod") is not None else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())