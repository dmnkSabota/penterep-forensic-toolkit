# Detaily testu

## Úkol

Na základe výsledkov validácie integrity (krok 15) automaticky rozhodnúť, či je potrebné pristúpiť k oprave poškodených fotografií (krok 17), alebo môžeme pokračovať priamo na katalogizáciu (krok 18).

## Obtiažnosť

Snadné

## Časová náročnosť

1

## Automatický test

Áno - Python skript automaticky vyhodnotí podmienky (počet poškodených, počet opraviteľných, odhad úspešnosti opravy) a rozhodne podľa pravidiel

## Popis

Toto je druhý kritický rozhodovací bod vo workflow, ktorý určuje či potrebujeme vykonať opravu fotografií pred ich odovzdaním klientovi. Rozhodnutie je založené na automatickej analýze výsledkov z kroku 15.

Prečo je tento krok kritický:
- Určuje, či investujeme čas do opravy poškodených súborov
- Ovplyvňuje konečný počet odovzdaných fotografií
- Vyvažuje čas vs. kvalita výsledku (cost-benefit analýza)
- Manažuje očakávania klienta (realistický odhad finálneho počtu)
- 4 možné varianty: všetky validné (→krok 18), opraviteľné súbory s vysokou úspešnosťou (→krok 17), neopraviteľné (→krok 18), málo validných ale cenné (→krok 17)

Rozhodovacia logika: ak corrupted=0 → skip repair, ak repairable>0 AND estimate>50% → perform repair, ak repairable=0 OR estimate<30% → skip repair, ak valid<50 (málo) → perform repair aj s nízkou úspešnosťou (každá fotka sa počíta). Výsledok určuje next_step: 17 (oprava) alebo 18 (katalogizácia).

## Jak na to

1. NAČÍTANIE VÝSLEDKOV - načítaj JSON report z kroku 15 (integrity_validation.json), extrahuj kľúčové hodnoty: total_photos, valid_files, corrupted_files, unrecoverable_files, potentially_repairable (počet), repair_success_estimate (%), integrity_score
2. ROZHODOVACIA LOGIKA - aplikuj pravidlá: corrupted=0 → strategy="skip_repair" next_step=18, repairable=0 → strategy="skip_repair" next_step=18, repairable>0 AND estimate≥50% → strategy="perform_repair" next_step=17, repairable>0 AND estimate<30% AND valid>50 → strategy="skip_repair" next_step=18, valid<50 → strategy="perform_repair" next_step=17 (každá fotka cenná)
3. VÝPOČET OČAKÁVANÉHO VÝSLEDKU - expected_additional_files = repairable * (estimate / 100), final_expected_count = valid + expected_additional_files, final_percentage = (final_count / total) * 100, improvement = final_percentage - integrity_score
4. URČENIE ISTOTY - confidence: "high" ak estimate>70% alebo corrupted=0, "medium" ak estimate 30-70%, "low" ak estimate<30%, vygeneruj reasoning text vysvetľujúci rozhodnutie
5. KONTROLA MANUÁLNEHO PREPÍSANIA - ak analytik nastaví override_enabled=true: použiť manual_strategy namiesto automatic, vyžaduj override_reason (min 50 znakov), vyžaduj override_approved_by (senior analytik), zdokumentuj dôvod prepísania
6. VYGENEROVANIE REPORTU - vytvor JSON report s decision_timestamp, strategy (perform_repair / skip_repair), next_step (17/18), confidence, reasoning, expected_outcome, ulož ako repair_decision.json, vypíš rozhodnutie do konzoly s vizualizáciou

---

## Výsledek

Automatické rozhodnutie: strategy (perform_repair alebo skip_repair), next_step (17 pre opravu, 18 pre katalogizáciu), confidence level (high/medium/low). Odôvodnenie: jasný reasoning text vysvetľujúci prečo bolo rozhodnutie prijaté na základe podmienok. Očakávaný výsledok: expected_additional_files z opravy, final_expected_count fotografií, final_percentage (% z celku), improvement percentage points. Manual override: <5% prípadov, len v odôvodnených situáciách (klient naliehavo potrebuje, fotografie nenahráditeľné, time-critical). Report obsahuje decision timestamp, input conditions, automatic decision, expected outcome, workflow next step.

## Reference

ISO/IEC 27037:2012 - Section 7.6 (Decision making in forensic process)
NIST SP 800-86 - Section 3.2 (Analysis decisions)
ISO 9001:2015 - Risk-based thinking in decision processes

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
