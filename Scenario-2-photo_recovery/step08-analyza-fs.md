# Detaily testu

## Úkol

Analyzovat forenzní obraz média a určit typ souborového systému, jeho stav, oddíly a metadata.

## Obtížnost

Jednoduchá

## Časová náročnost

10 minut

## Automatický test

Ano

## Popis

Analýza souborového systému je první krok forenzní analýzy po vytvoření a ověření forenzního obrazu. Výsledek přímo určuje strategii obnovy: rozpoznaný souborový systém s čitelnou adresářovou strukturou umožňuje obnovu založenou na souborovém systému (zachovává původní názvy souborů a metadata), poškozený nebo nerozpoznaný souborový systém vyžaduje file carving (hledá soubory podle signatur v raw datech).

Všechny příkazy pracují výhradně s forenzním obrazem – originální médium se v této fázi nedotýká.

## Jak na to

**1. Zjištění cesty k obrazu:**

Podívejte se do výstupu z kroku Kontrola hash a zapište si cestu k forenznímu obrazu. Typicky:
```
/var/forensics/images/PHOTORECOVERY-2025-01-26-001.dd
```

**2. Spuštění analýzy pomocí skriptu:**

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
IMAGE="/var/forensics/images/${CASE_ID}.dd"

# Pouze terminálový výstup
ptfilesystemanalysis ${CASE_ID} ${IMAGE} --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptfilesystemanalysis ${CASE_ID} ${IMAGE} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_filesystem_analysis.json
```

Skript automaticky ověří existenci forenzního obrazu a následně provede kroky 3–5.

Exit kódy: `0` – úspěch, `1` – chyba (obraz nenalezen, chybějící nástroje), `130` – přerušeno (Ctrl+C).

**3. Analýza tabulky oddílů (`mmls`):**

```bash
mmls "${IMAGE}"
```

Zaznamenejte typ tabulky (DOS/MBR, GPT), seznam oddílů s offsety a velikostmi. Pokud `mmls` selže nebo nevrátí žádné oddíly, předpokládá se formát superfloppy – celé médium je jeden souborový systém bez tabulky oddílů (typické pro USB flash disky a SD karty). V takovém případě použijte offset `0` v následujících příkazech.

**4. Analýza souborového systému (`fsstat`):**

Pro každý oddíl (nebo offset `0` při superfloppy):
```bash
fsstat -o OFFSET "${IMAGE}"
```

Zaznamenejte typ souborového systému (FAT32, exFAT, NTFS, ext4…), volume label, UUID, velikost sektoru a klastru. Pokud `fsstat` selže, souborový systém je nerozpoznaný nebo poškozený.

**5. Kontrola adresářové struktury (`fls`):**

```bash
fls -r -o OFFSET "${IMAGE}" | grep -iE '\.(jpg|jpeg|png|tiff?|bmp|gif|raw|cr2|nef|arw|dng|heic|webp)$'
```

Smazané soubory jsou v seznamu označené hvězdičkou `*`. Spočítejte aktivní a smazané obrazové soubory.

**6. Určení strategie obnovy:**

Na základě výsledků zvolte strategii:
- Rozpoznaný FS + čitelná adresářová struktura → `filesystem_scan`
- Nerozpoznaný FS (fsstat selhal) → `file_carving`
- Rozpoznaný FS, ale poškozená struktura (fsstat prošel, fls vrátil nekonzistentní data) → `hybrid`

**7. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` se vytvoří JSON s forenzními metadaty. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `filesystemAnalysis`:
```json
"filesystemAnalysis": {
  "version": "1.0.0",
  "compliance": ["NIST SP 800-86", "ISO/IEC 27042:2015"],
  "caseId": "PHOTORECOVERY-2025-01-26-001",
  "timestamp": "2025-01-26T13:30:00Z",
  "analyst": "Jméno Analytika",
  "partitionTable": {
    "tableType": "DOS/MBR",
    "partitionsFound": 1
  },
  "partitions": [
    {
      "partitionNumber": 0,
      "offset": 0,
      "filesystemType": "FAT32",
      "filesystemRecognized": true,
      "volumeLabel": "USB_PHOTOS",
      "directoryReadable": true,
      "imageFiles": {
        "total": 1247,
        "active": 834,
        "deleted": 413
      }
    }
  ],
  "recoveryStrategy": {
    "recommendedMethod": "filesystem_scan",
    "recommendedTool": "fls + icat (The Sleuth Kit)",
    "estimatedTimeMinutes": 15,
    "filesystemRecognized": true,
    "directoryReadable": true,
    "totalImageFiles": 1247
  }
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T13:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Analýza souborového systému – strategie: filesystem_scan",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**8. Archivace výstupů:**

Uložte textový výstup příkazů `mmls`, `fsstat` a `fls` do souboru `${CASE_ID}_filesystem_analysis.txt` pro auditní stopu.

## Výsledek

Typ souborového systému identifikován, stav a čitelnost adresářové struktury ověřeny. Výsledky zaznamenané v JSON souboru včetně tabulky oddílů, typu FS, počtu obrazových souborů a zvolené strategie obnovy.

Další krok závisí na strategii: `filesystem_scan` → Skenování souborového systému, `file_carving` → File Carving, `hybrid` → obě metody.

## Reference

ISO/IEC 27042:2015 – Section 5 (Investigative processes)

NIST SP 800-86 – Section 3.2 (Examination) & Section 4 (Using Data from Data Files)

The Sleuth Kit Documentation – mmls, fsstat, fls tools (https://www.sleuthkit.org/)

Brian Carrier: File System Forensic Analysis (Addison-Wesley, 2005)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)