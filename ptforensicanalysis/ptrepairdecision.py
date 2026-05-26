#!/usr/bin/env python3
"""
    Copyright (c) 2026 Bc. Dominik Sabota, VUT FEKT Brno
    ptrepairdecision - Repair decision engine for corrupted image files
    License: GNU GPL v3 - See <https://www.gnu.org/licenses/>
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

try:
    from ._constants import DEFAULT_OUTPUT_DIR
except ImportError:
    from _constants import DEFAULT_OUTPUT_DIR

try:
    from .ptforensictoolbase import ForensicToolBase
except ImportError:
    from ptforensictoolbase import ForensicToolBase

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME = "ptrepairdecision"

REPAIR_SUCCESS_RATES: Dict[str, float] = {
    "missing_footer": 90.0,
    "invalid_header": 85.0,
    "corrupt_segments": 60.0,
    "truncated": 85.0,
    "corrupt_data": 40.0,
    "fragmented": 15.0,
    "unknown": 29.0,
    "corrupted_metadata": 60.0,
    "invalid_structure": 20.0,
    "partial_data": 40.0,
}

DECISION_RULES = [
    (
        "R1 - High recovery probability",
        lambda rate: rate >= 85.0,
        "ATTEMPT_REPAIR",
        "High success rate (>=85%) justifies automated repair attempt.",
    ),
    (
        "R2 - Medium recovery probability",
        lambda rate: 50.0 <= rate < 85.0,
        "ATTEMPT_REPAIR",
        "Medium success rate (50-84%) - repair attempt worthwhile; "
        "manual review recommended if repair fails.",
    ),
    (
        "R3 - Low recovery probability",
        lambda rate: 30.0 <= rate < 50.0,
        "MANUAL_REVIEW",
        "Low success rate (30-49%) - automated repair unlikely to succeed; "
        "manual hex-level analysis recommended.",
    ),
    (
        "R4 - Very low recovery probability",
        lambda rate: 15.0 <= rate < 30.0,
        "SKIP",
        "Very low success rate (15-29%) - automated repair not cost-effective; "
        "note in report as unrecoverable.",
    ),
    (
        "R5 - Fragment or unrecoverable",
        lambda rate: rate < 15.0,
        "SKIP",
        "Success rate <15% - file is effectively unrecoverable via automated means.",
    ),
]


class PtRepairDecision(ForensicToolBase):
    """Rule-based repair decision engine (R1-R5) - NIST SP 800-86, ISO/IEC 27037:2012."""

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

        self.validation_file = Path(args.validation_file)

        self.total = 0
        self.attempt_repair = 0
        self.manual_review = 0
        self.skip = 0
        self._decisions: List[Dict] = []

        self._init_properties(__version__)

    def decide_single(self, corruption_type: str) -> Tuple[str, str, str, float]:
        rate = REPAIR_SUCCESS_RATES.get(corruption_type, REPAIR_SUCCESS_RATES["unknown"])
        for rule, test, decision, rationale in DECISION_RULES:
            if test(rate):
                return decision, rule, rationale, rate
        return "SKIP", "R5", "No rule matched.", rate

    def _load_validation_file(self) -> Optional[List[Dict]]:
        if self.dry_run:
            return []
        if not self.validation_file.exists():
            return None
        try:
            data = json.loads(self.validation_file.read_text(encoding="utf-8"))
            nodes = data.get("results", {}).get("nodes", [])
            iv = next((n for n in nodes if n.get("type") == "integrityValidation"), None)
            result = iv["properties"].get("fileResults", []) if iv else []
            ptprint(f"  Loaded: {len(result)} file records from {self.validation_file.name}",
                    "OK", condition=self._out())
            return result
        except Exception:
            return None

    def _run_decisions(self, repairable: List[Dict]) -> None:
        ptprint(f"  Repairable files: {len(repairable)}", "INFO", condition=self._out())
        for entry in repairable:
            ctype = entry.get("corruptionType", "unknown")
            decision, rule, rationale, rate = self.decide_single(ctype)
            self.total += 1
            if decision == "ATTEMPT_REPAIR":
                self.attempt_repair += 1
            elif decision == "MANUAL_REVIEW":
                self.manual_review += 1
            else:
                self.skip += 1
            self._decisions.append({
                "path": entry.get("path"),
                "filename": entry.get("filename"),
                "corruptionType": ctype,
                "successRatePct": rate,
                "decision": decision,
                "ruleApplied": rule,
                "rationale": rationale,
            })

    def _print_decision_summary(self) -> None:
        ptprint(f"\n  Total repairable: {self.total}  |  Attempt repair: {self.attempt_repair}  |  Manual review: {self.manual_review}  |  Skip: {self.skip}",
                "OK", condition=self._out())

        ptprint("\n  Decision breakdown by corruption type:",
                "INFO", condition=self._out())
        seen: Dict[str, Dict] = {}
        for d in self._decisions:
            ct = d["corruptionType"]
            if ct not in seen:
                seen[ct] = {
                    "count": 0, "decision": d["decision"],
                    "rate": d["successRatePct"], "rule": d["ruleApplied"],
                }
            seen[ct]["count"] += 1
        for ct, info in sorted(seen.items()):
            ptprint(f"  {info['count']}x {ct:<22s} -> {info['decision']:<15s} (rate={info['rate']:.0f}%, {info['rule']})",
                    "INFO", condition=self._out())

    def process_validation_report(self) -> bool:
        ptprint("\n[1/1] Processing integrity validation report",
                "TITLE", condition=self._out())

        file_results = self._load_validation_file()
        if file_results is None:
            return self._fail("repairDecision", f"{self.validation_file.name} not found or unreadable - run Integrity Validation first.")

        repairable = [r for r in file_results if r.get("status") == "repairable"]
        self._run_decisions(repairable)
        self._print_decision_summary()

        self._add_node("repairDecision", True,
                       totalRepairable=self.total,
                       attemptRepair=self.attempt_repair,
                       manualReview=self.manual_review,
                       skip=self.skip,
                       decisions=self._decisions)
        return True



    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint(f"REPAIR DECISION v{__version__}  |  Case: {self.case_id}",
                "TITLE", condition=self._out())
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=self._out())
        ptprint("=" * 70, "TITLE", condition=self._out())
        ptprint("\nRules R1-R5 based on REPAIR_SUCCESS_RATES (thesis Annex B).",
                "INFO", condition=self._out())

        if not self.process_validation_report():
            self.ptjsonlib.set_status("finished")
            return

        self.ptjsonlib.add_properties({
            "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
            "totalRepairable": self.total,
            "attemptRepair": self.attempt_repair,
            "manualReview": self.manual_review,
            "skip": self.skip,
            "repairRates": REPAIR_SUCCESS_RATES,
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "chainOfCustodyEntry",
            properties={
                "action": f"Repair decision complete - {self.attempt_repair} to repair, {self.manual_review} manual review, {self.skip} skip",
                "result": "SUCCESS",
                "analyst": self.analyst,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ))

        ptprint("\n" + "=" * 70, "TITLE", condition=self._out())
        ptprint("REPAIR DECISION COMPLETE", "OK", condition=self._out())
        ptprint(f"ATTEMPT_REPAIR: {self.attempt_repair}  |  MANUAL_REVIEW: {self.manual_review}  |  SKIP: {self.skip}",
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
            "Repair decision engine - ptlibs compliant",
            "Applies rule-based decisions (R1-R5) to repairable image files",
            "Decision outcomes: ATTEMPT_REPAIR | MANUAL_REVIEW | SKIP",
            "Rates cited: Kessler 2007; Garfinkel et al. 2009; NIST SP 800-86",
        ]},
        {"usage": ["ptrepairdecision <case-id> <validation-file> [options]"]},
        {"usage_example": [
            "ptrepairdecision CASE-001 /var/forensics/images/CASE-001_integrity_validation.json",
            "ptrepairdecision CASE-001 /path/to/validation.json --dry-run",
            "ptrepairdecision CASE-001 /path/to/validation.json --json-out step11.json",
        ]},
        {"options": [
            ["case-id", "", "Forensic case identifier - REQUIRED"],
            ["validation-file", "", "Path to integrity_validation.json - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Report output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-a", "--analyst", "<n>", "Analyst name (default: Analyst)"],
            ["-j", "--json-out", "<f>", "Save JSON report to file"],
            ["-q", "--quiet", "", "Suppress terminal output"],
            ["--dry-run", "", "Simulate without reading files"],
            ["-h", "--help", "", "Show help"],
            ["--version", "", "Show version"],
        ]},
        {"notes": [
            "R1 (>=85%): ATTEMPT_REPAIR | R2 (50-84%): ATTEMPT_REPAIR",
            "R3 (30-49%): MANUAL_REVIEW | R4-R5 (<30%): SKIP",
            "Output: case_id_repair_decisions.json",
            "Pure analytical step - no files are moved or modified",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("validation_file")
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
        tool = PtRepairDecision(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["results"]["properties"]
        return 0 if "totalRepairable" in props else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())