#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptexifanalysis - Forensic EXIF metadata analysis tool
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import DEFAULT_OUTPUT_DIR, IMAGE_EXTENSIONS
except ImportError:
    from _constants import DEFAULT_OUTPUT_DIR, IMAGE_EXTENSIONS

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptexifanalysis"

EXIFTOOL_BATCH = 50

FIELDS_TO_EXTRACT = [
    "FileName", "FileSize", "FileModifyDate", "FileCreateDate",
    "DateTimeOriginal", "CreateDate", "ModifyDate", "OffsetTime",
    "Make", "Model", "LensModel", "Software", "Artist", "Copyright",
    "ExposureTime", "FNumber", "ISO", "FocalLength", "Flash",
    "ImageWidth", "ImageHeight", "GPSLatitude", "GPSLongitude",
    "GPSAltitude", "GPSDateTime",
]

EDITING_SOFTWARE = frozenset({
    "photoshop", "lightroom", "gimp", "affinity photo",
    "instagram", "snapseed", "vsco", "facetune",
})

UNUSUAL_ISO_THRESHOLD = 25600


class PtExifAnalysis(ForensicToolBase):
    """Forensic EXIF metadata analysis - exiftool batch extraction, anomaly detection, NIST SP 800-86, ISO/IEC 27037:2012."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.image_dir = Path(args.image_dir)
        self.output_dir = Path(args.output_dir)
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise PermissionError(f"Permission denied: {self.output_dir} - try running with sudo")

        self.total = 0
        self.with_exif = 0
        self.no_exif = 0
        self.gps_count = 0
        self.anomalies = 0
        self.by_make: Dict[str, int] = {}
        self.by_anomaly: Dict[str, int] = {}
        self._records: List[Dict] = []

        self._init_properties(__version__)
        self.ptjsonlib.add_properties({"imageDir": str(self.image_dir)})

    def _run_exiftool_batch(self, files: List[Path]) -> List[Dict]:
        fields = [f"-{f}" for f in FIELDS_TO_EXTRACT]
        r = self._run_command(
            ["exiftool", "-json", "-charset", "utf8"] + fields +
            [str(f) for f in files],
            timeout=120)
        if r["success"] and r["stdout"]:
            try:
                data = json.loads(r["stdout"])
                return data if isinstance(data, list) else [data]
            except Exception:
                pass
        return [{"SourceFile": str(f)} for f in files]

    def _parse_datetime(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        m = re.match(r"(\d{4}):(\d{2}):(\d{2})\s+(\d{2}):(\d{2}):(\d{2})", str(raw))
        if not m:
            return None
        try:
            return datetime(*[int(x) for x in m.groups()], tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None

    def _detect_editing_software(self, exif: Dict) -> Optional[str]:
        for field in ("Software", "Artist", "Copyright"):
            val = str(exif.get(field, "")).lower()
            for sw in EDITING_SOFTWARE:
                if sw in val:
                    return sw
        return None

    def _detect_anomalies(self, exif: Dict) -> List[Dict]:
        anomalies: List[Dict] = []
        now = datetime.now(timezone.utc)

        dt_orig = self._parse_datetime(exif.get("DateTimeOriginal"))
        if dt_orig and dt_orig > now:
            anomalies.append({
                "type": "future_date",
                "description": "DateTimeOriginal is in the future",
                "value": str(dt_orig),
            })

        try:
            iso_val = int(str(exif.get("ISO", 0)).split()[0])
            threshold = UNUSUAL_ISO_THRESHOLD
            if iso_val > threshold:
                anomalies.append({
                    "type": "unusual_iso",
                    "description": f"ISO {iso_val} exceeds threshold ({threshold})",
                    "value": iso_val,
                })
        except (ValueError, TypeError):
            pass

        dt_modify = self._parse_datetime(exif.get("ModifyDate"))
        if dt_orig and dt_modify and dt_modify > dt_orig:
            delta = (dt_modify - dt_orig).days
            anomalies.append({
                "type": "modify_after_original",
                "description": f"ModifyDate is {delta} day(s) after DateTimeOriginal",
                "value": f"original={dt_orig}, modified={dt_modify}",
            })

        return anomalies

    def _parse_single(self, exif: Dict) -> Dict:
        src = exif.get("SourceFile", "")
        has_exif = bool(exif.get("DateTimeOriginal") or
                        exif.get("Make") or exif.get("Model"))
        gps = None
        if exif.get("GPSLatitude") and exif.get("GPSLongitude"):
            gps = {
                "latitude": exif.get("GPSLatitude"),
                "longitude": exif.get("GPSLongitude"),
                "altitude": exif.get("GPSAltitude"),
                "datetime": exif.get("GPSDateTime"),
            }
        return {
            "filename": Path(src).name if src else "unknown",
            "filePath": src,
            "hasExif": has_exif,
            "make": exif.get("Make"),
            "model": exif.get("Model"),
            "software": exif.get("Software"),
            "editingSoftware": self._detect_editing_software(exif),
            "dateTimeOriginal": exif.get("DateTimeOriginal"),
            "createDate": exif.get("CreateDate"),
            "modifyDate": exif.get("ModifyDate"),
            "iso": exif.get("ISO"),
            "fNumber": exif.get("FNumber"),
            "exposureTime": exif.get("ExposureTime"),
            "focalLength": exif.get("FocalLength"),
            "flash": exif.get("Flash"),
            "width": exif.get("ImageWidth"),
            "height": exif.get("ImageHeight"),
            "gps": gps,
            "anomalies": self._detect_anomalies(exif),
        }

    def check_tools(self) -> bool:
        ptprint("\n[1/2] Checking tools", "TITLE", condition=self._out())

        if not self._check_command("exiftool"):
            return self._fail("toolsCheck", "exiftool not found - sudo apt install libimage-exiftool-perl")

        r = self._run_command(["exiftool", "-ver"], timeout=5)
        ver = r["stdout"].strip() if r["success"] else "unknown"
        ptprint(f"  exiftool {ver}", "OK", condition=self._out())
        self._add_node("toolsCheck", True, exiftoolVersion=ver)
        return True

    def analyse_directory(self) -> bool:
        ptprint("\n[2/2] Extracting EXIF metadata", "TITLE", condition=self._out())

        if not self.image_dir.exists() and not self.dry_run:
            return self._fail("exifAnalysis", f"Directory not found: {self.image_dir}")

        candidates = [] if self.dry_run else [
            f for f in self.image_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        ]
        ptprint(f"  Files: {len(candidates)}", "INFO", condition=self._out())

        if not candidates and not self.dry_run:
            ptprint("  No image files found.", "WARNING", condition=self._out())
            self._add_node("exifAnalysis", True, totalFiles=0)
            return True

        processed = 0
        for start in range(0, len(candidates), EXIFTOOL_BATCH):
            batch = candidates[start:start + EXIFTOOL_BATCH]
            for exif_raw in self._run_exiftool_batch(batch):
                record = self._parse_single(exif_raw)
                self._records.append(record)
                processed += 1
                self._progress(processed, len(candidates), record["filename"][:35])

                self.total += 1
                if record["hasExif"]:
                    self.with_exif += 1
                else:
                    self.no_exif += 1
                if record["gps"]:
                    self.gps_count += 1
                if record["anomalies"]:
                    self.anomalies += 1
                    for a in record["anomalies"]:
                        t = a["type"]
                        self.by_anomaly[t] = self.by_anomaly.get(t, 0) + 1
                if record["make"]:
                    self.by_make[record["make"]] = self.by_make.get(record["make"], 0) + 1

        if self._out():
            print()

        ptprint(f"  Total: {self.total}  |  EXIF: {self.with_exif}  |  GPS: {self.gps_count}  |  Anomalies: {self.anomalies}",
                "OK", condition=self._out())

        if self.by_anomaly:
            ptprint("  Anomalies:", "WARNING", condition=self._out())
            for atype, count in sorted(self.by_anomaly.items()):
                ptprint(f"    {count}x {atype}", "WARNING", condition=self._out())

        if self.by_make:
            ptprint("  Camera makes (top 5):", "INFO", condition=self._out())
            for make, count in sorted(self.by_make.items(), key=lambda x: -x[1])[:5]:
                ptprint(f"    {count}x {make}", "INFO", condition=self._out())

        self._add_node("exifAnalysis", True,
                       totalFiles=self.total,
                       withExif=self.with_exif,
                       noExif=self.no_exif,
                       gpsCount=self.gps_count,
                       anomaliesDetected=self.anomalies,
                       byAnomaly=self.by_anomaly,
                       topMakes=dict(sorted(self.by_make.items(), key=lambda x: -x[1])[:5]),
                       exifRecords=self._records)
        return True

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"EXIF ANALYSIS v{__version__}  |  Case: {self.case_id}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.check_tools():
            self.ptjsonlib.set_status("finished")
            return

        self.analyse_directory()

        exif_rate = round(self.with_exif / self.total * 100, 1) if self.total else None

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "totalFiles": self.total,
            "withExif": self.with_exif,
            "noExif": self.no_exif,
            "gpsCount": self.gps_count,
            "anomaliesDetected": self.anomalies,
            "exifRate": exif_rate,
            "byAnomaly": self.by_anomaly,
            "editingSoftwareChecked": sorted(EDITING_SOFTWARE),
            "unusualIsoThreshold": UNUSUAL_ISO_THRESHOLD,
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": f"EXIF analysis complete - {self.with_exif} files with EXIF, {self.anomalies} anomalies",
                "result": "SUCCESS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))

        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint("EXIF ANALYSIS COMPLETE", "OK", condition=self._out())
        ptprint(f"Total: {self.total}  |  With EXIF: {self.with_exif}  |  GPS: {self.gps_count}  |  Anomalies: {self.anomalies}",
                "INFO", condition=self._out())
        if exif_rate is not None:
            ptprint(f"EXIF coverage: {exif_rate}%", "OK", condition=self._out())
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
            f"Forensic EXIF metadata analysis - batch {EXIFTOOL_BATCH} files/call, anomaly detection - ptlibs compliant",
            "Anomalies: future_date | unusual_iso | modify_after_original",
            "References: Farid 2016; NIST SP 800-86; CIPA DC-008:2019",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
        {"usage": ["ptexifanalysis <case-id> <image-dir> [options]"]},
        {"usage_example": [
            "ptexifanalysis CASE-001 /var/forensics/images/CASE-001_consolidated",
            "ptexifanalysis CASE-001 /var/forensics/images/CASE-001_repaired",
            "ptexifanalysis CASE-001 /path/to/images --dry-run",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["image-dir", "", "Directory with image files - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Report output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without reading files"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "Requires: exiftool (sudo apt install libimage-exiftool-perl)",
            f"Batch size: {EXIFTOOL_BATCH} files per exiftool call  |  Exit 0 = files processed",
            "Output: case_id_exif_analysis.json with full per-file EXIF catalog",
            "Exit 0 = files processed | Exit 1 = no files | Exit 99 = error",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("image_dir")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-a", "--analyst", default="Analyst")
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
        tool = PtExifAnalysis(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if props.get("totalFiles", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())