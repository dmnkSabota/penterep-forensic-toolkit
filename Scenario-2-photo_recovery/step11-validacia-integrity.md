# Detaily testu

## Úkol

Validovat integritu obnovených fotografií a identifikovat poškozené soubory.

## Obtížnost

Střední

## Časová náročnost

30 minut – 2 hodiny (závisí na počtu souborů)

## Automatický test

Ano

## Popis

Tento krok validuje každý obnovený obrazový soubor pomocí dvoustupňové kontroly: (1) velikost a rozpoznání typu obsahu (`file` + `identify`), (2) strukturální validace nástrojem specifickým pro formát (jpeginfo, pngcheck, tiffinfo), s PIL jako záložní metodou. Validace probíhá v místě – soubory zůstávají v konsolidovaném adresáři z předchozího kroku. Výstupem je JSON klasifikace s cestou a stavem každého souboru.

## Jak na to

**1. Instalace validačních nástrojů:**

```bash
sudo apt-get install imagemagick jpeginfo pngcheck libtiff-tools
```

Nástroje `jpeginfo`, `pngcheck` a `tiffinfo` jsou volitelné – při jejich absenci skript použije PIL/Pillow jako záložní metodu.

**2. Spuštění validace:**

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
CONSOL="/var/forensics/images/${CASE_ID}_consolidated"

# Pouze terminálový výstup
ptintegrityvalidation ${CASE_ID} ${CONSOL} --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptintegrityvalidation ${CASE_ID} ${CONSOL} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_integrity_validation.json

# Simulace bez čtení souborů
ptintegrityvalidation ${CASE_ID} ${CONSOL} --dry-run
```

Skript rekurzivně prohledá zadaný adresář a pro každý obrazový soubor automaticky provede kroky 3–4.

**3. Základní validace (`file` + `identify`):**

Pro každý soubor zkontrolujte typ obsahu a čitelnost struktury:
```bash
# Ověření typu obsahu – musí vrátit typ obrazu (např. JPEG image data)
file -b soubor.jpg

# Ověření čitelné struktury – musí projít bez chyby
identify soubor.jpg 2>&1
```

Pokud `file -b` nevrátí typ obrazu nebo `identify` selže na souboru větším než 1024 B, soubor je klasifikován jako `CORRUPTED`. Soubory menší než 100 B jsou automaticky `INVALID`.

**4. Strukturální validace (specifická pro formát):**

Pro soubory, které prošly základní validací, proveďte hloubkovou kontrolu podle formátu:

Pro JPEG soubory:
```bash
jpeginfo -c soubor.jpg
```
`OK` → `VALID`. `unexpected end` / `premature end` → `REPAIRABLE / truncated`. `missing EOI` → `REPAIRABLE / missing_footer`. `invalid marker` → `REPAIRABLE / corrupt_segments`.

Pro PNG soubory:
```bash
pngcheck -v soubor.png
```
Bez chyby → `VALID`. `CRC error` / `invalid chunk` → `REPAIRABLE / corrupt_segments`. `premature end` → `REPAIRABLE / truncated`.

Pro TIFF soubory:
```bash
tiffinfo soubor.tiff
```
Bez chyby → `VALID`. `bad value` / `corrupt` → `REPAIRABLE / corrupt_segments`. `not a TIFF` → `CORRUPTED / invalid_header`.

Výsledek každého souboru zaznamenejte do `{CASE_ID}_integrity_validation.json` s poli `path`, `status` a `corruptionType`. Soubory se fyzicky nepřesouvají.

**5. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` se vytvoří JSON s výsledky. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `integrityValidation`:
```json
"integrityValidation": {
  "timestamp": "2025-01-26T16:00:00Z",
  "analyst": "Jméno Analytika",
  "totalValidated": 2612,
  "valid": 2341,
  "repairable": 198,
  "corrupted": 73,
  "corruptionTypes": {
    "missing_footer": 87,
    "truncated": 64,
    "corrupt_segments": 31,
    "invalid_header": 16,
    "unknown": 0
  },
  "validationCatalog": "PHOTORECOVERY-2025-01-26-001_integrity_validation.json"
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T16:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "Validace integrity dokončena – 2341 VALID, 198 REPAIRABLE, 73 CORRUPTED (v místě, bez kopií)",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**6. Archivace výstupů:**

Archivujte do dokumentace případu:
- `${CASE_ID}_integrity_validation.json` – klasifikace každého souboru s cestou, stavem a typem poškození

## Výsledek

Každý soubor v konsolidovaném adresáři je klasifikován jako VALID, REPAIRABLE nebo CORRUPTED. Výsledky uloženy v `{CASE_ID}_integrity_validation.json`. Soubory zůstávají na původním místě – žádné kopírování. Pracovní postup pokračuje do kroku Kontrola fotografií (rozhodnutí o opravě).

## Reference

ISO/IEC 27042:2015 – Section 5 (Investigative processes)

NIST SP 800-86 – Section 3.3 (Analysis)

ImageMagick Documentation (https://imagemagick.org/)

LibJPEG / jpeginfo Documentation (https://github.com/tjko/jpeginfo)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)