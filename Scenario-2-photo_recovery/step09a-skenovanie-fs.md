# Detaily testu

## Úkol

Využít funkční souborový systém k identifikaci a obnově obrazových souborů.

## Obtížnost

Střední

## Časová náročnost

60 minut

## Automatický test

Ano

## Popis

Obnova ze souborového systému využívá zachovanou adresářovou strukturu forenzního obrazu k identifikaci a extrakci obrazových souborů pomocí nástrojů `fls` a `icat` z balíku The Sleuth Kit. Původní názvy souborů, adresářová struktura a časová razítka FS jsou zachovány. Provádí se při strategii `filesystem_scan` nebo `hybrid` (určené krokem Analýza souborového systému).

## Jak na to

**1. Ověření strategie a příprava:**

Z výstupu kroku Analýza souborového systému zkontrolujte doporučenou strategii – musí být `filesystem_scan` nebo `hybrid`. Při `file_carving` tento krok přeskočte a pokračujte krokem File Carving.

Pro každý oddíl z `filesystem_analysis.json` zaznamenejte jeho **offset v sektorech** (z výstupu `mmls`). Skript zpracuje jeden oddíl na spuštění.

Ověřte dostupnost nástrojů:
```bash
which fls icat file identify exiftool
```
Instalace (pokud chybí):
```bash
sudo apt-get install sleuthkit imagemagick libimage-exiftool-perl
```

**2. Spuštění skriptu:**

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
IMAGE="/var/forensics/images/${CASE_ID}.dd"
OFFSET=2048        # z výstupu mmls v kroku Analýza souborového systému (offset oddílu v sektorech)

# Pouze terminálový výstup
ptfilesystemrecovery ${CASE_ID} ${IMAGE} --offset ${OFFSET} --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptfilesystemrecovery ${CASE_ID} ${IMAGE} \
  --offset ${OFFSET} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_recovery_report.json

# Simulace bez spuštění fls/icat
ptfilesystemrecovery ${CASE_ID} ${IMAGE} --offset ${OFFSET} --dry-run
```

Při **formátu superfloppy** (USB flash, SD karta bez tabulky oddílů) použijte `--offset 0`. Při **disku s více oddíly** spusťte skript samostatně pro každý oddíl s příslušným offsetem; výsledky následně sloučí `ptrecoveryconsolidation` v kroku Extrakce fotografií.

Skript ověří existenci obrazu, dostupnost nástrojů a automaticky provede kroky 3–5.

Exit kódy: `0` – alespoň jeden platný soubor obnoven, `1` – žádný soubor, `130` – přerušeno (Ctrl+C).

**3. Skenování souborového systému (`fls`):**

Skript interně spustí:
```bash
fls -r -p -o ${OFFSET} "${IMAGE}"
```
Zpracuje výstup, filtruje na obrazové přípony (z konstanty `IMAGE_EXTENSIONS`), oddělí aktivní a smazané záznamy podle značky `*` ve stavu. Pro každý záznam si poznamená inode číslo.

**4. Extrakce (`icat`) a validace:**

Pro každý záznam:
```bash
icat -o ${OFFSET} "${IMAGE}" <INODE> > <output>
```
- Aktivní soubory → `${CASE_ID}_recovered/active/<original_path>/`
- Smazané soubory → `${CASE_ID}_recovered/deleted/<original_path>/`

Skript následně pro každý extrahovaný soubor zavolá `_validate_image_file` (sdílená metoda) – `file -b` + `identify`. Neplatné soubory jsou odstraněny, poškozené (>1024 B) zůstávají se stavem `corrupted`.

**5. Extrakce metadat EXIF:**

Pro každý platný soubor skript volá sdílenou metodu `_extract_exif_metadata` (přes `exiftool`). Záznamy s daty EXIF jsou počítány do čítače `withExif`.

**6. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` skript vytvoří JSON s výsledky. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `filesystemRecovery`:
```json
"filesystemRecovery": {
  "timestamp": "2025-01-26T14:00:00Z",
  "analyst": "Jméno Analytika",
  "method": "filesystem_scan",
  "imagePath": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001.dd",
  "offset": 2048,
  "imageFilesFound": 1247,
  "activeImages": 834,
  "deletedImages": 413,
  "validImages": 1223,
  "corruptedImages": 24,
  "withExif": 1098,
  "byFormat": {"jpeg": 980, "png": 215, "tiff": 28},
  "outputDir": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001_recovered",
  "successRate": 98.1
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T14:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "Obnova ze souborového systému dokončena - 1223 platných souborů obnoveno z oddílu offset=2048",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**7. Archivace výstupů:**

Archivujte do dokumentace případu:
- `${CASE_ID}_recovery_report.json` – souhrn výsledků
- Adresář `${CASE_ID}_recovered/` s podadresáři `active/` a `deleted/`

## Výsledek

Obnovené soubory uloženy v `${CASE_ID}_recovered/`: aktivní v `active/`, smazané v `deleted/`, s původními cestami a názvy zachovanými. Pracovní postup pokračuje do kroku File Carving (pokud `hybrid`) nebo přímo do kroku Extrakce fotografií.

## Reference

ISO/IEC 27042:2015 – Section 5 (Investigative processes)

NIST SP 800-86 – Section 3.2 (Examination) & Section 4 (Using Data from Data Files)

The Sleuth Kit Documentation – fls, icat (https://www.sleuthkit.org/)

Brian Carrier: File System Forensic Analysis (Addison-Wesley, 2005), Chapter 8

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)