# Detaily testu

## Úkol

Opravit poškozené fotografie pomocí automatizovaných technik odpovídajících typu poškození.

## Obtížnost

Střední

## Časová náročnost

45 minut

## Automatický test

Ano

## Popis

Nástroj načte seznam souborů s rozhodnutím `ATTEMPT_REPAIR` z výstupu předchozího kroku (`{CASE_ID}_repair_decisions.json`). Pro každý soubor přiřadí techniku podle `corruptionType`, provede opravu na pracovní kopii a následně validuje výsledek. Originály zůstávají nedotčené.

Spouští se pouze pokud výstup kroku Kontrola fotografií obsahuje záznamy s `ATTEMPT_REPAIR`. Při absenci takových záznamů skript skončí bez provedení oprav.

Podporované formáty: JPEG (oprava na úrovni bajtů), PNG (resave přes PIL). TIFF a RAW nejsou podporovány.

## Jak na to

**1. Ověření předchozích výstupů:**

Zkontrolujte, zda soubor s rozhodnutími obsahuje záznamy `ATTEMPT_REPAIR`:
```bash
grep -c "ATTEMPT_REPAIR" /var/forensics/images/${CASE_ID}_repair_decisions.json
```

Pokud výsledek je `0`, přeskočte tento krok a pokračujte na krok EXIF analýza.

**2. Instalace závislostí:**

```bash
pip install Pillow --break-system-packages
sudo apt-get install libjpeg-turbo-progs
```

**3. Spuštění opravy:**

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
DECISIONS="/var/forensics/images/${CASE_ID}_repair_decisions.json"

# Pouze terminálový výstup
ptphotorepair ${CASE_ID} ${DECISIONS} --analyst "Jméno Analytika"

# S JSON výstupem
ptphotorepair ${CASE_ID} ${DECISIONS} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_repair_report.json

# Simulace bez skutečných změn
ptphotorepair ${CASE_ID} ${DECISIONS} --dry-run
```

Skript pro každý soubor vytvoří pracovní kopii, přiřadí techniku podle `corruptionType` a automaticky provede kroky 4–5.

Exit kódy: `0` – alespoň jeden soubor opraven, `1` – žádný, `130` – přerušeno (Ctrl+C).

**4. Opravné techniky podle typu poškození:**

Vždy pracujte na kopii – originál se nesmí měnit:
```bash
cp originál.jpg /tmp/working_originál.jpg
```

Pro `missing_footer` – doplnění chybějícího markeru EOI:
```python
with open("/tmp/working.jpg", "r+b") as f:
    data = f.read()
    if not data.endswith(b"\xff\xd9"):
        f.seek(0, 2)
        f.write(b"\xff\xd9")
```

Pro `invalid_header` – obnovení markeru SOI:
```python
with open("/tmp/working.jpg", "rb") as f:
    data = f.read()
soi_pos = data.find(b"\xff\xd8")
if soi_pos > 0:
    with open("/tmp/working.jpg", "wb") as f:
        f.write(data[soi_pos:])
```

Pro `truncated` – částečná obnova přes PIL:
```python
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
img = Image.open("/tmp/working.jpg")
img.load()
img.save("/tmp/working.jpg", "JPEG", quality=95)
```

Pro PNG soubory – resave přes PIL:
```python
from PIL import Image
img = Image.open("/tmp/working.png")
img.load()
img.save("/tmp/working.png", optimize=True)
```

**5. Validace opraveného souboru:**

Po každé opravě ověřte výsledek:
```bash
identify /tmp/working.jpg 2>&1
```

Pokud `identify` projde bez chyby, přesuňte soubor do `{CASE_ID}_repaired/`. Pokud selže, přesuňte do `{CASE_ID}_repair_failed/`.

**6. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` se vytvoří JSON s výsledky. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `photoRepair`:
```json
"photoRepair": {
  "timestamp": "2025-01-26T17:00:00Z",
  "analyst": "Jméno Analytika",
  "totalAttempted": 156,
  "repaired": 134,
  "failed": 22,
  "successRate": 85.9,
  "repairedPath": "PHOTORECOVERY-2025-01-26-001_repaired/",
  "failedPath": "PHOTORECOVERY-2025-01-26-001_repair_failed/",
  "reportFile": "PHOTORECOVERY-2025-01-26-001_repair_report.json"
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T17:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "Oprava fotografií dokončena – 134 úspěšných, 22 neúspěšných",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**7. Archivace výstupů:**

Archivujte do dokumentace případu:
- `${CASE_ID}_repair_report.json` – výsledky včetně techniky a validace pro každý soubor

## Výsledek

Opravené soubory v `${CASE_ID}_repaired/`, neopravitelné v `${CASE_ID}_repair_failed/`. Originály na původních cestách zůstávají nedotčené. Pracovní postup pokračuje na krok EXIF analýza.

## Reference

ISO/IEC 27042:2015 – Section 5 (Investigative processes)

ISO/IEC 10918-1 – JPEG Standard (ITU-T Recommendation T.81, Digital Compression and Coding of Continuous-tone Still Images)

JFIF (JPEG File Interchange Format) Specification, version 1.02

NIST SP 800-86 – Section 3.3 (Analysis)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)