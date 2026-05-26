# Detaily testu

## Úkol

Vytvořit závěrečnou zprávu konsolidující výstupy všech předchozích kroků.

## Obtížnost

Jednoduchá

## Časová náročnost

10 minut

## Automatický test

Ne

## Popis

Závěrečná zpráva je generována platformou z průběžně budované dokumentace případu. Každý krok pracovního postupu do ní od začátku přispívá svými výstupy a záznamy řetězce důkazů – v tomto kroku je dokumentace kompletní a zpráva se z ní vygeneruje bez manuálního doplňování.

## Jak na to

**1. Kontrola úplnosti dokumentace případu:**

Každý krok pracovního postupu měl přidat své výstupy do dokumentace případu. Před generováním zprávy ověřte, že jsou přítomné záznamy ze všech povinných kroků:

| Krok | Výstupní soubor | Povinné |
|------|----------------|---------|
| Přijetí žádosti a vytvoření identifikátoru případu | `case.json` (první záznam) | Ano |
| Identifikace média a fotodokumentace | Záznam CoC č. 2 | Ano |
| Test čitelnosti média | `{CASE_ID}_readability.json` | Ano |
| Forenzní vytvoření obrazu + SHA-256 | `{CASE_ID}_imaging.json` | Ano |
| Ověření hashe SHA-256 | `{CASE_ID}_verification.json` | Ano |
| Analýza souborového systému | `{CASE_ID}_filesystem_analysis.json` | Ano |
| Skenování souborového systému / File Carving | `{CASE_ID}_recovery_report.json` / `{CASE_ID}_carving.json` | Ano |
| Extrakce fotografií (konsolidace) | `{CASE_ID}_consolidation_report.json` | Ano |
| Validace integrity fotografií | `{CASE_ID}_integrity_validation.json` | Ano |
| Rozhodnutí o opravě fotografií | `{CASE_ID}_repair_decisions.json` | Ano |
| Oprava fotografií | `{CASE_ID}_repair_report.json` | Ne |
| EXIF analýza | `{CASE_ID}_exif_analysis/{CASE_ID}_exif_database.json` | Ne |

**2. Struktura závěrečné zprávy:**

Platforma sestaví zprávu z nashromážděné dokumentace. Každá sekce má přesně definovaný zdroj:

**S1 – Shrnutí pro management (Executive Summary)**
Z `integrity_validation.json` (počty, skóre integrity) + `exif_database.json` (pokrytí EXIF) + `repair_report.json` (opravené soubory). Celkový počet obnovených fotografií, hodnocení kvality, seznam co klient dostává.

**S2 – Informace o případu**
Z `case.json` – identifikátor případu, jméno analytika, datum přijetí žádosti, klasifikace dokumentu. Vyplněné v kroku Přijetí žádosti.

**S3 – Informace o důkazu**
Z `case.json` (fyzická identifikace) + `readability.json` (stav média) + `imaging.json` (write-blocker, SHA-256). Vyplněné v krocích Identifikace média a Kontrola čitelnosti.

**S4 – Metodika**
Generováno automaticky podle toho, které kroky pracovního postupu proběhly a které nástroje byly použity (dc3dd/ddrescue, fls/icat, PhotoRec, ExifTool, PIL).

**S5 – Časová osa**
Z časových razítek záznamů CoC všech kroků – chronologický průběh případu od přijetí po závěrečnou zprávu.

**S6 – Výsledky**
Z `integrity_validation.json` + `repair_report.json` + `exif_database.json` + `consolidation_report.json`. Počty souborů, skóre integrity, statistiky opravy, pokrytí EXIF.

**S7 – Technické detaily**
Z `filesystem_analysis.json` (typ FS, strategie) + `integrity_validation.json` (validační logika) + `repair_report.json` (techniky opravy) + `exif_database.json` (parametry EXIF).

**S8 – Zajištění kvality**
Z `integrity_validation.json` (skóre integrity) + `exif_database.json` (skóre kvality EXIF) + `verification.json` (shoda SHA-256).

**S9 – Řetězec důkazů**
Ze záznamů CoC všech kroků – každý krok přidal svůj záznam do `case.json`. Kompletní nepřerušený řetězec od přijetí média po závěrečnou zprávu.

**S10 – Podpisy**
Podpisový blok – `PENDING` do fyzického podepsání oběma stranami.

**3. Recenze nadřízeným:**

Nadřízený analytik zkontroluje:
- Konzistenci čísel napříč sekcemi S1, S6 a S8
- Nepřerušenost řetězce důkazů v S9
- Správnost technických detailů v S7
- Vhodnost jazyka pro případné soudní použití

**4. Podpisy:**

Před předáním klientovi jsou povinné podpisy primárního analytika i recenzenta. Dokud jsou podpisy `PENDING`, zpráva není připravena na předání.

**5. Aktualizace řetězce důkazů:**

Přidejte závěrečný záznam do `case.json`:
```json
{
  "timestamp": "2025-01-26T18:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "Závěrečná zpráva vygenerována a podepsána - připravena na předání",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**6. Archivace výstupů:**

Archivujte do dokumentace případu:
- Závěrečná zpráva (JSON + PDF)
- Podepsaný předávací protokol
- Kontrolní seznam s potvrzením všech položek

## Výsledek

Závěrečná zpráva s 10 sekcemi podepsaná oběma stranami a připravená na předání klientovi. Pracovní postup pokračuje na krok Předání zákazníkovi.

## Reference

ISO/IEC 27042:2015 – Section 6 (Investigation closure and reporting)

NIST SP 800-86 – Section 3.4 (Reporting)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 4 (Overall responsibility for compliance with the principles)

SWGDE Best Practices for Computer Forensic Acquisitions / Examinations (Scientific Working Group on Digital Evidence)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)