#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptrecoveryconsolidation - Consolidation of filesystem and carving results
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import IMAGE_EXTENSIONS, FORMAT_GROUP_MAP, DEFAULT_OUTPUT_DIR
except ImportError:
    from _constants import IMAGE_EXTENSIONS, FORMAT_GROUP_MAP, DEFAULT_OUTPUT_DIR

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptrecoveryconsolidation"


class PtRecoveryConsolidation(ForensicToolBase):
    """Recovery consolidation - SHA-256 dedup, FS priority, NIST SP 800-86, ISO/IEC 27037:2012."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args = args
        self.case_id = self._sanitize_case_id(args.case_id)
        self.analyst = args.analyst
        self.dry_run = args.dry_run
        self.output_dir = Path(args.output_dir)
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise PermissionError(f"Permission denied: {self.output_dir} - try running with sudo")

        self.fs_recovery_dir = Path(args.fs_recovery_dir) if args.fs_recovery_dir else None
        self.carved_dir = Path(args.carved_dir) if args.carved_dir else None
        self.consolidated_dir = self.output_dir / f"{self.case_id}_consolidated"

        self.from_fs = 0
        self.from_carving = 0
        self.deduplicated = 0
        self.total = 0
        self.by_format: Dict[str, int] = {}

        self._init_properties(__version__)

    def _collect_dir(self, base: Path, label: str) -> List[Dict]:
        if not base.exists():
            return []
        files = [f for f in base.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
        ptprint(f"  {label}: {len(files)} image file(s)", "INFO", condition=self._out())
        return [{"path": f, "sha256": self._file_sha256(f), "source": label} for f in files]

    def _copy_entry(self, entry: Dict, seen_hashes: Set[str]) -> None:
        fp = entry["path"]
        sha = entry["sha256"]
        group = FORMAT_GROUP_MAP.get(fp.suffix.lower().lstrip("."), "other")

        if sha and sha in seen_hashes:
            self.deduplicated += 1
            return
        if sha:
            seen_hashes.add(sha)

        dest_sub = self.consolidated_dir / group
        if not self.dry_run:
            dest_sub.mkdir(parents=True, exist_ok=True)
        dest = dest_sub / fp.name
        if not self.dry_run and dest.exists():
            dest = dest_sub / f"{fp.stem}_{sha[:8] if sha else fp.stem[:8]}{fp.suffix}"
        if not self.dry_run:
            shutil.copy2(str(fp), str(dest))

        self.total += 1
        self.by_format[group] = self.by_format.get(group, 0) + 1
        if "fs" in entry["source"]:
            self.from_fs += 1
        else:
            self.from_carving += 1

    def consolidate(self) -> bool:
        ptprint("\n[1/1] Consolidating recovery results", "TITLE", condition=self._out())

        if not self.fs_recovery_dir and not self.carved_dir:
            return self._fail("consolidation", "At least one input directory (FS or carved) required")

        fs_files = []
        if self.fs_recovery_dir:
            if not self.fs_recovery_dir.exists() and not self.dry_run:
                return self._fail("consolidation", f"FS recovery dir not found: {self.fs_recovery_dir}")
            fs_files = (self._collect_dir(self.fs_recovery_dir / "active", "fs_active")
                        + self._collect_dir(self.fs_recovery_dir / "deleted", "fs_deleted"))

        carved_files = []
        if self.carved_dir:
            if not self.carved_dir.exists() and not self.dry_run:
                return self._fail("consolidation", f"Carved dir not found: {self.carved_dir}")
            carved_files = self._collect_dir(self.carved_dir, "carved")

        ptprint(f"\n  FS-recovered: {len(fs_files)}  |  Carved: {len(carved_files)}",
                "INFO", condition=self._out())

        all_entries = fs_files + carved_files
        if not all_entries:
            ptprint("  No files to consolidate.", "WARNING", condition=self._out())
            self._add_node("consolidation", False, error="No input files found")
            return False

        if not self.dry_run:
            self.consolidated_dir.mkdir(parents=True, exist_ok=True)

        seen_hashes: Set[str] = set()
        if not self.dry_run and self.consolidated_dir.exists():
            for existing in self.consolidated_dir.rglob("*"):
                if existing.is_file():
                    sha = self._file_sha256(existing)
                    if sha:
                        seen_hashes.add(sha)
            if seen_hashes:
                ptprint(f"  Existing: {len(seen_hashes)} files already consolidated (skipping duplicates)",
                        "INFO", condition=self._out())

        for idx, entry in enumerate(all_entries, 1):
            self._progress(idx, len(all_entries), entry["path"].name[:35])
            self._copy_entry(entry, seen_hashes)

        if self._out():
            print()

        ptprint(f"\n  Consolidated: {self.total} unique files  |  Deduplicated: {self.deduplicated}",
                "OK", condition=self._out())
        ptprint(f"  From FS: {self.from_fs}  |  From carving: {self.from_carving}",
                "INFO", condition=self._out())
        for fmt, count in sorted(self.by_format.items()):
            ptprint(f"    {fmt.upper()}: {count}", "INFO", condition=self._out())

        self._add_node("consolidation", True,
                       fromFilesystem=self.from_fs,
                       fromCarving=self.from_carving,
                       deduplicated=self.deduplicated,
                       totalConsolidated=self.total,
                       byFormat=self.by_format)
        return True

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"RECOVERY CONSOLIDATION v{__version__}  |  Case: {self.case_id}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())

        if not self.consolidate():
            self.ptjsonlib.set_status("finished")
            return

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "fromFilesystem": self.from_fs,
            "fromCarving": self.from_carving,
            "deduplicated": self.deduplicated,
            "totalConsolidated": self.total,
            "byFormat": self.by_format,
            "consolidatedDir": str(self.consolidated_dir),
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": f"Recovery consolidation complete - {self.total} unique files, {self.deduplicated} duplicates removed",
                "result": "SUCCESS" if self.total > 0 else "NO_FILES",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))

        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint("CONSOLIDATION COMPLETE", "OK", condition=self._out())
        ptprint(f"Total: {self.total}  |  FS: {self.from_fs}  |  Carved: {self.from_carving}  |  Deduped: {self.deduplicated}",
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
            "Recovery consolidation - merges filesystem and carving results",
            "Deduplication by SHA-256 with filesystem-recovery priority",
            "Compliant with NIST SP 800-86 and ISO/IEC 27037:2012",
        ]},
        {"usage": ["ptrecoveryconsolidation <case-id> <fs-recovery-dir> <carved-dir> [options]"]},
        {"usage_example": [
            "ptrecoveryconsolidation CASE-001 /path/to/recovered /path/to/carved/valid",
            "ptrecoveryconsolidation CASE-001 /path/to/recovered /path/to/carved/valid --dry-run",
            "ptrecoveryconsolidation CASE-001 '' /path/to/carved/valid --json-out step9.json",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["fs-recovery-dir", "", "Path to filesystem recovery dir (use '' to skip)"],
            ["carved-dir", "", "Path to carved files dir (use '' to skip)"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without copying files"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "At least one input directory (FS or carved) must be provided",
            "Use empty string '' to skip an optional directory",
            "Output: case_id_consolidated/<format_group>/",
            "Filesystem-recovered files take priority over carved duplicates",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("fs_recovery_dir")
    parser.add_argument("carved_dir")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-a", "--analyst", default="Analyst")
    parser.add_argument("-j", "--json-out", default=None)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--version", action="version", version=f"{SCRIPTNAME} {__version__}")

    if len(sys.argv) == 1 or {"-h", "--help"} & set(sys.argv):
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()

    if args.fs_recovery_dir == "":
        args.fs_recovery_dir = None
    if args.carved_dir == "":
        args.carved_dir = None

    args.json = bool(args.json_out)
    ptprinthelper.print_banner(SCRIPTNAME, __version__, False)
    return args


def main() -> int:
    try:
        args = parse_args()
        tool = PtRecoveryConsolidation(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if props.get("totalConsolidated", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())