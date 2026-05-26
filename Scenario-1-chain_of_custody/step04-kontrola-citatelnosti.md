# Detaily testu

## Úkol

Klasifikovat čitelnost forenzního média a vybrat nástroj pro vytvoření forenzního obrazu.

## Obtížnost

Jednoduchá

## Časová náročnost

5–10 minut

## Automatický test

Ano

## Popis

Tento krok klasifikuje forenzní médium jako READABLE, PARTIAL nebo UNREADABLE pomocí série diagnostických testů v režimu pouze pro čtení v souladu s ISO/IEC 27037:2012. Výsledek přímo určuje nástroj pro vytvoření obrazu: READABLE → dc3dd, PARTIAL → ddrescue. Při výsledku UNREADABLE se vytvoření obrazu neprovede – médium je nečitelné bez fyzické opravy, která je mimo rozsah tohoto scénáře. Analytik dokumentuje nález a případ eskaluje vyšetřovateli se stavem `UNREADABLE_MEDIA`.

## Jak na to

**1. Ověřte a připojte write-blocker:**

Fyzicky připojte write-blocker (write-blocker) a zapojte médium přes něj – nikdy ne přímo. Ověřte, že LED indikátor svítí (PROTECTED). U mechanických HDD zkontrolujte, zda zařízení nevydává neobvyklé zvuky (škrábání, cvakání).

Identifikujte cestu k zařízení (například `/dev/sdb`):

```bash
lsblk -d -o NAME,SIZE,TYPE,MODEL,SERIAL,TRAN
```

**2. Spuštění testu:**

```bash
# Pouze terminálový výstup
ptmediareadability /dev/sdb COC-2025-01-26-001 --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptmediareadability /dev/sdb COC-2025-01-26-001 \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_readability.json
```

Skript provede potvrzení write-blockeru (manuální výzva), předběžnou detekci (lsblk, blkid, smartctl, hdparm, mdadm) a diagnostické testy čitelnosti.

**3. Vyhodnocení výsledku:**

- **READABLE** → nástroj pro vytvoření obrazu: `dc3dd` – pokračujte vytvořením obrazu média s nástrojem dc3dd
- **PARTIAL** → nástroj pro vytvoření obrazu: `ddrescue` – pokračujte vytvořením obrazu média s nástrojem ddrescue
- **UNREADABLE** → médium není čitelné – pokračujte větví eskalace níže

Pokud byly identifikovány kritické nálezy (šifrování LUKS, BitLocker nebo VeraCrypt, aktivní TRIM, členství v poli RAID, kritické hodnoty SMART), informujte vyšetřovatele před pokračováním.

**4. Větev UNREADABLE – eskalace:**

Zaznamenejte nález do záznamu řetězce důkazů a nastavte stav případu na `UNREADABLE_MEDIA`. Kontaktujte vyšetřovatele s dokumentací o stavu média. Fyzická oprava médií je mimo rozsah tohoto scénáře a vyžaduje specializovanou laboratoř. Pracovní postup se pro tento případ zastavuje.

**5. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` skript vytvoří JSON s forenzními metadaty. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `readabilityTest`:

```json
"readabilityTest": {
  "version": "1.0.0",
  "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
  "caseId": "COC-2025-01-26-001",
  "timestamp": "2025-01-26T10:00:00Z",
  "analyst": "Jméno Analytika",
  "device": {
    "devicePath": "/dev/sdb",
    "mediaStatus": "READABLE",
    "recommendedTool": "dc3dd"
  },
  "criticalFindings": [],
  "statistics": {
    "testsRun": 4,
    "testsPassed": 4,
    "testsFailed": 0
  }
}
```

Nový záznam do pole `chainOfCustody`:

```json
{
  "timestamp": "2025-01-26T10:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "Test čitelnosti média – výsledek: READABLE, nástroj: dc3dd"
}
```

## Výsledek

READABLE / PARTIAL: médium klasifikováno, nástroj pro vytvoření obrazu vybrán. Pracovní postup pokračuje do kroku Forenzní imaging s příslušným nástrojem.

UNREADABLE: nález zdokumentován, stav případu nastaven na `UNREADABLE_MEDIA`, vyšetřovatel kontaktován. Pracovní postup zastaven.

## Reference

ISO/IEC 27037:2012 – Section 5.4.3 (Collection) & Section 6.9 (Preservation of potential digital evidence)

NIST SP 800-86 – Section 3.1.1 (Identifying Possible Sources of Data)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 1 (No action taken should change data)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)