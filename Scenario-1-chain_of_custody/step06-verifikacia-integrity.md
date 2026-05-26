# Detaily testu

## Úkol

Vypočítat SHA-256 hash forenzního obrazu a porovnat s hashem originálního zařízení pro matematické ověření integrity.

## Obtížnost

Jednoduchá

## Časová náročnost

30–120 minut

## Automatický test

Ano

## Popis

Krok Forenzní imaging vypočítal `source_hash` přímo z originálního média během kopírování. Verifikace integrity vypočítá `image_hash` ze souboru forenzního obrazu na disku a oba hashe porovná. Shoda matematicky dokazuje, že obraz je bit po bitu identický s daty přečtenými z originálního média. Při neshodě se vytvoření obrazu opakuje s diagnostikou příčiny – maximálně třikrát. Po překročení limitu se případ eskaluje se stavem `CRITICAL_HASH_MISMATCH`.

## Jak na to

**1. Načtení source_hash:**

Hash načtěte z průvodního `.sha256` souboru, který vytvořil předchozí krok – jde o kanonický forenzní formát kompatibilní s nástrojem `sha256sum -c`:

```bash
CASE_ID="COC-2025-01-26-001"
IMAGE="/var/forensics/images/${CASE_ID}.dd"
SOURCE_HASH=$(awk '{print $1}' "${IMAGE}.sha256")
echo "Hash: $SOURCE_HASH"
```

**2. Spuštění ověření:**

```bash
# Pouze terminálový výstup
ptimageverification ${CASE_ID} ${IMAGE} ${SOURCE_HASH} --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptimageverification ${CASE_ID} ${IMAGE} ${SOURCE_HASH} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_verification.json
```

Nástroj ověří formát `source_hash`, vypočítá `image_hash` v 4 MB blocích s průběžným zobrazováním postupu a porovná obě hodnoty.

**3. Výsledek SHODA:**

Všech 64 znaků hashů se shoduje. Obraz je bit po bitu identický se zdrojovým médiem. Originální médium lze bezpečně odpojit od write-blockeru. Pracovní postup pokračuje do dokumentace řetězce důkazů a fyzického zabezpečení důkazu.

**4. Výsledek NESHODA:**

Hashe se neshodují. Proveďte diagnostiku před opakováním vytváření obrazu:

```bash
# I/O chyby jádra
dmesg | grep -i error | tail -50

# Dostupné místo
df -h /var/forensics/images

# Velikost obrazu
ls -lh ${CASE_ID}.dd
```

Zkontrolujte fyzický stav kabelů a write-blockeru (LED indikátor). Odstraňte neplatný obraz:

```bash
shred -u ${CASE_ID}.dd
```

Zaznamenejte zjištěnou příčinu do dokumentace a opakujte vytvoření forenzního obrazu. Po třetím neúspěšném pokusu nastavte stav případu na `CRITICAL_HASH_MISMATCH` a eskalujte nadřízenému.

**5. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` skript vytvoří JSON s výsledkem ověření. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `imageVerification`:

```json
"imageVerification": {
  "version": "1.0.0",
  "compliance": ["NIST SP 800-86", "ISO/IEC 27037:2012"],
  "caseId": "COC-2025-01-26-001",
  "timestamp": "2025-01-26T12:30:00Z",
  "analyst": "Jméno Analytika",
  "sourceHash": "a3f5e8c9d2b1a7f4e6c8d9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2",
  "imageHash":  "a3f5e8c9d2b1a7f4e6c8d9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2",
  "verificationStatus": "VERIFIED",
  "hashMatch": true
}
```

Nový záznam do pole `chainOfCustody`:

```json
{
  "timestamp": "2025-01-26T12:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Ověření hashe dokončeno – výsledek: VERIFIED, image_hash shodný se source_hash"
}
```

## Výsledek

SHODA: `image_hash` shodný se `source_hash`, obraz ověřen. Kanonický průvodní `.sha256` soubor potvrzen. Originální médium odpojeno od write-blockeru.

NESHODA: Diagnostika provedena a zdokumentována, vytvoření forenzního obrazu se opakuje. Při třetím selhání případ eskalován se stavem `CRITICAL_HASH_MISMATCH`.

Pracovní postup pokračuje do kroku CoC brána a uložení – dokumentace řetězce důkazů a fyzického zabezpečení důkazu.

## Reference

ISO/IEC 27037:2012 – Section 5.4.4 (Acquisition) & Section 5.3.3 (Repeatability)

NIST SP 800-86 – Section 3.1.2 (Acquiring the Data)

NIST FIPS 180-4 – Secure Hash Standard (SHA-256 algorithm)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)