# Detaily testu

## Úkol

Vypočítat SHA-256 hash vytvořeného forenzního obrazu a porovnat se source_hash.

## Obtížnost

Jednoduchá

## Časová náročnost

45 minut

## Automatický test

Ano

## Popis

Krok Vytvoření obrazu vypočítal `source_hash` přímo z originálního média během kopírování. Ověření integrity vypočítá `image_hash` ze souboru forenzního obrazu a oba hashe porovná. Shoda matematicky dokazuje, že soubor obrazu je bit po bitu identický s daty přečtenými z originálního média – během kopírování nedošlo k žádné změně ani chybě.

## Jak na to

**1. Přečtení source_hash z dokumentace:**

Z výstupu kroku Vytvoření obrazu si zapište hodnotu `source_hash` (64 hexadecimálních znaků). Typicky se nachází v:
- Terminálovém výstupu z `dc3dd` nebo `ddrescue`
- Souboru `{CASE-ID}_imaging.log` (log vytvoření obrazu)
- JSON souboru (pokud byl použit `--json-out`)
- Kanonickém souboru s hashem `{CASE-ID}.dd.sha256`

Příklad:
```
source_hash: a3f5e8c9d2b1a7f4e6c8d9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2
```

**2. Spuštění ověření:**

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
IMAGE="/var/forensics/images/${CASE_ID}.dd"
SOURCE_HASH="a3f5e8c9d2b1a7f4e6c8d9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2"

# Pouze terminálový výstup
ptimageverification ${CASE_ID} ${IMAGE} ${SOURCE_HASH} --analyst "Jméno Analytika"

# S JSON výstupem
ptimageverification ${CASE_ID} ${IMAGE} ${SOURCE_HASH} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_verification.json
```

Nástroj automaticky ověří formát source_hash, vypočítá image_hash, porovná oba hashe, vytvoří kanonický soubor s hashem `.sha256` a aktualizuje řetězec důkazů.

**3. Podporované formáty obrazů:**

Nástroj podporuje formáty `.dd` a `.raw` přímým výpočtem SHA-256 a také formát `.e01` prostřednictvím `ewfverify`. Průběh se zobrazuje každých 1 GB s aktuální rychlostí čtení.

Pokud automatický nástroj není dostupný, vypočítejte `image_hash` manuálně:
```bash
sha256sum /var/forensics/images/PHOTORECOVERY-2025-01-26-001.dd
```
Výstup porovnejte se `source_hash` z imaging logu znak po znaku. Při shodě pokračujte, při neshodě opakujte vytvoření obrazu.

**4. Porovnání hashů:**

Nástroj porovná `source_hash` a `image_hash` znak po znaku:

**SHODA** – všech 64 znaků se shoduje. Obraz je bit po bitu identický se zdrojovým médiem. Pracovní postup pokračuje do kroku CoC brána.

**NESHODA** – hashe se neshodují. Možné příčiny: I/O chyba během vytváření obrazu, porušení souboru na disku, modifikace obrazu po vytvoření, degradace média během vytváření obrazu. Krok Vytvoření obrazu musí být zopakován, s obrazem se nesmí dále pracovat.

**5. Vytvoření kanonického souboru s hashem:**

Nástroj automaticky vytvoří `.sha256` soubor ve formátu kompatibilním s `sha256sum -c`:
```
{CASE-ID}.dd.sha256
```

Formát: `HASH  FILENAME` (dvě mezery mezi hashem a názvem souboru).

Manuální ověření integrity obrazu kdykoli později:
```bash
sha256sum -c /var/forensics/images/PHOTORECOVERY-2025-01-26-001.dd.sha256
```

Výstup by měl být: `PHOTORECOVERY-2025-01-26-001.dd: OK`

**6. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` se vytvoří JSON s forenzními metadaty. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `hashVerification`:
```json
"hashVerification": {
  "version": "1.0.0",
  "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
  "caseId": "PHOTORECOVERY-2025-01-26-001",
  "timestamp": "2025-01-26T13:00:00Z",
  "analyst": "Jméno Analytika",
  "image": {
    "imagePath": "/var/forensics/images/PHOTORECOVERY-2025-01-26-001.dd",
    "imageFormat": ".dd",
    "imageSizeBytes": 32017047552
  },
  "verification": {
    "algorithm": "SHA-256",
    "sourceHash": "a3f5e8c9d2b1a7f4e6c8d9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2",
    "imageHash": "a3f5e8c9d2b1a7f4e6c8d9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2",
    "hashMatch": true,
    "verificationStatus": "VERIFIED",
    "calculationTimeSeconds": 1847.5
  }
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T13:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Ověření integrity obrazu – výsledek: VERIFIED",
  "mediaSerial": "SN-XXXXXXXX"
}
```

## Výsledek

SHA-256 `image_hash` vypočítán a porovnán se `source_hash`. Při SHODĚ pracovní postup pokračuje do kroku CoC brána. Při NESHODĚ analýza zastavena a vytvoření forenzního obrazu se opakuje. Kanonický soubor s hashem `.sha256` vytvořen pro budoucí ověření.

## Reference

NIST SP 800-86 – Section 3.1.2 (Acquiring the Data – integrity verification)

ISO/IEC 27037:2012 – Section 5.4.4 (Acquisition) & Section 5.3.3 (Repeatability)

NIST FIPS 180-4 – Secure Hash Standard (SHA-256 algorithm)

RFC 6234 – US Secure Hash Algorithms (SHA and HMAC-SHA)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)