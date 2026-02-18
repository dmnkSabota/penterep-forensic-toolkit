#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptrepairdecision - Automated repair decision tool

    ptrepairdecision is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptrepairdecision is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptrepairdecision.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/images"

# Empirical repair success rates per corruption type (0.0 – 1.0)
REPAIR_SUCCESS_RATES: Dict[str, float] = {
    "truncated":        0.85,   # missing footer – straightforward fix
    "invalid_header":   0.70,   # header reconstruction
    "corrupt_segments": 0.60,   # skip / remove bad segments
    "corrupt_data":     0.40,   # partial pixel recovery
    "fragmented":       0.15,   # defragmentation, rarely succeeds
    "false_positive":   0.00,   # not an image – impossible
    "unknown":          0.50,   # conservative guess
}

# Rule thresholds
LOW_VALID_THRESHOLD      = 50    # Rule 3: every photo counts if valid < this
HIGH_ESTIMATE_THRESHOLD  = 50.0  # Rule 4/5 boundary (percent)
HIGH_CONFIDENCE_ESTIMATE = 70.0  # Rule 4: high confidence sub-threshold


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtRepairDecision:
    """
    Automated repair decision tool – ptlibs compliant.

    Five-phase decision process:
    1. Load validation report from Step 15
    2. Estimate per-file repair success rate from corruption types
    3. Apply five-rule decision logic (see RULES below)
    4. Calculate expected outcome (final file count, improvement %)
    5. Save repair_decision.json and print decision summary

    RULES (evaluated in priority order):
      R1: corrupted == 0               → skip_repair  (HIGH confidence)
      R2: repairable == 0              → skip_repair  (HIGH confidence)
      R3: valid < LOW_VALID_THRESHOLD  → perform_repair (HIGH confidence)
      R4: estimate ≥ HIGH_THRESHOLD    → perform_repair (HIGH/MEDIUM)
      R5: estimate < HIGH_THRESHOLD    → skip_repair  (MEDIUM confidence)

    Complies with ISO/IEC 27037:2012 Section 7.6 and NIST SP 800-86 Section 3.2.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State
        self._validation: Optional[Dict]   = None
        self._need_repair: List[Dict]      = []
        self._strategy: Optional[str]      = None
        self._next_step: Optional[int]     = None
        self._confidence: Optional[str]    = None
        self._reasoning:  List[str]        = []
        self._repair_estimate: float       = 0.0

        # Top-level JSON properties
        self.ptjsonlib.add_properties({
            "caseId":          self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "scriptVersion":   __version__,
            # Inputs (filled in Phase 1)
            "totalFiles":      0,
            "validFiles":      0,
            "corruptedFiles":  0,
            "unrecoverableFiles": 0,
            "integrityScore":  0.0,
            "filesNeedingRepair": 0,
            "repairSuccessEstimate": 0.0,
            # Decision (filled in Phase 3)
            "strategy":        None,
            "nextStep":        None,
            "confidence":      None,
            "reasoning":       [],
            # Outcome (filled in Phase 4)
            "expectedOutcome": {},
            "dryRun":          self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # PHASE 1 – LOAD VALIDATION REPORT
    # -------------------------------------------------------------------------

    def load_validation_report(self) -> bool:
        """
        Load the JSON report produced by Step 15 (ptintegrityvalidation).

        Accepts both the ptlibs format (result.properties) and the
        legacy flat format (statistics / files_needing_repair).

        Returns:
            bool: True if loaded successfully
        """
        ptprint("\n[STEP 1/5] Loading Validation Report from Step 15",
                "TITLE", condition=not self.args.json)

        report_file = self.output_dir / f"{self.case_id}_validation_report.json"

        if not report_file.exists() and not self.dry_run:
            ptprint(f"✗ Not found: {report_file}",
                    "ERROR", condition=not self.args.json)
            ptprint("  Please run Step 15 (Integrity Validation) first!",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "reportLoad",
                properties={"success": False,
                            "error": "validation_report.json not found"}
            ))
            return False

        if self.dry_run:
            # Synthetic data for simulation
            self._validation = {
                "result": {"properties": {
                    "totalFiles": 100, "validFiles": 85,
                    "corruptedFiles": 12, "unrecoverableFiles": 3,
                    "integrityScore": 85.0,
                }},
                "filesNeedingRepair": [
                    {"corruptionType": "truncated"} for _ in range(8)
                ] + [{"corruptionType": "corrupt_data"} for _ in range(4)],
            }
        else:
            try:
                with open(report_file, "r", encoding="utf-8") as fh:
                    self._validation = json.load(fh)
            except Exception as exc:
                ptprint(f"✗ Cannot read report: {exc}",
                        "ERROR", condition=not self.args.json)
                self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                    "reportLoad",
                    properties={"success": False, "error": str(exc)}
                ))
                return False

        # Extract stats – support ptlibs and legacy formats
        raw  = self._validation
        if "result" in raw and "properties" in raw.get("result", {}):
            props = raw["result"]["properties"]
        elif "statistics" in raw:
            props = raw["statistics"]
        else:
            props = raw  # flat format

        total        = int(props.get("totalFiles")        or props.get("total_files", 0))
        valid        = int(props.get("validFiles")        or props.get("valid_files", 0))
        corrupted    = int(props.get("corruptedFiles")    or props.get("corrupted_files", 0))
        unrecov      = int(props.get("unrecoverableFiles") or props.get("unrecoverable_files", 0))
        integrity    = float(props.get("integrityScore")  or props.get("integrity_score", 0.0))

        # Repair list – also support camelCase key
        self._need_repair = (
            raw.get("filesNeedingRepair") or
            raw.get("files_needing_repair") or []
        )

        ptprint(f"✓ Report loaded: {report_file.name}",
                "OK", condition=not self.args.json)
        ptprint(f"  Total:          {total}",    "INFO", condition=not self.args.json)
        ptprint(f"  Valid:          {valid}",    "OK",   condition=not self.args.json)
        ptprint(f"  Corrupted:      {corrupted}","WARNING", condition=not self.args.json)
        ptprint(f"  Unrecoverable:  {unrecov}",  "ERROR", condition=not self.args.json)
        ptprint(f"  Integrity:      {integrity}%","INFO", condition=not self.args.json)
        ptprint(f"  For repair:     {len(self._need_repair)}",
                "INFO", condition=not self.args.json)

        # Store for later phases
        self._total     = total
        self._valid     = valid
        self._corrupted = corrupted
        self._integrity = integrity

        self.ptjsonlib.add_properties({
            "totalFiles":         total,
            "validFiles":         valid,
            "corruptedFiles":     corrupted,
            "unrecoverableFiles": unrecov,
            "integrityScore":     integrity,
            "filesNeedingRepair": len(self._need_repair),
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "reportLoad",
            properties={"success": True, "sourceFile": str(report_file),
                        "totalFiles": total, "validFiles": valid,
                        "corruptedFiles": corrupted}
        ))
        return True

    # -------------------------------------------------------------------------
    # PHASE 2 – ESTIMATE REPAIR SUCCESS RATE
    # -------------------------------------------------------------------------

    def estimate_repair_rate(self) -> float:
        """
        Compute the weighted-average repair success probability across all
        files in the repair list.

        Uses REPAIR_SUCCESS_RATES table keyed on corruptionType /
        corruption_type field from the validation report.

        Returns:
            Estimated success percentage (0.0 – 100.0)
        """
        if not self._need_repair:
            return 0.0

        total_score = 0.0
        for fi in self._need_repair:
            ctype = (fi.get("corruptionType") or
                     fi.get("corruption_type") or "unknown")
            total_score += REPAIR_SUCCESS_RATES.get(ctype,
                                                     REPAIR_SUCCESS_RATES["unknown"])

        estimate = total_score / len(self._need_repair) * 100
        self._repair_estimate = round(estimate, 1)

        ptprint(f"\n  Repair success estimate: {self._repair_estimate}%  "
                f"({len(self._need_repair)} files)",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_properties({"repairSuccessEstimate": self._repair_estimate})
        return self._repair_estimate

    # -------------------------------------------------------------------------
    # PHASE 3 – DECISION LOGIC
    # -------------------------------------------------------------------------

    def apply_decision_logic(self) -> None:
        """
        Apply five prioritised decision rules and set
        self._strategy, self._next_step, self._confidence, self._reasoning.

        Rules are evaluated top-to-bottom; the first matching rule wins.
        """
        ptprint("\n[STEP 3/5] Applying Decision Logic",
                "TITLE", condition=not self.args.json)

        repairable = len(self._need_repair)
        estimate   = self._repair_estimate

        # ── RULE 1 ──────────────────────────────────────────────────────────
        if self._corrupted == 0:
            self._strategy   = "skip_repair"
            self._next_step  = 18
            self._confidence = "high"
            self._reasoning  = [
                "No corrupted files detected – all recovered photos are valid",
                "Repair step is unnecessary; proceeding directly to cataloging",
            ]
            ptprint("✓ Rule 1 matched: zero corrupted files",
                    "OK", condition=not self.args.json)

        # ── RULE 2 ──────────────────────────────────────────────────────────
        elif repairable == 0:
            self._strategy   = "skip_repair"
            self._next_step  = 18
            self._confidence = "high"
            self._reasoning  = [
                f"All {self._corrupted} corrupted file(s) are classified as "
                f"unrecoverable (false positives / fragmented)",
                "No candidates for repair – proceeding with current valid set",
            ]
            ptprint("✓ Rule 2 matched: no repairable files",
                    "WARNING", condition=not self.args.json)

        # ── RULE 3 ──────────────────────────────────────────────────────────
        elif self._valid < LOW_VALID_THRESHOLD:
            self._strategy   = "perform_repair"
            self._next_step  = 17
            self._confidence = "high"
            self._reasoning  = [
                f"Only {self._valid} valid file(s) recovered – every photo matters",
                f"{repairable} file(s) are candidates for repair "
                f"(estimated {estimate}% success)",
                "Repair is justified regardless of success rate when valid count is low",
            ]
            ptprint(f"✓ Rule 3 matched: low valid count ({self._valid} < {LOW_VALID_THRESHOLD})",
                    "OK", condition=not self.args.json)

        # ── RULE 4 ──────────────────────────────────────────────────────────
        elif estimate >= HIGH_ESTIMATE_THRESHOLD:
            self._strategy   = "perform_repair"
            self._next_step  = 17
            self._confidence = "high" if estimate >= HIGH_CONFIDENCE_ESTIMATE else "medium"
            self._reasoning  = [
                f"{repairable} file(s) can be repaired "
                f"with estimated {estimate}% success rate",
                "Cost-benefit analysis favours repair – "
                "expected improvement justifies the effort",
                f"Estimated additional files: "
                f"+{int(repairable * estimate / 100)}",
            ]
            ptprint(f"✓ Rule 4 matched: repair estimate {estimate}% ≥ {HIGH_ESTIMATE_THRESHOLD}%",
                    "OK", condition=not self.args.json)

        # ── RULE 5 (default) ────────────────────────────────────────────────
        else:
            self._strategy   = "skip_repair"
            self._next_step  = 18
            self._confidence = "medium"
            self._reasoning  = [
                f"{repairable} file(s) potentially repairable, "
                f"but success estimate is low ({estimate}%)",
                f"Already have {self._valid} valid file(s) "
                f"({self._integrity}% integrity score)",
                "Cost-benefit analysis favours skipping repair; "
                "proceeding with current valid set",
            ]
            ptprint(f"⚠ Rule 5 matched: repair estimate {estimate}% < {HIGH_ESTIMATE_THRESHOLD}%",
                    "WARNING", condition=not self.args.json)

        ptprint(f"  Strategy:   {self._strategy}",
                "OK", condition=not self.args.json)
        ptprint(f"  Next step:  Step {self._next_step}",
                "OK", condition=not self.args.json)
        ptprint(f"  Confidence: {self._confidence.upper()}",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.add_properties({
            "strategy":   self._strategy,
            "nextStep":   self._next_step,
            "confidence": self._confidence,
            "reasoning":  self._reasoning,
        })
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "decisionLogic",
            properties={
                "strategy":              self._strategy,
                "nextStep":              self._next_step,
                "confidence":            self._confidence,
                "repairSuccessEstimate": self._repair_estimate,
                "repairableCandidates":  repairable,
            }
        ))

    # -------------------------------------------------------------------------
    # PHASE 4 – EXPECTED OUTCOME
    # -------------------------------------------------------------------------

    def calculate_expected_outcome(self) -> Dict[str, Any]:
        """
        Compute the expected final photo count and improvement percentage.

        For perform_repair:
            expected_additional = repairable × (estimate / 100)
            final_count = valid + expected_additional

        For skip_repair:
            final_count = valid (no change)

        Returns:
            Outcome dict (also stored in ptjsonlib properties)
        """
        repairable = len(self._need_repair)

        if self._strategy == "perform_repair":
            additional = int(repairable * self._repair_estimate / 100)
            final      = self._valid + additional
            final_pct  = round(final / max(self._total, 1) * 100, 2)
            delta      = round(final_pct - self._integrity, 2)
        else:
            additional = 0
            final      = self._valid
            final_pct  = self._integrity
            delta      = 0.0

        outcome: Dict[str, Any] = {
            "currentValid":               self._valid,
            "expectedAdditionalFromRepair": additional,
            "finalExpectedCount":         final,
            "finalExpectedPercent":       final_pct,
            "improvementPercentagePoints": delta,
        }

        ptprint("\n  Expected outcome:", "INFO", condition=not self.args.json)
        ptprint(f"  Current valid:   {self._valid}",
                "INFO", condition=not self.args.json)
        if self._strategy == "perform_repair":
            ptprint(f"  From repair:    +{additional}",
                    "INFO", condition=not self.args.json)
            ptprint(f"  Final count:    {final}  ({final_pct}%)",
                    "OK",   condition=not self.args.json)
            ptprint(f"  Improvement:   +{delta} pp",
                    "OK",   condition=not self.args.json)
        else:
            ptprint(f"  Final count:    {final}  ({final_pct}%)  [no change]",
                    "INFO", condition=not self.args.json)

        self.ptjsonlib.add_properties({"expectedOutcome": outcome})
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "expectedOutcome", properties=outcome
        ))
        return outcome

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate the five-phase decision pipeline."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("REPAIR DECISION", "TITLE", condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.load_validation_report():
            self.ptjsonlib.set_status("finished")
            return

        ptprint("\n[STEP 2/5] Estimating Repair Success Rate",
                "TITLE", condition=not self.args.json)
        self.estimate_repair_rate()

        self.apply_decision_logic()

        ptprint("\n[STEP 4/5] Calculating Expected Outcome",
                "TITLE", condition=not self.args.json)
        self.calculate_expected_outcome()

        # Console summary
        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("DECISION SUMMARY", "OK",    condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Strategy:   {self._strategy.upper()}",
                "OK",   condition=not self.args.json)
        ptprint(f"Next step:  Step {self._next_step}",
                "OK",   condition=not self.args.json)
        ptprint(f"Confidence: {(self._confidence or '?').upper()}",
                "INFO", condition=not self.args.json)
        ptprint("\nReasoning:", "INFO", condition=not self.args.json)
        for r in self._reasoning:
            ptprint(f"  • {r}", "INFO", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    # -------------------------------------------------------------------------
    # PHASE 5 – SAVE REPORT
    # -------------------------------------------------------------------------

    def save_report(self) -> Optional[str]:
        """
        Phase 5 – Persist the decision to disk.

        --json mode: prints ptlibs JSON to stdout only.
        Otherwise writes {case_id}_repair_decision.json.

        Returns:
            Path to saved file, or None in --json mode
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        decision_file = self.output_dir / f"{self.case_id}_repair_decision.json"
        props         = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]

        if not self.dry_run:
            with open(decision_file, "w", encoding="utf-8") as fh:
                json.dump(props, fh, indent=2, ensure_ascii=False)

        ptprint(f"✓ Decision saved: {decision_file.name}",
                "OK", condition=not self.args.json)

        # Human-readable one-liner
        if self._strategy == "perform_repair":
            outcome = props.get("expectedOutcome", {})
            ptprint(
                f"\n→ PERFORM REPAIR (Step 17) | "
                f"Expected +{outcome.get('expectedAdditionalFromRepair',0)} files "
                f"(+{outcome.get('improvementPercentagePoints',0)} pp)",
                "OK", condition=not self.args.json
            )
        else:
            ptprint(
                f"\n→ SKIP REPAIR (Step 18 – Cataloging) | "
                f"{self._valid} valid files ready",
                "OK", condition=not self.args.json
            )

        return str(decision_file)


# ============================================================================
# CLI HELPERS
# ============================================================================

def get_help():
    return [
        {"description": [
            "Automated repair decision tool – ptlibs compliant",
            "Analyses Step 15 validation results and decides whether to",
            "perform photo repair (→ Step 17) or skip to cataloging (→ Step 18)",
        ]},
        {"usage": ["ptrepairdecision <case-id> [options]"]},
        {"usage_example": [
            "ptrepairdecision PHOTO-2025-001",
            "ptrepairdecision CASE-042 --json",
            "ptrepairdecision TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",    "",              "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<dir>",  f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",              "Simulate with synthetic validation data"],
            ["-j",  "--json",       "",      "JSON output for platform integration"],
            ["-q",  "--quiet",      "",      "Suppress progress output"],
            ["-h",  "--help",       "",      "Show this help and exit"],
            ["--version",  "",              "Show version and exit"],
        ]},
        {"decision_rules": [
            "R1: corrupted == 0                           → skip_repair   (HIGH)",
            "R2: repairable candidates == 0               → skip_repair   (HIGH)",
            f"R3: valid < {LOW_VALID_THRESHOLD} (every photo matters)  → perform_repair (HIGH)",
            f"R4: repair estimate ≥ {HIGH_ESTIMATE_THRESHOLD}%                    → perform_repair (HIGH/MEDIUM)",
            f"R5: repair estimate < {HIGH_ESTIMATE_THRESHOLD}%   (default)        → skip_repair   (MEDIUM)",
        ]},
        {"repair_success_rates": [
            f"truncated:        {int(REPAIR_SUCCESS_RATES['truncated']*100)}%  (missing footer – easy)",
            f"invalid_header:   {int(REPAIR_SUCCESS_RATES['invalid_header']*100)}%  (header rebuild)",
            f"corrupt_segments: {int(REPAIR_SUCCESS_RATES['corrupt_segments']*100)}%  (segment removal)",
            f"corrupt_data:     {int(REPAIR_SUCCESS_RATES['corrupt_data']*100)}%  (pixel data – partial)",
            f"fragmented:       {int(REPAIR_SUCCESS_RATES['fragmented']*100)}%  (defragmentation – difficult)",
            f"false_positive:   {int(REPAIR_SUCCESS_RATES['false_positive']*100)}%  (not an image)",
        ]},
        {"forensic_notes": [
            "Pure analysis tool – no files are read or written except the decision JSON",
            "Reads: {case_id}_validation_report.json  (Step 15 output)",
            "Writes: {case_id}_repair_decision.json",
            "ISO/IEC 27037:2012 Section 7.6 / NIST SP 800-86 Section 3.2 compliant",
        ]},
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Automated repair decision"
    )
    parser.add_argument("case_id",         help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run",       action="store_true")
    parser.add_argument("-j", "--json",    action="store_true")
    parser.add_argument("-q", "--quiet",   action="store_true")
    parser.add_argument("--version",       action="version",
                        version=f"{SCRIPTNAME} {__version__}")
    parser.add_argument("--socket-address", type=str, default=None)
    parser.add_argument("--socket-port",    type=str, default=None)
    parser.add_argument("--process-ident",  type=str, default=None)

    if len(sys.argv) == 1 or "-h" in sys.argv or "--help" in sys.argv:
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    if args.json:
        args.quiet = True
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main():
    global SCRIPTNAME
    SCRIPTNAME = "ptrepairdecision"
    try:
        args = parse_args()
        tool = PtRepairDecision(args)
        tool.run()
        tool.save_report()

        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("strategy") else 1

    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())
