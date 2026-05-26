# Detaily testu

## Úkol

Provést bránovou validaci řetězce důkazů před spuštěním analytické fáze.

## Obtížnost

Jednoduchá

## Časová náročnost

5 minut

## Automatický test

Ano

## Popis

CoC brána je rychlá validační brána, která ověří konzistenci prvních tří zpráv pracovního postupu (čitelnost, vytvoření obrazu, ověření) **před** spuštěním časově náročných analytických kroků (Analýza souborového systému, File Carving, Validace integrity, EXIF analýza). Účelem je včas zachytit neshody v řetězci důkazů — pokud `sourceHash` z kroku Vytvoření obrazu nesedí se `sourceHash` z kroku Kontrola hash, nebo `verificationStatus` není `VERIFIED`, brána okamžitě selže a pracovní postup se zastaví.

Bez tohoto kroku by analytik mohl strávit hodiny carvingem obrazu, který je ve skutečnosti poškozený nebo nepatří k původnímu médiu. Brána ošetřuje i scénář, kde skript pro vytvoření obrazu byl omylem spuštěn dvakrát s různými výsledky.

Brána volá `ptcocmanager --mode gate`, což je stejný skript jako finální konsolidace v kroku CoC konsolidace — pouze v jiném režimu. Druhé volání (konsolidace) proběhne na konci pracovního postupu.

## Jak na to

**1. Spuštění bránové validace:**

Skript automaticky detekuje scénář z předpony `PHOTORECOVERY-*` a automaticky vyhledá JSON zprávy v `--output-dir` (výchozí `/var/forensics/images`):

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"

# Pouze terminálový výstup
ptcocmanager ${CASE_ID} --mode gate --analyst "Jméno Analytika"

# S JSON výstupem (auditní záznam brány)
ptcocmanager ${CASE_ID} --mode gate \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_coc_gate.json
```

Při umístění JSON souborů mimo výchozí adresář použijte explicitní cesty:

```bash
ptcocmanager ${CASE_ID} --mode gate \
  -i ${CASE_ID}_imaging.json \
  -v ${CASE_ID}_verification.json \
  -r ${CASE_ID}_readability.json \
  --analyst "Jméno Analytika"
```

**2. Co brána kontroluje:**

| Validace | Zdroj | Očekávání |
|-----------|-------|------------|
| `sourceHash` v imaging | `${CASE_ID}_imaging.json` | 64-znakový SHA-256 hex |
| Shoda `sourceHash` | imaging vs verification JSON | identické hodnoty |
| `verificationStatus` | verification JSON | `VERIFIED` |
| `hashMatch` | verification JSON | `true` |
| `mediaStatus` | readability JSON | `READABLE` nebo `PARTIAL` |

**3. Výsledek PASS:**

Skript vrátí exit kód `0` a vypíše:
```
✓ Gate PASSED - safe to proceed with analysis phase
```
Pracovní postup pokračuje do kroku Analýza souborového systému.

**4. Výsledek FAIL:**

Skript vrátí exit kód `1` a vypíše:
```
⚠ Gate FAILED - do not proceed with analysis phase
```

Diagnostika:
- Zkontrolujte hodnoty hashů v obou JSON souborech:
  ```bash
  jq '.results.properties.sourceHash' ${CASE_ID}_imaging.json
  jq '.results.properties.sourceHash' ${CASE_ID}_verification.json
  jq '.results.properties.verificationStatus' ${CASE_ID}_verification.json
  ```
- Pokud hashe nesedí, vraťte se do kroku Vytvoření obrazu a zopakujte vytvoření obrazu – původní obraz je neplatný.
- Pokud `verificationStatus` není `VERIFIED`, vraťte se do kroku Kontrola hash a vyřešte neshodu.

**5. Zápis výsledků a aktualizace řetězce důkazů:**

Skript zapíše do `${CASE_ID}_coc_gate.json` auditní záznam:

```json
"crossValidation": {
  "sourceHash": "a3f5e8c9d2b1a7f4...",
  "imageHash": "a3f5e8c9d2b1a7f4...",
  "hashMatch": true,
  "verificationStatus": "VERIFIED",
  "crossValid": true
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T12:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "CoC gate [photo-recovery] - cross-validation: PASS",
  "result": "SUCCESS"
}
```

## Výsledek

PASS: Řetězec důkazů je matematicky konzistentní (`crossValidated: true`). Pracovní postup pokračuje do kroku Analýza souborového systému.

FAIL: Řetězec je porušený – pracovní postup se zastaví. Vraťte se do kroku Vytvoření obrazu nebo Kontrola hash a vyřešte problém. **Nepokračujte v analýze** na neplatném obrazu.

## Reference

NIST SP 800-86 – Section 3.1.2 (Acquiring the Data – cross-validation)

ISO/IEC 27037:2012 – Section 5.4.4 (Acquisition) & Section 6.1 (Chain of custody)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 2 (Persons accessing original data must be competent and able to give evidence explaining their actions)

NIST FIPS 180-4 – Secure Hash Standard (SHA-256 algorithm)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)