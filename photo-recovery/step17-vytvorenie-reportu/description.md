# Detaily testu

## Úkol

Vytvoriť finálny report pre klienta aj technické detaily pre expertov.

## Obtiažnosť

Stredná

## Časová náročnosť

60 minút

## Automatický test

Áno

## Popis

Finálny report je najdôležitejší výstup celého procesu. Je to dokument, ktorý dostane klient, môže byť použitý ako dôkaz v súdnom konaní a slúži ako technická dokumentácia preukazujúca profesionalitu laboratória.

Systém načíta JSON reporty zo všetkých predchádzajúcich krokov (`validation_report.json`, `exif_database.json`, `repair_report.json`, `catalog_summary.json`) a konsoliduje ich do 11-sekčného reportu. Povinné vstupy sú iba `validation_report.json` a `catalog_summary.json` – EXIF a repair sú voliteľné. Pri `--dry-run` sa použijú syntetické dáta.

PDF generovanie je voliteľné – vyžaduje `pip install reportlab`. Ak nie je dostupný, výstup v JSON formáte je plnohodnotný.

## Jak na to

**1. Zber dát:**

Systém načíta JSON reporty zo všetkých krokov. Povinné: `{case_id}_validation_report.json` a `{case_id}_catalog/catalog_summary.json`. Voliteľné: EXIF databáza a repair report.

**2. Stavba 11-sekčného reportu:**

Každá sekcia má dedikovanú metódu: executive summary, case info, evidence info, methodology, timeline, výsledky, technické detaily, QA, delivery package, chain of custody, signatures.

**3. PDF report (voliteľný):**

Ak je nainštalovaný reportlab, vygeneruje A4 dokument s cover page, tabuľkami a signature blokom. Bez reportlab sa preskočí.

**4. Klientská dokumentácia:**

`README.txt` s inštrukciami, `delivery_checklist.json` so statusom 8 položiek (6 completed, 2 pending – peer review a podpisy).

**5. Záverečné uloženie:**

`FINAL_REPORT.json` (11 sekcií), `workflow_summary.json` (zhrnutie krokov a deliverables).

## Výsledek

Adresár `{case_id}_final_report/` s: `FINAL_REPORT.json` (11 sekcií), `FINAL_REPORT.pdf` (voliteľný), `README.txt`, `delivery_checklist.json`, `workflow_summary.json`. Peer review a podpisy sú REQUIRED pred odovzdaním. Stav checklist: 6/8 completed, 2 PENDING.

## Reference

ISO/IEC 27037:2012 – Digital evidence handling
NIST SP 800-86 – Forensic Techniques
ACPO Good Practice Guide
SWGDE Best Practices

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

`_get()` helper extrahuje hodnoty z camelCase aj snake_case kľúčov – potrebné pre kompatibilitu medzi rôznymi verziami JSON exportov. `_stats()` helper normalizuje prístup k `result.properties` (ptlibs formát) aj `statistics` (legacy formát). Metóda `_save_client_files()` spája README a checklist do jednej fázy pre čistejší pipeline.