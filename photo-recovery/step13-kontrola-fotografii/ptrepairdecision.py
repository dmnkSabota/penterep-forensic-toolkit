#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptrepairdecision - Automated repair decision tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

SCRIPTNAME         = "ptrepairdecision"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"

REPAIR_SUCCESS_RATES: Dict[str, float] = {
    "truncated":        0.85,
    "invalid_header":   0.70,
    "corrupt_segments": 0.60,
    "corrupt_data":     0.40,
    "fragmented":       0.15,
    "false_positive":   0.00,
    "unknown":          0.50,
}

LOW_VALID_THRESHOLD     = 50
HIGH_ESTIMATE_THRESHOLD = 50.0
HIGH_CONFIDENCE_LEVEL   = 70.0

# ---------------------------------------------------------------------------
# MAIN CLASS
# ---------------------------------------------------------------------------

class PtRepairDecision:
    """
    Automated repair decision – ptlibs compliant.

    Pipeline: load validation_report.json → estimate repair rate →
              apply 5-rule decision logic → calculate outcome → save JSON.

    Rules (first match wins):
      R1: corrupted == 0               → skip_repair  (high)
      R2: repairable == 0              → skip_repair  (high)
      R3: valid < LOW_VALID_THRESHOLD  → perform_repair (high)
      R4: estimate ≥ HIGH_THRESHOLD    → perform_repair (high/medium)
      R5: default                      → skip_repair  (medium)

    Pure analysis – no image files are read or modified.
    Compliant with ISO/IEC 27037:2012 §7.6 and NIST SP 800-86 §3.2.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._need_repair: List[Dict] = []
        self._strategy:    Optional[str] = None
        self._confidence:  Optional[str] = None
        self._reasoning:   List[str]     = []
        self._estimate:    float         = 0.0
        self._s: Dict[str, Any] = {
            "total": 0, "valid": 0, "corrupted": 0, "integrity": 0.0
        }

        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "strategy": None, "confidence": None,
            "reasoning": [], "expectedOutcome": {},
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

    # --- phases -------------------------------------------------------------

    def load_report(self) -> bool:
        """Load validation_report.json. In dry-run mode uses synthetic data."""
        ptprint("\n[1/3] Loading Validation Report", "TITLE", condition=not self.args.json)

        if self.dry_run:
            raw = {
                "result": {"properties": {
                    "totalFiles": 100, "validFiles": 85,
                    "corruptedFiles": 12, "unrecoverableFiles": 3,
                    "integrityScore": 85.0,
                }},
                "filesNeedingRepair": [{"corruptionType": "truncated"}] * 8 +
                                      [{"corruptionType": "corrupt_data"}] * 4,
            }
        else:
            f = self.output_dir / f"{self.case_id}_validation_report.json"
            if not f.exists():
                return self._fail("reportLoad", f"{f.name} not found – run integrity validation first.")
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
            except Exception as exc:
                return self._fail("reportLoad", f"Cannot read report: {exc}")

        # Support ptlibs format (result.properties) and flat/legacy
        if "result" in raw and "properties" in raw.get("result", {}):
            p = raw["result"]["properties"]
        elif "statistics" in raw:
            p = raw["statistics"]
        else:
            p = raw

        self._s = {
            "total":     int(p.get("totalFiles")    or p.get("total_files", 0)),
            "valid":     int(p.get("validFiles")    or p.get("valid_files", 0)),
            "corrupted": int(p.get("corruptedFiles") or p.get("corrupted_files", 0)),
            "integrity": float(p.get("integrityScore") or p.get("integrity_score", 0.0)),
        }
        self._need_repair = raw.get("filesNeedingRepair") or raw.get("files_needing_repair") or []

        s = self._s
        ptprint(f"Valid: {s['valid']} | Corrupted: {s['corrupted']} | "
                f"Score: {s['integrity']}% | For repair: {len(self._need_repair)}",
                "OK", condition=not self.args.json)
        self.ptjsonlib.add_properties({
            "totalFiles": s["total"], "validFiles": s["valid"],
            "corruptedFiles": s["corrupted"], "integrityScore": s["integrity"],
            "filesNeedingRepair": len(self._need_repair),
        })
        self._add_node("reportLoad", True, totalFiles=s["total"],
                       validFiles=s["valid"], corruptedFiles=s["corrupted"])
        return True

    def decide(self) -> None:
        """Estimate repair rate and apply 5-rule decision logic."""
        ptprint("\n[2/3] Estimating and Deciding", "TITLE", condition=not self.args.json)

        # Estimate
        if self._need_repair:
            score = sum(REPAIR_SUCCESS_RATES.get(
                fi.get("corruptionType") or fi.get("corruption_type") or "unknown",
                REPAIR_SUCCESS_RATES["unknown"]
            ) for fi in self._need_repair)
            self._estimate = round(score / len(self._need_repair) * 100, 1)
        ptprint(f"  Repair estimate: {self._estimate}% ({len(self._need_repair)} files)",
                "INFO", condition=not self.args.json)
        self.ptjsonlib.add_properties({"repairSuccessEstimate": self._estimate})

        # Rules
        s = self._s
        r = len(self._need_repair)
        e = self._estimate

        if s["corrupted"] == 0:
            self._strategy, self._confidence = "skip_repair", "high"
            self._reasoning = ["No corrupted files – all recovered photos are valid.",
                               "Repair step is unnecessary."]
        elif r == 0:
            self._strategy, self._confidence = "skip_repair", "high"
            self._reasoning = [f"All {s['corrupted']} corrupted file(s) are unrecoverable.",
                               "No candidates for repair."]
        elif s["valid"] < LOW_VALID_THRESHOLD:
            self._strategy, self._confidence = "perform_repair", "high"
            self._reasoning = [f"Only {s['valid']} valid file(s) – every photo matters.",
                               f"{r} candidate(s) for repair (est. {e}% success)."]
        elif e >= HIGH_ESTIMATE_THRESHOLD:
            conf = "high" if e >= HIGH_CONFIDENCE_LEVEL else "medium"
            self._strategy, self._confidence = "perform_repair", conf
            self._reasoning = [f"{r} file(s) repairable with {e}% estimated success.",
                               f"Expected +{int(r * e / 100)} additional files."]
        else:
            self._strategy, self._confidence = "skip_repair", "medium"
            self._reasoning = [f"Repair estimate {e}% below threshold {HIGH_ESTIMATE_THRESHOLD}%.",
                               f"Already {s['valid']} valid file(s) ({s['integrity']}%)."]

        ptprint(f"  Strategy: {self._strategy} | Confidence: {self._confidence.upper()}",
                "OK", condition=not self.args.json)
        self.ptjsonlib.add_properties({
            "strategy": self._strategy, "confidence": self._confidence,
            "reasoning": self._reasoning,
        })
        self._add_node("decision", True, strategy=self._strategy,
                       confidence=self._confidence, repairEstimate=self._estimate)

    def outcome(self) -> None:
        """Calculate and store expected final file count."""
        ptprint("\n[3/3] Calculating Expected Outcome", "TITLE", condition=not self.args.json)

        s = self._s
        r = len(self._need_repair)
        additional = int(r * self._estimate / 100) if self._strategy == "perform_repair" else 0
        final      = s["valid"] + additional
        final_pct  = round(final / max(s["total"], 1) * 100, 2)
        delta      = round(final_pct - s["integrity"], 2)

        result = {"currentValid": s["valid"], "expectedAdditional": additional,
                  "finalExpectedCount": final, "finalExpectedPercent": final_pct,
                  "improvementPp": delta}
        ptprint(f"  Current: {s['valid']} | "
                + (f"+{additional} from repair → " if additional else "")
                + f"Final: {final} ({final_pct}%)",
                "OK", condition=not self.args.json)
        self.ptjsonlib.add_properties({"expectedOutcome": result})
        self._add_node("expectedOutcome", True, **result)

    # --- run & save ---------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the decision pipeline."""
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"REPAIR DECISION v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_report():
            self.ptjsonlib.set_status("finished"); return

        self.decide()
        self.outcome()

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"DECISION: {self._strategy.upper()} | {self._confidence.upper()} confidence",
                "OK", condition=not self.args.json)
        for line in self._reasoning:
            ptprint(f"  • {line}", "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        self.ptjsonlib.set_status("finished")

    def save_report(self) -> Optional[str]:
        """Save repair_decision.json."""
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        f = self.output_dir / f"{self.case_id}_repair_decision.json"
        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        if not self.dry_run:
            f.write_text(json.dumps(props, indent=2, ensure_ascii=False), encoding="utf-8")
        ptprint(f"Decision saved: {f.name}", "OK", condition=not self.args.json)

        outcome = props.get("expectedOutcome", {})
        if self._strategy == "perform_repair":
            ptprint(f"→ PERFORM REPAIR | "
                    f"+{outcome.get('expectedAdditional',0)} files expected "
                    f"(+{outcome.get('improvementPp',0)} pp)",
                    "OK", condition=not self.args.json)
        else:
            ptprint(f"→ SKIP REPAIR | {self._s['valid']} valid files ready for cataloging.",
                    "OK", condition=not self.args.json)
        return str(f)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def get_help() -> List:
    return [
        {"description": [
            "Automated repair decision – ptlibs compliant",
            "Analyses integrity validation results and decides: perform_repair or skip_repair",
        ]},
        {"usage": ["ptrepairdecision <case-id> [options]"]},
        {"usage_example": [
            "ptrepairdecision PHOTO-2025-001",
            "ptrepairdecision CASE-042 --json",
            "ptrepairdecision TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier – REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate with synthetic validation data"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"notes": [
            f"R1: corrupted=0 → skip (high) | R2: repairable=0 → skip (high)",
            f"R3: valid<{LOW_VALID_THRESHOLD} → repair (high) | R4: estimate≥{HIGH_ESTIMATE_THRESHOLD}% → repair | R5: default → skip",
            "Rates: truncated 85% | invalid_header 70% | corrupt_segments 60% | corrupt_data 40% | fragmented 15%",
            "Pure analysis – no image files are read or modified",
            "Compliant with ISO/IEC 27037:2012 §7.6 and NIST SP 800-86 §3.2",
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
        tool = PtRepairDecision(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("strategy") else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())