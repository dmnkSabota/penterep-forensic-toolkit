# Detaily testu

## Úkol

Je potrebné pristúpiť k oprave poškodených fotografií, alebo možno pokračovať priamo na katalogizáciu?

## Obtiažnosť

Jednoduchá

## Časová náročnosť

1 minúta

## Automatický test

Áno

## Popis

Toto je rozhodovací bod vo workflow, ktorý určuje, či je investícia času do opravy poškodených súborov opodstatnená. Rozhodnutie vychádza z výsledkov validácie integrity a empirických mier úspešnosti opravy podľa typu poškodenia.

Systém aplikuje päť pravidiel v poradí priority: ak nie sú žiadne poškodené súbory → preskočiť opravu, ak žiadny súbor nie je opraviteľný → preskočiť, ak je obnovených málo validných fotografií → opraviť bez ohľadu na odhadovanú úspešnosť, ak odhadovaná úspešnosť opravy ≥ 50 % → opraviť, inak → preskočiť. Odhadovaná úspešnosť sa vypočíta ako vážený priemer podľa typov poškodení (truncated 85 %, corrupt_segments 60 %, corrupt_data 40 %, fragmented 15 %).

Vstupom je `{case_id}_validation_report.json`. Výstupom je `{case_id}_repair_decision.json`.

## Jak na to

**1. Načítanie validačného reportu:**

Systém načíta `{case_id}_validation_report.json` a extrahuje štatistiky: počet validných, poškodených a neopraviteľných súborov, integrity score a zoznam súborov odporúčaných na opravu.

**2. Odhad úspešnosti opravy:**

Pre každý súbor v zozname opraviteľných systém vyhľadá empirickú mieru úspešnosti podľa typu poškodenia a vypočíta vážený priemer.

**3. Aplikácia rozhodovacích pravidiel:**

Päť pravidiel v poradí priority (R1–R5) určí stratégiu (`perform_repair` alebo `skip_repair`) a úroveň istoty (`high`/`medium`).

**4. Výpočet očakávaného výsledku:**

Pri `perform_repair`: `expected_additional = repairable × (estimate / 100)`, `final_count = valid + expected_additional`. Pri `skip_repair` sa počty nemenia.

**5. Uloženie rozhodnutia:**

Systém uloží `{case_id}_repair_decision.json` so stratégiou, odôvodnením, úrovňou istoty a očakávaným výsledkom.

## Výsledek

JSON súbor s rozhodnutím: `strategy` (perform_repair / skip_repair), `confidence` (high / medium), `reasoning` (text odôvodnenia), `expectedOutcome` (expected_additional_files, final_expected_count, improvement_pp). Čistá analytická operácia – žiadne súbory sa nekopírujú ani nemenia.

## Reference

ISO/IEC 27037:2012 – Section 7.6 (Decision making)
NIST SP 800-86 – Section 3.2 (Analysis decisions)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Empirické miery úspešnosti (REPAIR_SUCCESS_RATES) sú konzervatívne odhady – skutočná úspešnosť závisí od konkrétneho stavu média. Pravidlo R3 (málo validných súborov) je zámerne agresívne: keď je obnovených menej ako 50 fotografií, každá ďalšia má vysokú hodnotu pre klienta bez ohľadu na nízku pravdepodobnosť opravy.