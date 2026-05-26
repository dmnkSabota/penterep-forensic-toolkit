# Detaily testu

## Úkol

Obnovit obrazové soubory přímým vyhledáváním bajtových signatur v raw datech forenzního obrazu.

## Obtížnost

Střední

## Časová náročnost

30 minut – 8 hodin (závisí na velikosti obrazu a formátu)

## Automatický test

Ano

## Popis

File carving vyhledává soubory přímo v raw datech forenzního obrazu podle jejich bajtových signatur (magic bytes) – nezávisle na souborovém systému. Tento přístup funguje i tehdy, když je souborový systém zcela poškozený nebo neexistuje. Nevýhodou je ztráta původních názvů souborů, adresářové struktury a časových razítek FS.

Carving se vždy provádí na **forenzním obrazu**, nikdy ne přímo na živém zařízení. Skript `ptfilecarving` přijímá formáty RAW (`.dd`, `.raw`, `.img`, `.001`) přímo a formát `.e01` (libewf) automaticky konvertuje přes `ewfexport` před carvingem. Bloková zařízení (`/dev/sdX`) a cesty `/dev/*` skript zamítá – obraz musíte nejprve získat přes `ptforensicimaging`.

Krok se provádí při strategii `file_carving` nebo `hybrid` (určené krokem Analýza souborového systému). Při strategii `filesystem_scan` tento krok přeskočte.

### Podporované vstupní formáty

| Formát | Způsob zpracování | Poznámka |
|--------|--------------------|----------|
| `.dd`, `.raw`, `.img`, `.001` | Přímé carvování | bitový obraz RAW |
| `.e01` (EnCase / libewf) | Automatická konverze přes `ewfexport` → `.raw` | vyžaduje `libewf-tools`; konvertovaný soubor se po dokončení automaticky odstraní (nebo `--keep-converted`) |
| `/dev/sdX` (živé zařízení) | **Zamítnuto** | nejprve vytvořit obraz přes `ptforensicimaging` |

### Omezení automatizace

Skript carvuje **celý forenzní obraz najednou** (od offsetu 0 po konec). Pro speciální případy (carving konkrétního oddílu, fragmentované soubory) je nutný **manuální postup** (sekce 9 níže).

## Jak na to

**1. Ověření strategie a příprava:**

Z výstupu kroku Analýza souborového systému zkontrolujte doporučenou strategii – musí být `file_carving` nebo `hybrid`. Při `filesystem_scan` tento krok přeskočte.

Ověřte dostupnost nástrojů:
```bash
which photorec file identify
which ewfexport     # pouze pokud vstupem bude .e01
```
Instalace (pokud chybí):
```bash
sudo apt-get install testdisk imagemagick file
sudo apt-get install libewf-tools    # pro .e01 podporu
```

**2. Spuštění skriptu (formáty RAW `.dd`/`.raw`/`.img`/`.001`):**

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
IMAGE="/var/forensics/images/${CASE_ID}.dd"

# Pouze terminálový výstup
ptfilecarving ${CASE_ID} ${IMAGE} --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptfilecarving ${CASE_ID} ${IMAGE} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_carving.json

# Simulace bez spuštění PhotoRec
ptfilecarving ${CASE_ID} ${IMAGE} --dry-run
```

**3. Spuštění skriptu (formát `.e01`):**

Skript při `.e01` vstupu nejprve volá `ewfexport` a vytvoří dočasný `.raw` soubor v `--output-dir`. Carving probíhá na konvertovaném `.raw` souboru. Po dokončení se konvertovaný soubor automaticky smaže (příznak `--keep-converted` zachová konvertovaný `.raw` pro opakované použití):

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
IMAGE="/var/forensics/images/${CASE_ID}.E01"

# Konverze + carving + automatický úklid
ptfilecarving ${CASE_ID} ${IMAGE} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_carving.json

# Zachovat konvertovaný .raw soubor pro opakované použití
ptfilecarving ${CASE_ID} ${IMAGE} \
  --keep-converted \
  --analyst "Jméno Analytika"
```

Konvertovaný soubor se ukládá jako `${CASE_ID}_ewfexport.raw` ve výstupním adresáři. Pokud je již přítomen z předchozího běhu, skript ho znovu použije bez opakované konverze.

**4. Spuštění PhotoRec:**

PhotoRec se spouští přes `pexpect` (automatická navigace v menu – whole disk → Other → Free → Search). Výstup průběhu se průběžně zobrazuje na terminál a zaznamenává do log souboru `${CASE_ID}_photorec.log`. Doba běhu závisí na velikosti obrazu – pro 32 GB obvykle 2–4 hodiny.

**5. Filtrování na obrazové přípony:**

Po dokončení PhotoRec skript prefiltruje výsledky na obrazové soubory podle `IMAGE_EXTENSIONS` (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.gif`, `.bmp`, `.heic`, `.webp`, `.cr2`, `.nef`, `.arw`, `.dng`, `.raf`, `.rw2`, ...).

**6. SHA-256 deduplikace:**

Skript spočítá SHA-256 pro každý unikátní soubor (přes sdílenou metodu `_file_sha256`). Duplikáty (stejný hash) jsou přesunuty do `duplicates/`.

**7. Validace extrahovaných souborů:**

Pro každý unikátní soubor skript volá `_validate_image_file` (sdílená metoda) – `file -b` + `identify`. Soubory:
- `valid` → `${CASE_ID}_carved/valid/<format_group>/`
- `corrupted` → `${CASE_ID}_carved/corrupted/`
- `invalid` (signatury falešně pozitivního carvingu) → smazány

**8. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` se vytvoří JSON s výsledky. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `fileCarvingResult`:
```json
"fileCarvingResult": {
  "timestamp": "2025-01-26T15:00:00Z",
  "analyst": "Jméno Analytika",
  "recoveryMethod": "file_carving",
  "sourceFormat": ".e01",
  "carvingTarget": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001_ewfexport.raw",
  "conversionPerformed": true,
  "totalCarved": 2341,
  "validImageFiles": 1876,
  "corrupted": 312,
  "duplicates": 153,
  "validationRate": 80.1,
  "deduplicationRate": 6.5,
  "outputPath": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001_carved/",
  "photorec_log": "PHOTORECOVERY-2025-01-26-001_photorec.log"
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T15:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "File carving dokončen - nalezeno 1876 platných souborů, 153 duplikátů",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**9. Speciální případy (manuální postup):**

Skript carvuje celý obraz od offsetu 0. Pro speciální případy použijte manuální postup:

**Carving konkrétního oddílu (obraz s více oddíly):**

Pokud `filesystem_analysis.json` obsahuje více oddílů a chcete carvovat pouze jeden (např. oddíl ext4 s offsetem 264192 sektorů), nejprve vyřízněte oddíl do samostatného obrazu, poté spusťte skript:
```bash
PART_OFFSET=264192
PART_SIZE_SECTORS=4194304
dd if=${IMAGE} of=${IMAGE}.part2.dd \
   bs=512 skip=${PART_OFFSET} count=${PART_SIZE_SECTORS}

ptfilecarving ${CASE_ID}-part2 ${IMAGE}.part2.dd \
   --analyst "Jméno Analytika" \
   --json-out ${CASE_ID}_part2_carving.json
```

Alternativně interaktivní PhotoRec (uživatel si zvolí oddíl sám):
```bash
photorec ${IMAGE}
# v menu: vybrat konkrétní oddíl → File Format → Search
```

**Carving ze živého zařízení:**

Skript zamítá cesty `/dev/sdX` a bloková zařízení. Nejprve vytvořte obraz přes `ptforensicimaging` a carving spusťte na obrazu. Carving na živém zařízení je v rozporu s NIST SP 800-86 (fáze Examination) a ISO/IEC 27037:2012 (požadavek write-blockeru).

**Optimalizace (omezení formátů pro rychlost):**

PhotoRec předvolen skenuje cca 480 signatur. Pro scénář obnovy fotografií stačí cca 15. Při interaktivním spuštění manuálně:
```bash
photorec ${IMAGE}
# v menu: File Format → Disable All → Enable: jpg, png, tif, gif, bmp, raw, cr2, nef, arw, dng
```

**Carving fragmentovaných souborů:**

PhotoRec dokáže rekonstruovat pouze **souvislé (contiguous)** soubory. Fragmentované (rozkouskované) soubory nejsou obnovitelné tímto nástrojem – jejich obnova vyžaduje specializované carving algoritmy (Scalpel s grammar-based carving, Adroit, atd.). Zmiňte to v závěrečné zprávě jako omezení.

**10. Archivace výstupů:**

Archivujte do dokumentace případu:
- `${CASE_ID}_carving.json` – kompletní zpráva o obnově
- `${CASE_ID}_photorec.log` – log běhu PhotoRec
- Adresář `${CASE_ID}_carved/` s organizovanými soubory (valid/corrupted/duplicates)

## Výsledek

Obnovené soubory organizované v `${CASE_ID}_carved/valid/<format>/`, poškozené v `corrupted/`, duplikáty v `duplicates/`. Zachované: obsah fotografií. Ztracené: původní názvy souborů, adresářová struktura a časová razítka FS. Pracovní postup pokračuje do kroku Extrakce fotografií.

## Reference

ISO/IEC 27042:2015 – Section 5 (Investigative processes)

NIST SP 800-86 – Section 3.2 (Examination) & Section 4 (Using Data from Data Files)

Brian Carrier: File System Forensic Analysis (Addison-Wesley, 2005) – Chapter 14 (File Carving)

PhotoRec Documentation (https://www.cgsecurity.org/wiki/PhotoRec)

Garfinkel, S.L. (2007). Carving contiguous and fragmented files with fast object validation. Digital Investigation, 4(Supplement), 2–12. doi:10.1016/j.diin.2007.06.017

libewf Documentation (https://github.com/libyal/libewf)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)