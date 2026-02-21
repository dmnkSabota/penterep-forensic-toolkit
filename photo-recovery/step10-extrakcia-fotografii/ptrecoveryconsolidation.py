#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptrecoveryconsolidation - Forensic recovery consolidation tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SCRIPTNAME         = "ptrecoveryconsolidation"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"
HASH_CHUNK         = 65536   # 64 KB SHA-256 read chunks

IMAGE_EXTENSIONS: set = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".tiff", ".tif", ".heic", ".heif", ".webp",
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".dng", ".orf", ".raf", ".rw2", ".pef", ".raw",
}

FORMAT_MAP: Dict[str, str] = {
    "jpg": "jpg", "jpeg": "jpg", "png": "png",
    "tif": "tiff", "tiff": "tiff",
    "gif": "other", "bmp": "other", "heic": "other", "heif": "other", "webp": "other",
    "cr2": "raw", "cr3": "raw", "nef": "raw", "nrw": "raw",
    "arw": "raw", "srf": "raw", "sr2": "raw", "dng": "raw",
    "orf": "raw", "raf": "raw", "rw2": "raw", "pef": "raw", "raw": "raw",
}

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtRecoveryConsolidation:
    """
    Forensic recovery consolidation – ptlibs compliant.

    Pipeline: detect sources (Step 9 / Step 10) → inventory → SHA-256 dedup
              → copy + organise → master_catalog.json + report.

    Priority rule: FS-based files win over carved duplicates (preserve names).
    READ-ONLY on source directories (copies, never moves originals).
    Compliant with ISO/IEC 27037:2012 and NIST SP 800-86.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Source directories
        self.fs_recovery_dir = self.output_dir / f"{self.case_id}_recovered"
        self.carving_dir     = self.output_dir / f"{self.case_id}_carved"

        # Output directories
        self.consolidated_dir = self.output_dir / f"{self.case_id}_consolidated"
        self.fs_based_out     = self.consolidated_dir / "fs_based"
        self.carved_out       = self.consolidated_dir / "carved"
        self.duplicates_out   = self.consolidated_dir / "duplicates"

        # All counters in one dict
        self._s: Dict[str, Any] = {
            "discovered": 0, "fs": 0, "carved": 0,
            "dupes": 0, "unique": 0, "size": 0,
            "by_format": {}, "by_source": {},
        }
        self._hash_db:  Dict[str, Dict] = {}
        self._organised: List[Dict]     = []

        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "sourcesFound": [],
            "totalDiscovered": 0, "fsBasedFiles": 0, "carvedFiles": 0,
            "duplicatesDetected": 0, "finalUniqueFiles": 0,
            "totalSizeBytes": 0, "totalSizeMb": 0.0,
            "byFormat": {}, "bySource": {},
            "consolidatedDir": str(self.consolidated_dir),
            "dryRun": self.dry_run,
        })
        ptprint(f"Initialized: case={self.case_id}", "INFO", condition=not self.args.json)

    # --- helpers ------------------------------------------------------------

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type, properties={"success": success, **kwargs}
        ))

    def _fail(self, node_type: str, msg: str) -> bool:
        ptprint(msg, "ERROR", condition=not self.args.json)
        self._add_node(node_type, False, error=msg)
        return False

    def _sha256(self, filepath: Path) -> Optional[str]:
        h = hashlib.sha256()
        try:
            with open(filepath, "rb") as fh:
                for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    def _scan_dir(self, directory: Path, source_label: str) -> List[Dict]:
        """Recursively collect image files from a directory."""
        files = []
        for item in directory.rglob("*"):
            if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
                files.append({"path": item, "source": source_label, "size": size,
                              "ext": item.suffix.lstrip(".").lower()})
        return files

    # --- phases -------------------------------------------------------------

    def detect_sources(self) -> List[str]:
        """Discover which recovery outputs exist (Step 9 / Step 10)."""
        ptprint("\n[1/3] Detecting Recovery Sources", "TITLE", condition=not self.args.json)

        sources: List[str] = []

        if self.fs_recovery_dir.exists() and (
                (self.fs_recovery_dir / "active").exists() or
                (self.fs_recovery_dir / "deleted").exists()):
            sources.append("fs_based")
            ptprint(f"  ✓ Step 9 (FS-based): {self.fs_recovery_dir.name}",
                    "OK", condition=not self.args.json)

        if self.carving_dir.exists() and (self.carving_dir / "organized").exists():
            sources.append("carved")
            ptprint(f"  ✓ Step 10 (File carving): {self.carving_dir.name}",
                    "OK", condition=not self.args.json)

        if not sources:
            return [] if self._fail(
                "sourceDetection",
                "No recovery sources found – run Step 9 and/or Step 10 first."
            ) else []

        self._add_node("sourceDetection", True, sources=sources)
        return sources

    def inventory_sources(self, sources: List[str]) -> List[Dict]:
        """Scan all available source directories and collect every image file."""
        ptprint("\n[2/3] Inventorying Sources", "TITLE", condition=not self.args.json)

        all_files: List[Dict] = []

        if "fs_based" in sources:
            for sub in ("active", "deleted"):
                d = self.fs_recovery_dir / sub
                if d.exists():
                    batch = self._scan_dir(d, "fs_based")
                    all_files.extend(batch)
                    ptprint(f"  fs_based/{sub}/: {len(batch)} image files",
                            "INFO", condition=not self.args.json)

        if "carved" in sources:
            d = self.carving_dir / "organized"
            if d.exists():
                batch = self._scan_dir(d, "carved")
                all_files.extend(batch)
                ptprint(f"  carved/organized/: {len(batch)} image files",
                        "INFO", condition=not self.args.json)

        self._s["fs"]         = sum(1 for f in all_files if f["source"] == "fs_based")
        self._s["carved"]     = sum(1 for f in all_files if f["source"] == "carved")
        self._s["discovered"] = len(all_files)

        ptprint(f"  Total: {self._s['discovered']} "
                f"(fs_based={self._s['fs']}, carved={self._s['carved']})",
                "OK", condition=not self.args.json)
        self._add_node("inventory", True, totalDiscovered=self._s["discovered"],
                       fsBasedFiles=self._s["fs"], carvedFiles=self._s["carved"])
        return all_files

    def hash_and_deduplicate(self, all_files: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        SHA-256 each file and remove cross-source duplicates.
        FS-based copy wins over carved when hashes collide.
        """
        ptprint("\n[3/3] Hashing and Deduplicating", "TITLE", condition=not self.args.json)

        total = len(all_files)
        unique: List[Dict] = []
        dupes:  List[Dict] = []

        for idx, fi in enumerate(all_files, 1):
            if idx % 100 == 0 or idx == total:
                ptprint(f"  {idx}/{total} ({idx*100//total}%)",
                        "INFO", condition=not self.args.json)

            digest = (f"dry-run-{idx:08d}" if self.dry_run
                      else self._sha256(fi["path"]))
            if digest is None:
                ptprint(f"  Cannot hash {fi['path'].name}",
                        "WARNING", condition=not self.args.json)
                continue
            fi["hash"] = digest

            if digest in self._hash_db:
                existing = self._hash_db[digest]
                # FS-based wins: swap out carved copy already in unique
                if fi["source"] == "fs_based" and existing["source"] == "carved":
                    dupes.append(existing)
                    unique = [u for u in unique if u.get("hash") != digest]
                    self._hash_db[digest] = fi
                    unique.append(fi)
                else:
                    dupes.append(fi)
                self._s["dupes"] += 1
            else:
                self._hash_db[digest] = fi
                unique.append(fi)

        dup_pct = self._s["dupes"] / total * 100 if total else 0
        ptprint(f"  Unique: {len(unique)} | Duplicates: {self._s['dupes']} ({dup_pct:.1f}%)",
                "OK", condition=not self.args.json)
        self._add_node("deduplication", True, totalInput=total, uniqueFiles=len(unique),
                       duplicates=self._s["dupes"], duplicationRate=round(dup_pct, 1))
        return unique, dupes

    def copy_and_organise(self, unique: List[Dict], dupes: List[Dict]) -> List[Dict]:
        """Copy unique files into consolidated tree; copy duplicates to duplicates/."""
        ptprint("\nCopying and organising …", "TITLE", condition=not self.args.json)

        # Create directory tree inline
        if not self.dry_run:
            for base in (self.fs_based_out, self.carved_out):
                for sub in ("jpg", "png", "tiff", "raw", "other"):
                    (base / sub).mkdir(parents=True, exist_ok=True)
            self.duplicates_out.mkdir(parents=True, exist_ok=True)

        fmt_counters: Dict[str, Dict[str, int]] = {
            "fs_based": defaultdict(int), "carved": defaultdict(int)
        }

        for fi in unique:
            source    = fi["source"]
            ext       = fi["ext"]
            fmt_group = FORMAT_MAP.get(ext, "other")
            base_out  = self.fs_based_out if source == "fs_based" else self.carved_out
            dest_dir  = base_out / fmt_group

            if source == "fs_based":
                new_name = fi["path"].name
                dest = dest_dir / new_name
                if not self.dry_run and dest.exists():
                    fmt_counters[source][fmt_group] += 1
                    new_name = f"{dest.stem}_{fmt_counters[source][fmt_group]}{dest.suffix}"
                    dest = dest_dir / new_name
            else:
                fmt_counters[source][fmt_group] += 1
                seq = fmt_counters[source][fmt_group]
                new_name = f"{self.case_id}_{fmt_group}_{seq:06d}.{ext}"
                dest = dest_dir / new_name

            if not self.dry_run:
                shutil.copy2(str(fi["path"]), str(dest))

            self._s["by_format"][fmt_group] = self._s["by_format"].get(fmt_group, 0) + 1
            self._s["by_source"][source]    = self._s["by_source"].get(source, 0) + 1
            self._s["size"] += fi["size"]

            fi["consolidatedName"] = new_name
            fi["consolidatedPath"] = (str(dest.relative_to(self.consolidated_dir))
                                      if not self.dry_run else new_name)
            self._organised.append(fi)

        # Copy duplicates to audit folder
        for dup in dupes:
            dest = self.duplicates_out / dup["path"].name
            if not self.dry_run:
                if dest.exists():
                    dest = self.duplicates_out / \
                           f"{dest.stem}_{dup.get('hash','')[:8]}{dest.suffix}"
                shutil.copy2(str(dup["path"]), str(dest))

        self._s["unique"] = len(self._organised)
        ptprint(f"{self._s['unique']} files organised.", "OK", condition=not self.args.json)
        return self._organised

    def create_master_catalog(self) -> None:
        """Build and save master_catalog.json inside the consolidated directory."""
        ptprint("\nCreating master catalog …", "TITLE", condition=not self.args.json)

        size_mb = round(self._s["size"] / (1024 * 1024), 2)
        catalog = {
            "caseId": self.case_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "totalFiles": self._s["unique"],
                "totalSizeBytes": self._s["size"], "totalSizeMb": size_mb,
                "sourcesUsed": list({f["source"] for f in self._organised}),
                "fsBasedFiles": self._s["fs"], "carvedFiles": self._s["carved"],
                "duplicatesRemoved": self._s["dupes"],
                "finalUniqueFiles": self._s["unique"],
            },
            "byFormat": self._s["by_format"],
            "bySource": self._s["by_source"],
            "files": [
                {
                    "id": idx,
                    "filename": fi["consolidatedName"],
                    "originalFilename": fi["path"].name,
                    "path": fi["consolidatedPath"],
                    "sizeBytes": fi["size"],
                    "sizeMb": round(fi["size"] / (1024 * 1024), 4),
                    "hashSha256": fi.get("hash", ""),
                    "format": fi["ext"],
                    "formatGroup": FORMAT_MAP.get(fi["ext"], "other"),
                    "recoveryMethod": fi["source"],
                }
                for idx, fi in enumerate(self._organised, 1)
            ],
        }

        if not self.dry_run:
            self.consolidated_dir.mkdir(parents=True, exist_ok=True)
            (self.consolidated_dir / "master_catalog.json").write_text(
                json.dumps(catalog, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8"
            )
        ptprint(f"master_catalog.json saved ({len(catalog['files'])} entries).",
                "OK", condition=not self.args.json)
        self._add_node("masterCatalog", True, totalEntries=len(catalog["files"]),
                       totalSizeMb=size_mb, byFormat=self._s["by_format"],
                       bySource=self._s["by_source"])

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the full consolidation pipeline."""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"RECOVERY CONSOLIDATION v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        sources = self.detect_sources()
        if not sources:
            self.ptjsonlib.set_status("finished"); return

        all_files = self.inventory_sources(sources)
        if not all_files:
            ptprint("No image files found in recovery sources.",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.set_status("finished"); return

        unique, dupes = self.hash_and_deduplicate(all_files)
        self.copy_and_organise(unique, dupes)
        self.create_master_catalog()

        s = self._s
        size_mb = round(s["size"] / (1024 * 1024), 2)
        self.ptjsonlib.add_properties({
            "sourcesFound": sources,
            "totalDiscovered": s["discovered"],
            "fsBasedFiles": s["fs"], "carvedFiles": s["carved"],
            "duplicatesDetected": s["dupes"], "finalUniqueFiles": s["unique"],
            "totalSizeBytes": s["size"], "totalSizeMb": size_mb,
            "byFormat": s["by_format"], "bySource": s["by_source"],
        })

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("CONSOLIDATION COMPLETED", "OK", condition=not self.args.json)
        ptprint(f"Discovered: {s['discovered']} (fs={s['fs']}, carved={s['carved']}) | "
                f"Dupes: {s['dupes']} | Unique: {s['unique']} | {size_mb:.1f} MB",
                "INFO", condition=not self.args.json)
        ptprint("Next: Step 12 – EXIF Analysis", "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        self.ptjsonlib.set_status("finished")

    def _write_text_report(self, props: Dict) -> Path:
        """Write CONSOLIDATION_REPORT.txt to consolidated_dir."""
        txt = self.consolidated_dir / "CONSOLIDATION_REPORT.txt"
        self.consolidated_dir.mkdir(parents=True, exist_ok=True)
        sep = "=" * 70
        lines = [sep, "RECOVERY CONSOLIDATION REPORT", sep, "",
                 f"Case ID:   {self.case_id}",
                 f"Timestamp: {props.get('timestamp','')}", "",
                 "SOURCES:", *[f"  - {s}" for s in props.get("sourcesFound", [])],
                 "", "STATISTICS:",
                 f"  Total discovered:    {props.get('totalDiscovered',0)}",
                 f"  FS-based files:      {props.get('fsBasedFiles',0)}",
                 f"  Carved files:        {props.get('carvedFiles',0)}",
                 f"  Duplicates removed:  {props.get('duplicatesDetected',0)}",
                 f"  Final unique files:  {props.get('finalUniqueFiles',0)}",
                 f"  Total size:          {props.get('totalSizeMb',0):.1f} MB",
                 "", "BY FORMAT:"]
        lines += [f"  {k.upper():8s}: {v}" for k, v in sorted(props.get("byFormat", {}).items())]
        lines += ["", "BY SOURCE:"]
        lines += [f"  {k}: {v}" for k, v in sorted(props.get("bySource", {}).items())]
        txt.write_text("\n".join(lines), encoding="utf-8")
        return txt

    def save_report(self) -> Optional[str]:
        """Save JSON report and CONSOLIDATION_REPORT.txt."""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        json_file = self.output_dir / f"{self.case_id}_consolidation_report.json"
        report = {
            "result": json.loads(self.ptjsonlib.get_result_json()),
            "consolidatedFiles": [
                {"filename": fi.get("consolidatedName"),
                 "originalFilename": fi["path"].name,
                 "consolidatedPath": fi.get("consolidatedPath"),
                 "source": fi["source"], "sizeBytes": fi["size"],
                 "hashSha256": fi.get("hash", ""), "format": fi["ext"]}
                for fi in self._organised
            ],
        }
        json_file.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                             encoding="utf-8")
        ptprint(f"JSON report: {json_file}", "OK", condition=not self.args.json)

        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        txt = self._write_text_report(props)
        ptprint(f"Text report: {txt}", "OK", condition=not self.args.json)
        return str(json_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_help() -> List[Dict]:
    return [
        {"description": [
            "Forensic recovery consolidation – ptlibs compliant",
            "Merges Step 9 (FS-based) and/or Step 10 (carving) into one deduplicated dataset",
        ]},
        {"usage": ["ptrecoveryconsolidation <case-id> [options]"]},
        {"usage_example": [
            "ptrecoveryconsolidation PHOTO-2025-001",
            "ptrecoveryconsolidation CASE-042 --json",
            "ptrecoveryconsolidation TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate without copying files"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"notes": [
            "Pipeline: detect sources → inventory → SHA-256 dedup → copy → catalog",
            "Output:   fs_based/ | carved/ | duplicates/ | master_catalog.json",
            "FS-based files keep original names; carved → {case_id}_{type}_{seq:06d}.ext",
            "FS-based priority: wins over carved on hash collision",
            "READ-ONLY on source directories (copies, never moves originals)",
            "Compliant with ISO/IEC 27037:2012 and NIST SP 800-86",
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
        tool = PtRecoveryConsolidation(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("finalUniqueFiles", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())