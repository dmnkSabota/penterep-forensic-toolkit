# Detaily testu

## Úkol

Konsolidovat všechny zprávy pracovního postupu do jednoho hlavního dokumentu řetězce důkazů s chronologickou časovou osou.

## Obtížnost

Jednoduchá

## Časová náročnost

10 minut

## Automatický test

Ano

## Popis

Konsolidace je finální zapečetění řetězce důkazů **po dokončení všech analytických kroků** a **před generováním závěrečné zprávy** v kroku Vytvoření reportu. Skript `ptcocmanager --mode consolidate` automaticky detekuje všechny JSON zprávy v `--output-dir`, sestaví chronologickou časovou osu ze všech záznamů `chainOfCustody`, vypočítá SHA-256 každé zprávy (manifest) a vygeneruje hlavní JSON dokument řetězce důkazů.

Hlavní dokument řetězce důkazů obsahuje:
- **Chronologickou časovou osu** – všechny záznamy CoC ze všech kroků, seřazené podle časového razítka
- **Manifest** – SHA-256 hashe všech JSON zpráv pro ověření integrity
- **Konsolidovaný inventář artefaktů** – forenzní obraz, obnovené soubory, carved dataset, opravené soubory, databáze EXIF
- **Blok specifický pro scénář** – pro obnovu fotografií obsahuje `client.data`
- **Křížové ověření (sanity check)** – opakovaná kontrola konzistence hashů

Tento dokument je vstupem do kroku Vytvoření reportu (závěrečná zpráva) a slouží jako jediný zdroj pravdy pro řetězec důkazů.

## Jak na to

**1. Spuštění konsolidace:**

Skript automaticky detekuje scénář z předpony `PHOTORECOVERY-*` a načte všechny dostupné zprávy z `--output-dir`:

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"

# Pouze terminálový výstup
ptcocmanager ${CASE_ID} --mode consolidate \
  --client-data "Jméno Klienta, Art.6(1)(b) GDPR" \
  --analyst "Jméno Analytika"

# S JSON výstupem (hlavní dokument řetězce důkazů)
ptcocmanager ${CASE_ID} --mode consolidate \
  --client-data "Jméno Klienta, Art.6(1)(b) GDPR" \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_coc_master.json
```

**2. Jaké zprávy skript hledá:**

Automatické vyhledávání projde tyto vzory v `--output-dir`:

| Typ | Zdrojový skript | Vzor |
|-----|-----------------|---------|
| imaging | `ptforensicimaging` | `${CASE_ID}_imaging.json` |
| verification | `ptimageverification` | `${CASE_ID}_verification.json` |
| readability | `ptmediareadability` | `${CASE_ID}_readability.json` |
| filesystem | `ptfilesystemanalysis` | `${CASE_ID}_filesystem_analysis.json` |
| fs_recovery | `ptfilesystemrecovery` | `${CASE_ID}_recovery_report.json` |
| carving | `ptfilecarving` | `${CASE_ID}_carving.json` |
| consolidation | `ptrecoveryconsolidation` | `${CASE_ID}_consolidation_report.json` |
| integrity | `ptintegrityvalidation` | `${CASE_ID}_integrity_validation.json` |
| repair_decision | `ptrepairdecision` | `${CASE_ID}_repair_decisions.json` |
| repair | `ptphotorepair` | `${CASE_ID}_repair_report.json` |
| exif | `ptexifanalysis` | `${CASE_ID}_exif_database.json` |

Chybějící zprávy jsou přeskočeny (zaznamenány jako `INFO`, ne chyba). Skript však vyžaduje minimálně `imaging` a `verification` – jinak skončí s chybou.

**3. Struktura hlavního JSON dokumentu řetězce důkazů:**

Skript vyprodukuje `${CASE_ID}_coc_master.json` se třemi hlavními uzly:

**Uzel `cocTimeline`** – chronologická časová osa všech záznamů CoC:
```json
"cocTimeline": {
  "entryCount": 12,
  "sourceReports": ["readability", "imaging", "verification", "filesystem", "carving", "consolidation", "integrity", "repair", "exif"],
  "entries": [
    {
      "timestamp": "2025-01-26T10:00:00Z",
      "action": "Media readability test completed - status: READABLE",
      "analyst": "Jméno Analytika",
      "tool": "ptmediareadability",
      "sourceReport": "readability"
    },
    {
      "timestamp": "2025-01-26T11:00:00Z",
      "action": "Forensic imaging complete - source_hash: a3f5...",
      "analyst": "Jméno Analytika",
      "tool": "dc3dd",
      "sourceReport": "imaging"
    },
    ...
  ]
}
```

**Uzel `cocDocumentation`** – hlavní dokument řetězce důkazů:
```json
"cocDocumentation": {
  "scenario": "photo-recovery",
  "mode": "consolidate",
  "sourceHash": "a3f5e8c9d2b1a7f4...",
  "imageHash": "a3f5e8c9d2b1a7f4...",
  "crossValidated": true,
  "scenarioSpecific": {
    "client": {"data": "Jméno Klienta, Art.6(1)(b) GDPR"}
  },
  "artefacts": [
    {"type": "forensic_image", "path": ".../CASE.dd", "sha256": "a3f5...", "sizeBytes": 32212254720, "sourceReport": "imaging"},
    {"type": "fs_recovered_dataset", "path": ".../CASE_recovered", "sourceReport": "fs_recovery"},
    {"type": "carved_dataset", "path": ".../CASE_carved", "sourceReport": "carving"},
    {"type": "recovered_dataset", "path": ".../CASE_consolidated", "sourceReport": "consolidation"}
  ]
}
```

**Uzel `manifest`** – SHA-256 každé zprávy:
```json
"manifest": {
  "generatedAt": "2025-01-26T17:00:00Z",
  "fileCount": 11,
  "files": [
    {"filename": "CASE_imaging.json", "sha256": "b2c3d4...", "sizeBytes": 2048, "label": "imaging"},
    {"filename": "CASE_verification.json", "sha256": "c3d4e5...", "sizeBytes": 1024, "label": "verification"},
    ...
  ]
}
```

**4. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` skript vytvoří hlavní JSON dokument řetězce důkazů. Analytik manuálně zkopíruje závěrečný záznam do `case.json`:

```json
{
  "timestamp": "2025-01-26T17:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "CoC consolidation [photo-recovery] - 11 reports, 47 timeline entries, cross-validation: PASS",
  "result": "SUCCESS"
}
```

**5. Archivace výstupů:**

Archivujte do dokumentace případu:
- `${CASE_ID}_coc_master.json` – hlavní dokument řetězce důkazů (vstup pro krok Vytvoření reportu)
- Všechny původní JSON zprávy (manifest se na ně odkazuje SHA-256)

## Výsledek

Hlavní JSON dokument řetězce důkazů s úplnou chronologickou časovou osou, manifestem integrity a inventářem všech artefaktů. Pracovní postup pokračuje do kroku Vytvoření reportu (závěrečná zpráva), který hlavní dokument řetězce důkazů použije jako primární vstup.

Při neúspěšném křížovém ověření (`crossValidated: false`) skript vrátí exit kód 1 a hlavní dokument je označen jako neplatný. **Nepřecházejte do kroku Vytvoření reportu** – vraťte se do kroku Kontrola hash a vyřešte problém.

## Reference

ISO/IEC 27037:2012 – Section 5.4.5 (Preservation) & Section 6.1 (Chain of custody) & Section 6.6 (Documentation)

ISO/IEC 27042:2015 – Section 6 (Investigation closure and reporting)

NIST SP 800-86 – Section 3.4 (Reporting)

NIST FIPS 180-4 – Secure Hash Standard (SHA-256 pro manifest)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 4 (Overall responsibility for compliance with the principles)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)