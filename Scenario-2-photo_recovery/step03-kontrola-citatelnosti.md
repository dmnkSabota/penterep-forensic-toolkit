# Detaily testu

## Úkol

Je médium čitelné?

## Obtížnost

Jednoduchá

## Časová náročnost

5–10 minut

## Automatický test

Ano

## Popis

Tento rozhodovací bod určuje klíčové větvení pracovního postupu. Analytik připojí médium přes write-blocker, provede sérii diagnostických příkazů pouze pro čtení a na základě výsledků klasifikuje médium jako READABLE, PARTIAL nebo UNREADABLE. Všechny příkazy pracují výhradně v režimu čtení – originální médium se nesmí modifikovat.

## Jak na to

**1. Ověřte a připojte write-blocker:**

Fyzicky připojte write-blocker a zapojte médium přes něj – nikdy ne přímo. Ověřte, že LED indikátor svítí (PROTECTED). U mechanických HDD zkontrolujte, zda zařízení nevydává neobvyklé zvuky (škrábání, cvakání).

Pokud některá podmínka není splněna, nepokračujte – existuje riziko poškození důkazu.

Identifikujte cestu k zařízení (např. `/dev/sdb`) – použijete ji ve všech následujících příkazech místo `/dev/sdX`.

**2. Spuštění testu pomocí skriptu:**

```bash
# Pouze terminálový výstup
ptmediareadability /dev/sdb PHOTORECOVERY-2025-01-26-001 --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptmediareadability /dev/sdb PHOTORECOVERY-2025-01-26-001 --analyst "Jméno Analytika" --json-out ${CASE_ID}_readability.json
```

Skript provede potvrzení write-blockeru (manuální výzva) a následně automaticky předběžnou detekci a diagnostické testy.

**3. Předběžná detekce:**

Ověřte, že OS zařízení vidí, a zaznamenejte základní informace:
```bash
lsblk -d -o NAME,SIZE,TYPE,MODEL,SERIAL,TRAN /dev/sdX
```

Zjistěte souborový systém a zkontrolujte přítomnost šifrování (signatura LUKS, hlavička BitLocker):
```bash
blkid /dev/sdX
```
Prázdný výsledek u poškozeného média není chyba – zaznamenejte ho jako „žádná odpověď".

Pro HDD a SSD zkontrolujte zdravotní data SMART:
```bash
smartctl -a /dev/sdX
```
Sledujte: Reallocated Sector Count (vyšší hodnoty naznačují poškození), Current Pending Sector Count (>0 = aktivně selhává), Uncorrectable Sector Count a teplotu (zvýšená teplota představuje riziko – referenční hodnoty se liší podle výrobce). Flash média SMART nepodporují – chyba příkazu je v pořádku.

Pro SSD zařízení zaznamenejte stav podpory TRIM:
```bash
hdparm -I /dev/sdX | grep TRIM
```
Pokud je TRIM aktivní, upozorněte klienta – smazaná data mohou být fyzicky odstraněna a obnova může být neúplná.

Pokud `lsblk` naznačuje pole RAID, zjistěte konfiguraci:
```bash
mdadm --examine /dev/sdX
```
Pokud je médium součástí pole RAID, upozorněte klienta, že pro úplnou obnovu je potřeba přístup ke všem členům pole.

**4. Diagnostické testy:**

Pokuste se přečíst první sektor (512 B). Pokud tento příkaz selže, médium je nečitelné:
```bash
dd if=/dev/sdX of=/dev/null bs=512 count=1 status=none
```

Zkuste sekvenční čtení 1 MB:
```bash
dd if=/dev/sdX of=/dev/null bs=512 count=2048 status=none
```

Otestujte čtení na třech různých pozicích média (začátek, střed, konec):
```bash
dd if=/dev/sdX of=/dev/null bs=512 count=1 skip=2048 status=none
dd if=/dev/sdX of=/dev/null bs=512 count=1 skip=$(($(blockdev --getsize64 /dev/sdX) / 1024)) status=none
dd if=/dev/sdX of=/dev/null bs=512 count=1 skip=$(($(blockdev --getsize64 /dev/sdX) / 512 - 20480)) status=none
```

Změřte rychlost čtení 10 MB – výrazně nízká rychlost může naznačovat extrémně dlouhé vytváření obrazu nebo riziko selhání během procesu:
```bash
dd if=/dev/sdX of=/dev/null bs=512 count=20480 status=progress
```

**5. Vyhodnocení a klasifikace:**

Na základě výsledků klasifikujte médium:
- Všechny testy prošly → **READABLE** → doporučený nástroj: `dc3dd`
- Test sekvenčního čtení prošel, některé jiné selhaly → **PARTIAL** → doporučený nástroj: `ddrescue`
- Test prvního sektoru selhal → **UNREADABLE** → pokračuje krok Fyzická oprava média

Pokud byly identifikovány kritické nálezy (aktivní TRIM, špatný stav SMART, šifrování, RAID), informujte klienta o omezeních obnovy před pokračováním.

**6. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` skript vytvoří JSON s forenzními metadaty. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `readabilityTest`:
```json
"readabilityTest": {
  "version": "1.0.0",
  "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
  "caseId": "PHOTORECOVERY-2025-01-26-001",
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
  "action": "Test čitelnosti média – výsledek: READABLE, nástroj: dc3dd",
  "mediaSerial": "SN-XXXXXXXX"
}
```

## Výsledek

Stav média je klasifikován jako READABLE, PARTIAL nebo UNREADABLE. Výsledky předběžné detekce a všech diagnostických testů jsou zobrazeny na terminálu a volitelně uloženy do JSON souboru. Klient je informován o případných kritických omezeních. Analytik pokračuje do příslušného kroku.

## Reference

ISO/IEC 27037:2012 – Section 5.4.3 (Collection) & Section 6.9 (Preservation of potential digital evidence)

NIST SP 800-86 – Section 3.1.1 (Identifying Possible Sources of Data)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 1 (No action taken should change data)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)