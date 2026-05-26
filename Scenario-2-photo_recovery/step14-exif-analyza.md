# Detaily testu

## Úkol

Extrahovat a analyzovat metadata EXIF ze všech obnovených fotografií.

## Obtížnost

Jednoduchá

## Časová náročnost

30 minut

## Automatický test

Ano

## Popis

Nástroj dávkově extrahuje metadata EXIF pomocí `exiftool` ze všech obrazových souborů v zadaném adresáři. Provede analýzu časové osy, seznam zařízení, GPS souřadnice a detekci anomálií (budoucí datum záznamu, neobvyklé ISO, změna po vytvoření).

## Jak na to

**1. Ověření předchozích výstupů:**

Poznamenejte si cestu ke konsolidovanému adresáři a případně k adresáři opravených souborů:
```bash
ls /var/forensics/images/${CASE_ID}_consolidated/
ls /var/forensics/images/${CASE_ID}_repaired/    # pokud proběhla oprava
```

**2. Instalace závislostí:**

```bash
sudo apt-get install libimage-exiftool-perl
```

**3. Spuštění analýzy:**

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
CONSOL="/var/forensics/images/${CASE_ID}_consolidated"

# Pouze terminálový výstup
ptexifanalysis ${CASE_ID} ${CONSOL} --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptexifanalysis ${CASE_ID} ${CONSOL} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_exif_analysis.json

# Simulace bez spuštění exiftool
ptexifanalysis ${CASE_ID} ${CONSOL} --dry-run
```

První argument je identifikátor případu, druhý je povinná cesta k adresáři s fotografiemi. Pokud chcete zahrnout i opravené soubory, spusťte nástroj znovu na adresáři `{CASE_ID}_repaired/`. Skript automaticky provede kroky 4–5.

**4. Dávková extrakce metadat EXIF:**

Extrahujte EXIF ze všech souborů v jednom volání:
```bash
EXIF_DIR="/var/forensics/images/${CASE_ID}_exif_analysis"
mkdir -p "${EXIF_DIR}"

exiftool -j -G -a -s -n "${CONSOL}/" \
  > "${EXIF_DIR}/${CASE_ID}_exif_database.json"
```

Volitelně exportujte CSV pro tabulkový editor:
```bash
exiftool -csv -G -a "${CONSOL}/" \
  > "${EXIF_DIR}/${CASE_ID}_exif_data.csv"
```

**5. Analýza metadat:**

Analýza časové osy – seskupení podle data:
```bash
exiftool -DateTimeOriginal -T -r "${CONSOL}/" \
  | sort | uniq -c | sort -rn
```

Seznam zařízení:
```bash
exiftool -Make -Model -T -r "${CONSOL}/" \
  | sort | uniq -c | sort -rn
```

Souřadnice GPS:
```bash
exiftool -GPSLatitude -GPSLongitude -FileName -T -r "${CONSOL}/" \
  | grep -v "^-"
```

Detekce editačního softwaru:
```bash
exiftool -Software -FileName -T -r "${CONSOL}/" \
  | grep -iv "^-" \
  | grep -i "photoshop\|lightroom\|gimp\|affinity\|instagram\|snapseed\|vsco\|facetune"
```

**6. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` se vytvoří JSON s výsledky. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `exifAnalysis`:
```json
"exifAnalysis": {
  "timestamp": "2025-01-26T17:30:00Z",
  "analyst": "Jméno Analytika",
  "totalProcessed": 2612,
  "exifPositive": 2341,
  "withDateTimeOriginal": 2198,
  "withGPS": 412,
  "anomaliesDetected": 7,
  "anomalyTypes": {
    "future_date": 2,
    "unusual_iso": 3,
    "modify_after_original": 2
  },
  "exifDatabase": "PHOTORECOVERY-2025-01-26-001_exif_analysis.json"
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T17:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "EXIF analýza dokončena – 2341 souborů s EXIF, 7 anomálií",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**7. Archivace výstupů:**

Archivujte do dokumentace případu:
- `${CASE_ID}_exif_analysis.json` – kompletní databáze EXIF s metadaty každého souboru a anomáliemi

## Výsledek

Kompletní databáze EXIF s metadaty každého souboru, časovou osou, seznamem GPS souřadnic a detekovanými anomáliemi. Výsledky zaznamenané v dokumentaci případu. Pracovní postup pokračuje na krok CoC konsolidace.

## Reference

CIPA DC-008-Translation-2023 (Exif Version 3.0) – Exchangeable image file format for digital still cameras

ISO 12234-2:2001 – Electronic still-picture imaging – Removable memory – Part 2: TIFF/EP image data format

Farid, H. (2016). Photo Forensics. MIT Press, Chapters 3–4.

Casey, E. (2011). Digital Evidence and Computer Crime (3rd ed.). Academic Press / Elsevier, Chapter 14.

ExifTool Documentation (https://exiftool.org)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)