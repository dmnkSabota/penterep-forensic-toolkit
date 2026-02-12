# Detaily testu

## Úkol

Vytvoriť kompletný, profesionálny finálny report, ktorý dokumentuje celý proces obnovy od začiatku po koniec a poskytuje executive summary pre klienta a technické detaily pre expertov.

## Obtiažnosť

Střední

## Časová náročnosť

60

## Automatický test

Áno

## Popis

Finálny report je najdôležitejší výstup celého procesu. Je to dokument, ktorý dostane klient, môže byť použitý ako dôkaz v súdnom konaní a slúži ako technická dokumentácia preukazujúca profesionalitu laboratória.

Prečo je tento krok kritický:
- Poskytuje klientovi zrozumiteľné zhrnutie celého procesu a výsledkov
- Dokumentuje každý krok pre právne účely (courtroom ready)
- Zahŕňa executive summary v jednoduchom jazyku pre klienta
- Obsahuje technické detaily pre expertov a peer review
- Spĺňa forenzné štandardy (ISO/IEC 27037, NIST SP 800-86, ACPO)

Report konsoliduje výsledky: počet obnovených fotografií, integrity score, časový proces, kompletná dokumentácia, validácia všetkých krokov, odporúčania pre klienta.

## Jak na to

1. ZBER DÁTOVÝCH ZDROJOV - načítaj JSON reporty zo všetkých krokov: validation_report.json, exif_analysis/, repair_report.json, catalog_summary.json, ulož collected_data.json
2. EXECUTIVE SUMMARY - vytvor client-friendly zhrnutie: čo dostali (médium info), čo obnovili (počet fotiek + integrity), what we did (recovery process), what client gets (katalóg + dokumentácia), recommendations (zálohovanie)
3. KOMPLETNÝ REPORT (JSON) - vygeneruj 11-sekčný report: exec summary, case info, evidence, methodology, timeline, results, technical details, QA, delivery package, chain of custody, signatures section
4. PDF GENEROVANIE - ak reportlab dostupný: vytvor PDF s cover page, table of contents, 11 sekcií, formatting, page numbering, signatures, 13+ strán, ak nedostupný skip PDF
5. README PRE KLIENTA - vytvor README.txt: obsah balíka, ako otvoriť katalóg (photo_catalog.html), ako prezerať metadata, zálohovanie (3-2-1 rule), FAQ, support contact
6. DELIVERY CHECKLIST - vytvor checklist.json: katalóg pripravený, report, README, hash hodnoty, peer review (TODO), next steps (podpísanie, delivery, kontakt klienta)

---

## Výsledek

Kompletný finálny report pripravený na peer review a odovzdanie. JSON report: 11 sekcií konsolidujúcich dáta zo všetkých krokov. PDF report (optional): 13+ strán profesionálnej dokumentácie. README.txt: návod pre klienta, inštrukcie, zálohovanie, FAQ. Delivery checklist: 7 položiek na overenie. Metriky: report completeness 100%, data accuracy verifikovaná, peer review REQUIRED, podpisy REQUIRED. Výstupy: FINAL_REPORT.json, FINAL_REPORT.pdf (optional), README.txt, delivery_checklist.json, workflow_summary.json.

## Reference

ISO/IEC 27037:2012 - Digital evidence handling
NIST SP 800-86 - Forensic Techniques
ACPO Good Practice Guide
SWGDE Best Practices

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)