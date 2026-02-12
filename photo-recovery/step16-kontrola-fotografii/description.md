# Detaily testu

## Úkol

Na základe výsledkov validácie integrity (krok 15) automaticky rozhodnúť, či je potrebné pristúpiť k oprave poškodených fotografií (krok 17), alebo môžeme pokračovať priamo na katalogizáciu (krok 18).

## Obtiažnosť

Snadné

## Časová náročnosť

1

## Automatický test

Áno

## Popis

Toto je rozhodovací bod vo workflow, ktorý určuje či potrebujeme vykonať opravu fotografií pred ich odovzdaním klientovi. Rozhodnutie je založené na automatickej analýze výsledkov z kroku 15.

Prečo je tento krok kritický:
- Určuje, či investujeme čas do opravy poškodených súborov
- Ovplyvňuje konečný počet odovzdaných fotografií
- Vyvažuje čas vs. kvalita výsledku (cost-benefit analýza)
- Manažuje očakávania klienta (realistický odhad finálneho počtu)

Rozhodovacia logika: ak corrupted=0 → skip repair (krok 18), ak repairable>0 AND estimate>50% → perform repair (krok 17), ak repairable=0 OR estimate<30% → skip repair, ak valid<50 (málo) → perform repair aj s nízkou úspešnosťou.

## Jak na to

1. NAČÍTANIE - načítaj validation_report.json z kroku 15, extrahuj: total_files, valid_files, corrupted_files, files_needing_repair, corruption_types
2. ROZHODOVANIE - aplikuj pravidlá: corrupted=0 → skip, repairable=0 → skip, repairable>0 AND valid<50 → repair (každá fotka cenná), repairable>0 AND estimate≥50% → repair
3. OČAKÁVANÝ VÝSLEDOK - expected_additional = repairable * 0.6 (odhad 60% úspešnosti), final_count = valid + expected_additional, improvement = (expected_additional / total) * 100
4. ISTOTA - confidence: "high" ak corrupted=0 alebo estimate>70%, "medium" ak 30-70%, "low" ak <30%, vygeneruj reasoning text
5. REPORT - vytvor repair_decision.json s: strategy (perform_repair/skip_repair), next_step (17/18), confidence, reasoning, expected_outcome

---

## Výsledek

Automatické rozhodnutie: strategy (perform_repair alebo skip_repair), next_step (17 pre opravu, 18 pre katalogizáciu), confidence level (high/medium/low). Odôvodnenie: reasoning text vysvetľujúci rozhodnutie. Očakávaný výsledok: expected_additional_files, final_expected_count, improvement percentage. Report obsahuje decision timestamp, input conditions, automatic decision, expected outcome, next step.

## Reference

ISO/IEC 27037:2012 - Section 7.6 (Decision making)
NIST SP 800-86 - Section 3.2 (Analysis decisions)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)