# Detaily testu

## Úkol

Vytvořit bit-přesnou forenzní kopii originálního média a vypočítat SHA-256 hash originálního zařízení.

## Obtížnost

Jednoduchá

## Časová náročnost

60–240 minut

## Automatický test

Ano

## Popis

Vytvoření forenzního obrazu spočívá ve zhotovení bit-přesné kopie celého originálního média včetně aktivních souborů, smazaných dat, nealokovaného prostoru, volného místa v clusterech a metadat souborového systému. SHA-256 `source_hash` se vypočítává současně s kopírováním v jediném průchodu – nástroj dc3dd má integrovaný výpočet hashe (`hash=sha256`), čímž se médium čte právě jednou. U PARTIAL média nástroj ddrescue nejprve vytvoří obraz s maximálním úsilím o záchranu sektorů, SHA-256 se vypočítá následně.

Nástroj pro vytvoření obrazu je určen výsledkem kroku Kontrola čitelnosti: READABLE → dc3dd, PARTIAL → ddrescue.

Skript vyžaduje manuální potvrzení aktivního write-blockeru před každým spuštěním – bez potvrzení se vytváření obrazu nespustí. Pokud podmínka není splněna, nepokračujte – existuje riziko poškození důkazu. Originální médium zůstává po celou dobu připojené výhradně přes write-blocker.

## Jak na to

**1. Připojení write-blockeru:**

Fyzicky připojte write-blocker a zapojte médium přes něj – nikdy ne přímo. Ověřte, že LED indikátor svítí (PROTECTED). Identifikujte cestu k zařízení:

```bash
lsblk -d -o NAME,SIZE,TYPE,MODEL,SERIAL,TRAN
```

Dokumentujte write-blocker v záznamu řetězce důkazů: typ, model, sériové číslo, verze firmwaru.

**2. Kontrola dostupného místa:**

Ověřte, že cílové úložiště má dostatečnou kapacitu – doporučuje se minimálně 110 % kapacity média:

```bash
df -h /var/forensics/images
lsblk -d -o NAME,SIZE /dev/sdX
```

Nedostatek místa během vytváření obrazu může způsobit ztrátu důkazu – vždy počítejte s rezervou.

**3. Spuštění skriptu:**

Použijte nástroj určený krokem Kontrola čitelnosti (`dc3dd` pro READABLE, `ddrescue` pro PARTIAL):

```bash
# Pouze terminálový výstup
ptforensicimaging COC-2025-01-26-001 /dev/sdb dc3dd --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptforensicimaging COC-2025-01-26-001 /dev/sdb dc3dd \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_imaging.json

# Pro PARTIAL médium (ddrescue)
ptforensicimaging COC-2025-01-26-001 /dev/sdb ddrescue \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_imaging.json
```

Skript provede potvrzení write-blockeru (manuální výzva), kontrolu dostupného místa a následně automaticky provede vytvoření obrazu s integrovaným výpočtem hashe.

**4. Vytvoření obrazu:**

**Pro READABLE médium – dc3dd:**

dc3dd automaticky vypočítá SHA-256 hash během kopírování:

```bash
dc3dd if=/dev/sdX \
      of=/var/forensics/images/COC-2025-01-26-001.dd \
      hash=sha256 \
      log=/var/forensics/images/COC-2025-01-26-001_imaging.log
```

Hash (64 hexadecimálních znaků) se zaznamenává jako `source_hash`. Vizuálně zkontrolujte posledních 8 znaků oproti fyzickému zápisku – eliminuje chyby kopírování.

**Pro PARTIAL médium – ddrescue:**

ddrescue použije strategii minimalizace zátěže média – čte zdravé oblasti nejprve, problematické sektory opakovaně s menšími bloky:

```bash
ddrescue -f -v \
    /dev/sdX \
    /var/forensics/images/COC-2025-01-26-001.dd \
    /var/forensics/images/COC-2025-01-26-001.mapfile
```

Po dokončení se SHA-256 vypočítá samostatně:

```bash
sha256sum /var/forensics/images/COC-2025-01-26-001.dd
```

**5. Archivace výstupů:**

Vytvořené soubory:
- `COC-2025-01-26-001.dd` – forenzní obraz (nativní formát)
- `COC-2025-01-26-001.dd.sha256` – kanonický průvodní soubor s hashem
- `COC-2025-01-26-001_imaging.log` – detailní log průběhu
- `COC-2025-01-26-001.mapfile` – pouze pro ddrescue (mapa zdravých a chybných oblastí)

**6. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` skript vytvoří JSON s forenzními metadaty. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `forensicImaging`:

```json
"forensicImaging": {
  "version": "1.0.0",
  "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
  "caseId": "COC-2025-01-26-001",
  "timestamp": "2025-01-26T11:00:00Z",
  "analyst": "Jméno Analytika",
  "source": {
    "devicePath": "/dev/sdb",
    "sizeBytes": 500107862016
  },
  "acquisition": {
    "tool": "dc3dd",
    "toolVersion": "7.2.646",
    "method": "single-pass with integrated hashing",
    "durationSeconds": 3600,
    "averageSpeedMBps": 132.5
  },
  "output": {
    "imagePath": "/var/forensics/images/COC-2025-01-26-001.dd",
    "imageFormat": "raw (.dd)",
    "imageSizeBytes": 500107862016,
    "imagingLog": "/var/forensics/images/COC-2025-01-26-001_imaging.log",
    "hashFile": "/var/forensics/images/COC-2025-01-26-001.dd.sha256"
  },
  "integrity": {
    "writeBlockerConfirmed": true,
    "hashAlgorithm": "SHA-256",
    "sourceHash": "a3f5e8c9d2b1a7f4e6c8d9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2",
    "errorSectors": 0,
    "hashVerified": true
  }
}
```

Nový záznam do pole `chainOfCustody`:

```json
{
  "timestamp": "2025-01-26T12:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "Vytvoření forenzního obrazu dokončeno – nástroj: dc3dd, source_hash: a3f5e8c9...b1c2"
}
```

## Výsledek

Po dokončení kroku existují tyto výstupy:
- Forenzní obraz `COC-2025-01-26-001.dd` vytvořený
- SHA-256 `source_hash` vypočítaný a uložený v JSON zprávě i v průvodním `.sha256` souboru
- Detailní log průběhu vytváření obrazu archivován

Pracovní postup pokračuje do kroku Verifikace integrity obrazu.

## Reference

ISO/IEC 27037:2012 – Section 5.4.4 (Acquisition of digital evidence)

NIST SP 800-86 – Section 3.1.2 (Acquiring the Data)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 1 (No action taken should change data) & Principle 2 (Competence to access original data)

NIST FIPS 180-4 – Secure Hash Standard (SHA-256 specification)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)