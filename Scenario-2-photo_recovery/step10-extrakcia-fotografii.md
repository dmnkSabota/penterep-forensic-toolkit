# Detaily testu

## Úkol

Spojit obnovené fotografie do jednoho deduplikovaného datasetu.

## Obtížnost

Jednoduchá

## Časová náročnost

30 minut

## Automatický test

Ano

## Popis

Tento krok sjednotí výstupy z kroků obnovy (Skenování souborového systému a/nebo File Carving) do jednoho organizovaného datasetu pomocí SHA-256 deduplikace napříč zdroji. Soubory obnovené ze souborového systému mají přednost před carved soubory stejného SHA-256 – zachovávají metadata a původní názvy. Provádí se vždy – při `filesystem_scan` zpracuje jeden zdroj, při `hybrid` oba.

## Jak na to

**1. Ověření dostupných zdrojů:**

Zkontrolujte, které výstupy z předchozích kroků existují:
```bash
ls /var/forensics/images/${CASE_ID}_recovered/
ls /var/forensics/images/${CASE_ID}_carved/valid/
```

Pokud žádný adresář neexistuje, vraťte se k Skenování souborového systému nebo File Carving.

**2. Spuštění skriptu:**

Skript přijímá 3 poziční argumenty: `case-id`, `fs_recovery_dir`, `carved_dir`. Prázdný řetězec `""` v kterémkoli z adresářů znamená, že daný zdroj neexistuje (přeskočí se).

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
BASE="/var/forensics/images"
FS_DIR="${BASE}/${CASE_ID}_recovered"
CARVED_DIR="${BASE}/${CASE_ID}_carved/valid"

# Hybrid: oba zdroje
ptrecoveryconsolidation ${CASE_ID} "${FS_DIR}" "${CARVED_DIR}" \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_consolidation_report.json

# Pouze filesystem_scan (carving neproběhl)
ptrecoveryconsolidation ${CASE_ID} "${FS_DIR}" "" \
  --analyst "Jméno Analytika"

# Pouze file_carving (obnova ze souborového systému neproběhla)
ptrecoveryconsolidation ${CASE_ID} "" "${CARVED_DIR}" \
  --analyst "Jméno Analytika"

# Simulace bez kopírování souborů
ptrecoveryconsolidation ${CASE_ID} "${FS_DIR}" "${CARVED_DIR}" --dry-run
```

Skript provede kroky 3–5 automaticky.

**3. Hashování zdrojů přes SHA-256:**

Skript rekurzivně projde oba adresáře, pro každý obrazový soubor (filtrované přes `IMAGE_EXTENSIONS`) vypočítá SHA-256 přes sdílenou metodu `_file_sha256`. Sleduje průběh přes `_progress`.

**4. Deduplikace napříč zdroji:**

Pro každý soubor:
- Pokud hash již existuje v `seen_hashes` → duplikát (přeskočit).
- Pokud hash je nový → kopie do konsolidovaného adresáře.

Soubory obnovené ze souborového systému jsou zpracovány **první** – tím získávají prioritu před carved kopií stejného hashe.

**5. Kopírování do konsolidovaného adresáře:**

Soubory jsou kopírovány do `${CASE_ID}_consolidated/<format_group>/`, kde `format_group` je z `FORMAT_GROUP_MAP` (jpeg/png/tiff/raw/other). Při kolizi názvů se přidá prvních 8 znaků SHA-256 jako přípona.

**6. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` se vytvoří JSON s výsledky. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `photoConsolidation`:
```json
"photoConsolidation": {
  "timestamp": "2025-01-26T15:30:00Z",
  "analyst": "Jméno Analytika",
  "sourcesProcessed": ["filesystem_recovery", "file_carving"],
  "filesFromFilesystem": 1223,
  "filesFromCarving": 1876,
  "duplicatesRemoved": 487,
  "uniqueFiles": 2612,
  "byFormat": {"jpeg": 2030, "png": 415, "tiff": 70, "raw": 60, "other": 37},
  "consolidatedDir": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001_consolidated",
  "consolidationReport": "PHOTORECOVERY-2025-01-26-001_consolidation_report.json"
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T15:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Konsolidace dokončena - 2612 unikátních souborů, 487 duplikátů odstraněno",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**7. Archivace výstupů:**

Archivujte do dokumentace případu:
- `${CASE_ID}_consolidation_report.json` – přehled statistik
- Adresář `${CASE_ID}_consolidated/` s podadresáři podle skupin formátů

## Výsledek

Konsolidovaný dataset v `${CASE_ID}_consolidated/<format_group>/`. Pracovní postup pokračuje do kroku Validace integrity fotografií.

## Reference

ISO/IEC 27042:2015 – Section 5 (Investigative processes)

NIST SP 800-86 – Section 3.3 (Analysis)

NIST FIPS 180-4 – Secure Hash Standard (SHA-256 pro deduplikaci)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)