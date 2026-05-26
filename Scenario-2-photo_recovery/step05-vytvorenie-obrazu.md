# Detaily testu

## Úkol

Vytvořit forenzní obraz média a vypočítat SHA-256 hash originálu.

## Obtížnost

Jednoduchá

## Časová náročnost

60–240 minut

## Automatický test

Ano

## Popis

Forenzní vytvoření obrazu produkuje přesnou bitovou kopii úložného média, která zachycuje vše – aktivní soubory, smazaná data, slack space, nealokovaný prostor a metadata. SHA-256 hash se počítá současně s kopírováním v jednom průchodu (dc3dd) nebo po dokončení (ddrescue). Výběr nástroje: `dc3dd` pro READABLE médium, `ddrescue` pro PARTIAL médium.

Originální médium zůstává připojené přes write-blocker. Všechny analýzy se provádějí na kopii, čímž je zajištěna soudní přípustnost důkazu.

Nástroj `ptforensicimaging` automatizuje proces – potvrzení write-blockeru, kontrolu předpokladů, vytvoření obrazu, hashování a vytvoření kanonického souboru s hashem. Generuje JSON výstup v souladu se standardy.

## Jak na to

**1. Ověřte a připojte write-blocker:**

Fyzicky připojte write-blocker a zapojte médium přes něj – nikdy ne přímo. Ověřte, že LED indikátor svítí (PROTECTED).

**Write-blocker je VŽDY povinný** – skript vyžaduje potvrzení před každým spuštěním. Pokud podmínka není splněna, nepokračujte – existuje riziko poškození důkazu.

Identifikujte cestu k zařízení:
```bash
lsblk -d -o NAME,SIZE
```

**2. Kontrola dostupného místa:**

Ujistěte se, že cílové úložiště má dostatečnou rezervu kapacity oproti zdrojovému médiu – doporučuje se minimálně stejná kapacita plus rezerva pro log soubory a metadata:
```bash
df -h /var/forensics/images
lsblk -d -o NAME,SIZE /dev/sdX
```
Nedostatek místa během vytváření obrazu může způsobit ztrátu důkazu – vždy počítejte s rezervou.

**3. Poznamenejte si výsledky testu čitelnosti:**

Z výsledků kroku Kontrola čitelnosti si poznamenejte:
- `devicePath` – cesta k zařízení (např. `/dev/sdb`)
- `mediaStatus` – READABLE nebo PARTIAL
- `recommendedTool` – `dc3dd` nebo `ddrescue`

Tyto hodnoty použijete jako parametry skriptu.

**4. Spuštění skriptu:**

```bash
# Pouze terminálový výstup
ptforensicimaging PHOTORECOVERY-2025-01-26-001 /dev/sdb dc3dd --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptforensicimaging PHOTORECOVERY-2025-01-26-001 /dev/sdb dc3dd --analyst "Jméno Analytika" --json-out ${CASE_ID}_imaging.json

# Pro PARTIAL médium (ddrescue)
ptforensicimaging PHOTORECOVERY-2025-01-26-001 /dev/sdb ddrescue --analyst "Jméno Analytika" --json-out ${CASE_ID}_imaging.json
```

Skript provede potvrzení write-blockeru, kontrolu předpokladů a následně automaticky provede vytvoření obrazu a vytvoří kanonický soubor s hashem.

**5. Provedení vytvoření obrazu:**

**Pro READABLE médium – dc3dd:**

dc3dd používá minimalistickou syntaxi (nepodporuje parametry `bs=` ani `progress=`):
```bash
dc3dd if=/dev/sdX \
      of=/var/forensics/images/CASE-ID.dd \
      hash=sha256 \
      log=/var/forensics/images/CASE-ID_imaging.log
```

dc3dd automaticky zobrazuje průběh a vypíše SHA-256 hash do konzole i do log souboru. Hash (64 hexadecimálních znaků) se zaznamenává jako `source_hash`. Hash se počítá během kopírování – jeden průchod médiem, žádné dodatečné čtení.

**Pro PARTIAL médium – ddrescue:**
```bash
ddrescue -f -v \
    /dev/sdX \
    /var/forensics/images/CASE-ID.dd \
    /var/forensics/images/CASE-ID.mapfile
```

ddrescue použije strategii minimalizace zátěže média – čte zdravé oblasti nejprve, problematické sektory opakovaně s menšími bloky. Vytvoří mapfile, který zaznamenává pozice chybných sektorů. Po dokončení se vypočítá SHA-256 hash:
```bash
sha256sum /var/forensics/images/CASE-ID.dd
```

Výstup ddrescue se automaticky zapisuje do log souboru spolu s příkazem, časovými razítky a exit kódem.

**6. Vytvoření kanonického souboru s hashem:**

Skript automaticky vytvoří `.sha256` soubor ve formátu kompatibilním s `sha256sum -c`. Formát je: `HASH  FILENAME` (dvě mezery mezi hashem a názvem souboru).

Ověření integrity obrazu:
```bash
sha256sum -c CASE-ID.dd.sha256
```

**7. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` skript vytvoří JSON s forenzními metadaty. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `forensicImaging`:
```json
"forensicImaging": {
  "version": "1.0.0",
  "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
  "caseId": "PHOTORECOVERY-2025-01-26-001",
  "timestamp": "2025-01-26T12:00:00Z",
  "analyst": "Jméno Analytika",
  "source": {
    "devicePath": "/dev/sdb",
    "mediaStatus": "READABLE",
    "sizeBytes": 32017047552
  },
  "acquisition": {
    "tool": "dc3dd",
    "toolVersion": "7.2.646",
    "method": "single-pass with integrated hashing",
    "durationSeconds": 1847.5,
    "averageSpeedMBps": 16.5
  },
  "output": {
    "imagePath": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001.dd",
    "imageFormat": "raw (.dd)",
    "imageSizeBytes": 32017047552,
    "imagingLog": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001_imaging.log",
    "hashFile": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001.dd.sha256"
  },
  "integrity": {
    "writeBlockerConfirmed": true,
    "errorSectors": 0,
    "hashAlgorithm": "SHA-256",
    "sourceHash": "a3f5e8c9d2b1a7f4e6c8d9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2",
    "verified": true
  }
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T12:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Forenzní vytvoření obrazu dokončeno – nástroj: dc3dd, výsledek: SUCCESS",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**8. Archivace výstupů:**

Vytvořené soubory:
- `{CASE-ID}.dd` – forenzní obraz (raw formát, bitová kopie)
- `{CASE-ID}.dd.sha256` – kanonický soubor s hashem pro ověření
- `{CASE-ID}_imaging.log` – detailní log procesu (časová razítka, rychlost, chyby)
- `{CASE-ID}.mapfile` – pouze pro ddrescue (mapa zdravých/chybných oblastí)

Archivujte tyto soubory do dokumentace případu.

## Výsledek

Forenzní obraz vytvořen ve formátu `.dd`. SHA-256 `source_hash` vypočítán a zaznamenán. Kanonický soubor s hashem vytvořen pro ověření. JSON v souladu se standardy vygenerován s metadaty souladu. Záznamy připravené na integraci do dokumentace. Originální médium zůstává neporušené.

Pracovní postup pokračuje do kroku Kontrola hash – ověření integrity obrazu.

## Reference

ISO/IEC 27037:2012 – Section 5.4.4 (Acquisition of digital evidence)

NIST SP 800-86 – Section 3.1.2 (Acquiring the Data)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 1 (No action taken should change data) & Principle 2 (Competence of persons accessing original data)

NIST FIPS 180-4 – Secure Hash Standard (SHA-256 specification)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)