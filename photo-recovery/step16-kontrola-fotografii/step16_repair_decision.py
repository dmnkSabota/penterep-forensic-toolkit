#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-DECISION: Rozhodnutie o oprave fotografií
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript automaticky rozhodne či pristúpiť k oprave poškodených fotografií
alebo pokračovať priamo na katalogizáciu.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False


class RepairDecision:
    """
    Automatické rozhodovanie o oprave fotografií.
    
    Proces:
    1. Load validation results from Step 15
    2. Apply decision rules
    3. Calculate expected outcome
    4. Determine confidence level
    5. Generate reasoning
    6. Output decision
    """
    
    # Odhad úspešnosti opravy podľa typu poškodenia
    REPAIR_SUCCESS_ESTIMATES = {
        'truncated': 0.85,  # 85% úspešnosť
        'invalid_header': 0.70,
        'corrupt_segments': 0.60,
        'corrupt_data': 0.40,
        'fragmented': 0.15,
        'false_positive': 0.0,
        'unknown': 0.50
    }
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        
        # Validation report path
        self.validation_report_path = self.output_dir / f"{case_id}_validation_report.json"
        
        # Input data
        self.validation_data = None
        
        # Decision output
        self.decision = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "input_conditions": {},
            "strategy": None,
            "next_step": None,
            "confidence": None,
            "reasoning": [],
            "expected_outcome": {}
        }
    
    def _print(self, message, level="INFO"):
        """Helper pre výpis"""
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
    
    def load_validation_results(self):
        """Načítanie výsledkov validácie z Kroku 15"""
        self._print("\nLoading validation results from Step 15...", "TITLE")
        
        if not self.validation_report_path.exists():
            self._print(f"ERROR: Validation report not found: {self.validation_report_path}", "ERROR")
            self._print("Please run Step 15 (Integrity Validation) first!", "ERROR")
            return False
        
        try:
            with open(self.validation_report_path, 'r', encoding='utf-8') as f:
                self.validation_data = json.load(f)
            
            stats = self.validation_data["statistics"]
            
            # Extract key values
            self.decision["input_conditions"] = {
                "total_files": stats["total_files"],
                "valid_files": stats["valid_files"],
                "corrupted_files": stats["corrupted_files"],
                "unrecoverable_files": stats["unrecoverable_files"],
                "integrity_score": stats["integrity_score"],
                "files_needing_repair": len(self.validation_data.get("files_needing_repair", []))
            }
            
            self._print(f"Validation report loaded", "OK")
            self._print(f"Total files: {self.decision['input_conditions']['total_files']}", "INFO")
            self._print(f"Valid files: {self.decision['input_conditions']['valid_files']}", "INFO")
            self._print(f"Corrupted files: {self.decision['input_conditions']['corrupted_files']}", "INFO")
            self._print(f"Files needing repair: {self.decision['input_conditions']['files_needing_repair']}", "INFO")
            self._print(f"Integrity score: {self.decision['input_conditions']['integrity_score']}%", "INFO")
            
            return True
            
        except Exception as e:
            self._print(f"ERROR loading validation report: {str(e)}", "ERROR")
            return False
    
    def estimate_repair_success_rate(self):
        """Odhad úspešnosti opravy na základe typov poškodení"""
        
        files_needing_repair = self.validation_data.get("files_needing_repair", [])
        
        if not files_needing_repair:
            return 0.0
        
        total_estimate = 0.0
        
        for file_info in files_needing_repair:
            corruption_type = file_info.get("corruption_type", "unknown")
            estimate = self.REPAIR_SUCCESS_ESTIMATES.get(corruption_type, 0.50)
            total_estimate += estimate
        
        avg_estimate = (total_estimate / len(files_needing_repair)) * 100
        
        return round(avg_estimate, 1)
    
    def apply_decision_logic(self):
        """
        Aplikácia rozhodovacích pravidiel.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("DECISION LOGIC", "TITLE")
        self._print("="*70, "TITLE")
        
        cond = self.decision["input_conditions"]
        
        corrupted = cond["corrupted_files"]
        repairable = cond["files_needing_repair"]
        valid = cond["valid_files"]
        total = cond["total_files"]
        
        # Estimate repair success rate
        repair_estimate = self.estimate_repair_success_rate()
        self.decision["input_conditions"]["repair_success_estimate"] = repair_estimate
        
        reasoning = []
        
        # PRAVIDLO 1: Žiadne poškodené súbory
        if corrupted == 0:
            self.decision["strategy"] = "skip_repair"
            self.decision["next_step"] = 18
            self.decision["confidence"] = "high"
            reasoning.append("No corrupted files detected - all photos are valid")
            reasoning.append("No repair necessary - proceeding directly to cataloging")
            
            self._print("\nRULE 1: No corrupted files", "OK")
            self._print("Decision: SKIP REPAIR → Step 18 (Cataloging)", "OK")
        
        # PRAVIDLO 2: Žiadne opraviteľné súbory
        elif repairable == 0:
            self.decision["strategy"] = "skip_repair"
            self.decision["next_step"] = 18
            self.decision["confidence"] = "high"
            reasoning.append(f"All {corrupted} corrupted files are unrecoverable")
            reasoning.append("No files can be repaired - proceeding to cataloging with valid files only")
            
            self._print("\nRULE 2: No repairable files", "WARNING")
            self._print("Decision: SKIP REPAIR → Step 18 (Cataloging)", "OK")
        
        # PRAVIDLO 3: Málo validných súborov (<50) - každá fotka cenná
        elif valid < 50:
            self.decision["strategy"] = "perform_repair"
            self.decision["next_step"] = 17
            self.decision["confidence"] = "high"
            reasoning.append(f"Only {valid} valid files recovered - every photo counts")
            reasoning.append(f"{repairable} files potentially repairable (estimated {repair_estimate}% success)")
            reasoning.append("Attempting repair to maximize final count")
            
            self._print("\nRULE 3: Low valid count - every photo matters", "INFO")
            self._print("Decision: PERFORM REPAIR → Step 17 (Photo Repair)", "OK")
        
        # PRAVIDLO 4: Vysoká úspešnosť opravy (>50%)
        elif repairable > 0 and repair_estimate >= 50:
            self.decision["strategy"] = "perform_repair"
            self.decision["next_step"] = 17
            
            if repair_estimate >= 70:
                self.decision["confidence"] = "high"
            else:
                self.decision["confidence"] = "medium"
            
            reasoning.append(f"{repairable} files can be repaired with estimated {repair_estimate}% success rate")
            reasoning.append("High repair success probability - worth the effort")
            reasoning.append("Repair will significantly improve final count")
            
            self._print(f"\nRULE 4: High repair success estimate ({repair_estimate}%)", "OK")
            self._print("Decision: PERFORM REPAIR → Step 17 (Photo Repair)", "OK")
        
        # PRAVIDLO 5: Nízka úspešnosť opravy (<50%) a dosť validných
        elif repairable > 0 and repair_estimate < 50:
            self.decision["strategy"] = "skip_repair"
            self.decision["next_step"] = 18
            self.decision["confidence"] = "medium"
            reasoning.append(f"{repairable} files potentially repairable but low success estimate ({repair_estimate}%)")
            reasoning.append(f"Already have {valid} valid files ({cond['integrity_score']}% integrity)")
            reasoning.append("Cost-benefit analysis favors skipping repair - proceed with valid files")
            
            self._print(f"\nRULE 5: Low repair success estimate ({repair_estimate}%)", "WARNING")
            self._print("Decision: SKIP REPAIR → Step 18 (Cataloging)", "OK")
        
        # DEFAULT: Skip
        else:
            self.decision["strategy"] = "skip_repair"
            self.decision["next_step"] = 18
            self.decision["confidence"] = "medium"
            reasoning.append("No clear benefit from attempting repair")
            reasoning.append("Proceeding with valid files to cataloging")
            
            self._print("\nDEFAULT: Proceed without repair", "INFO")
            self._print("Decision: SKIP REPAIR → Step 18 (Cataloging)", "OK")
        
        self.decision["reasoning"] = reasoning
    
    def calculate_expected_outcome(self):
        """Výpočet očakávaného výsledku"""
        
        cond = self.decision["input_conditions"]
        
        valid = cond["valid_files"]
        repairable = cond["files_needing_repair"]
        total = cond["total_files"]
        repair_estimate = cond.get("repair_success_estimate", 0)
        
        if self.decision["strategy"] == "perform_repair":
            # Očakávané dodatočné súbory z opravy
            expected_additional = int(repairable * (repair_estimate / 100))
            final_count = valid + expected_additional
            final_percentage = (final_count / total) * 100 if total > 0 else 0
            improvement = final_percentage - cond["integrity_score"]
            
            self.decision["expected_outcome"] = {
                "current_valid": valid,
                "expected_additional_from_repair": expected_additional,
                "final_expected_count": final_count,
                "final_percentage": round(final_percentage, 2),
                "improvement_percentage_points": round(improvement, 2)
            }
            
            self._print("\nExpected outcome:", "INFO")
            self._print(f"  Current valid: {valid}", "INFO")
            self._print(f"  Expected from repair: +{expected_additional}", "INFO")
            self._print(f"  Final count: {final_count} ({final_percentage:.1f}%)", "OK")
            self._print(f"  Improvement: +{improvement:.1f} percentage points", "OK")
        
        else:
            # Bez opravy
            final_percentage = cond["integrity_score"]
            
            self.decision["expected_outcome"] = {
                "current_valid": valid,
                "expected_additional_from_repair": 0,
                "final_expected_count": valid,
                "final_percentage": final_percentage,
                "improvement_percentage_points": 0.0
            }
            
            self._print("\nExpected outcome:", "INFO")
            self._print(f"  Final count: {valid} ({final_percentage:.1f}%)", "INFO")
            self._print(f"  No repair - proceeding with current valid files", "INFO")
    
    def make_decision(self):
        """Hlavná funkcia - vykonaj rozhodnutie"""
        
        self._print("="*70, "TITLE")
        self._print("REPAIR DECISION", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Load validation results
        if not self.load_validation_results():
            return None
        
        # 2. Apply decision logic
        self.apply_decision_logic()
        
        # 3. Calculate expected outcome
        self.calculate_expected_outcome()
        
        # 4. Summary
        self._print("\n" + "="*70, "TITLE")
        self._print("DECISION SUMMARY", "TITLE")
        self._print("="*70, "TITLE")
        
        self._print(f"Strategy: {self.decision['strategy'].upper()}", "OK")
        self._print(f"Next step: Step {self.decision['next_step']}", "OK")
        self._print(f"Confidence: {self.decision['confidence'].upper()}", "INFO")
        
        self._print("\nReasoning:", "INFO")
        for reason in self.decision["reasoning"]:
            self._print(f"  • {reason}", "INFO")
        
        self._print("="*70 + "\n", "TITLE")
        
        return self.decision
    
    def save_decision(self):
        """Uloženie rozhodnutia"""
        
        decision_file = self.output_dir / f"{self.case_id}_repair_decision.json"
        
        with open(decision_file, 'w', encoding='utf-8') as f:
            json.dump(self.decision, f, indent=2, ensure_ascii=False)
        
        self._print(f"Decision saved: {decision_file}", "OK")
        
        return str(decision_file)


def main():
    """
    Hlavná funkcia
    """
    
    print("\n" + "="*70)
    print("FOR-COL-DECISION: Repair Decision")
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
    
    # Make decision
    decision_maker = RepairDecision(case_id)
    decision = decision_maker.make_decision()
    
    if decision:
        # Save decision
        decision_maker.save_decision()
        
        # Output next step
        if decision["next_step"] == 17:
            print(f"\n✓ Decision: PERFORM REPAIR")
            print(f"Next step: Step 17 (Photo Repair)")
            print(f"Expected improvement: +{decision['expected_outcome']['improvement_percentage_points']:.1f} percentage points")
        else:
            print(f"\n✓ Decision: SKIP REPAIR")
            print(f"Next step: Step 18 (Cataloging)")
            print(f"Proceeding with {decision['expected_outcome']['current_valid']} valid files")
        
        sys.exit(0)
    else:
        print("\nDecision failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - DECISION LOGIC
================================================================================

AUTOMATED REPAIR DECISION
- Analyzes validation results from Step 15
- Applies rule-based decision logic
- Calculates cost-benefit analysis
- Determines next workflow step

FIVE DECISION RULES

RULE 1: No corrupted files (corrupted = 0)
→ Strategy: SKIP REPAIR
→ Next step: 18 (Cataloging)
→ Confidence: HIGH
→ Reasoning: All photos valid, nothing to repair

RULE 2: No repairable files (files_needing_repair = 0)
→ Strategy: SKIP REPAIR
→ Next step: 18 (Cataloging)
→ Confidence: HIGH
→ Reasoning: All corrupted files are unrecoverable

RULE 3: Low valid count (valid < 50)
→ Strategy: PERFORM REPAIR
→ Next step: 17 (Photo Repair)
→ Confidence: HIGH
→ Reasoning: Every photo counts when total is low

RULE 4: High repair success (repairable > 0 AND estimate ≥ 50%)
→ Strategy: PERFORM REPAIR
→ Next step: 17 (Photo Repair)
→ Confidence: HIGH (if estimate ≥ 70%) or MEDIUM
→ Reasoning: Good probability of successful repair

RULE 5: Low repair success (repairable > 0 AND estimate < 50%)
→ Strategy: SKIP REPAIR
→ Next step: 18 (Cataloging)
→ Confidence: MEDIUM
→ Reasoning: Low probability, already have good valid count

REPAIR SUCCESS ESTIMATES BY CORRUPTION TYPE
- truncated: 85% (missing footer - easily fixable)
- invalid_header: 70% (corrupt header - repairable)
- corrupt_segments: 60% (segment issues - moderate)
- corrupt_data: 40% (pixel corruption - partial)
- fragmented: 15% (fragmentation - difficult)
- false_positive: 0% (not an image - impossible)

EXPECTED OUTCOME CALCULATION
- expected_additional = repairable × (repair_estimate / 100)
- final_count = valid + expected_additional
- final_percentage = (final_count / total) × 100
- improvement = final_percentage - current_integrity_score

================================================================================
EXAMPLE OUTPUT
================================================================================

======================================================================
REPAIR DECISION
Case ID: PHOTO-2025-01-26-001
======================================================================

Loading validation results from Step 15...
[✓] Validation report loaded
[i] Total files: 692
[i] Valid files: 623
[i] Corrupted files: 54
[i] Files needing repair: 38
[i] Integrity score: 90.03%

======================================================================
DECISION LOGIC
======================================================================

RULE 4: High repair success estimate (65.5%)
[✓] Decision: PERFORM REPAIR → Step 17 (Photo Repair)

Expected outcome:
[i]   Current valid: 623
[i]   Expected from repair: +25
[✓]   Final count: 648 (93.6%)
[✓]   Improvement: +3.6 percentage points

======================================================================
DECISION SUMMARY
======================================================================
[✓] Strategy: PERFORM_REPAIR
[✓] Next step: Step 17
[i] Confidence: MEDIUM

Reasoning:
[i]   • 38 files can be repaired with estimated 65.5% success rate
[i]   • High repair success probability - worth the effort
[i]   • Repair will significantly improve final count

======================================================================

[✓] Decision saved: PHOTO-2025-01-26-001_repair_decision.json

✓ Decision: PERFORM REPAIR
Next step: Step 17 (Photo Repair)
Expected improvement: +3.6 percentage points

================================================================================
USAGE
================================================================================

INTERACTIVE MODE:
$ python3 step16_repair_decision.py
Case ID: PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step16_repair_decision.py PHOTO-2025-01-26-001

REQUIREMENTS:
- Step 15 (Integrity Validation) must be completed
- Python 3 with json module

TIME ESTIMATE:
- < 1 minute (instant analysis)

================================================================================
DECISION OUTPUT FORMAT
================================================================================

{
  "case_id": "PHOTO-2025-01-26-001",
  "timestamp": "2025-01-26T23:00:00Z",
  "input_conditions": {
    "total_files": 692,
    "valid_files": 623,
    "corrupted_files": 54,
    "unrecoverable_files": 15,
    "integrity_score": 90.03,
    "files_needing_repair": 38,
    "repair_success_estimate": 65.5
  },
  "strategy": "perform_repair",
  "next_step": 17,
  "confidence": "medium",
  "reasoning": [
    "38 files can be repaired with estimated 65.5% success rate",
    "High repair success probability - worth the effort",
    "Repair will significantly improve final count"
  ],
  "expected_outcome": {
    "current_valid": 623,
    "expected_additional_from_repair": 25,
    "final_expected_count": 648,
    "final_percentage": 93.6,
    "improvement_percentage_points": 3.6
  }
}

================================================================================
"""