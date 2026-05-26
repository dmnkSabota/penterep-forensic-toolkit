# Detaily testu

## Úkol

Provést bránové ověření hashů, fyzicky označit zařízení bezpečnostním (tamper-evident) štítkem a uložit ho do zabezpečené úschovny.

## Obtížnost

Jednoduchá

## Časová náročnost

30 minut

## Automatický test

Ano 

## Popis

Tento krok kombinuje **automatizované bránové ověření** (`ptcocmanager --mode gate`) s **fyzickými laboratorními úkony** (vyplnění formuláře, označení štítkem, uložení). Brána neopakuje ověření integrity samotného obrazu – to již provedl předchozí krok Verifikace integrity. Místo toho načítá JSON zprávy z kroků Kontrola čitelnosti, Forenzní imaging a Verifikace integrity a křížově porovná dvě klíčové hodnoty: zda se `sourceHash` ve zprávě z kroku Forenzní imaging shoduje se `sourceHash` ve zprávě z kroku Verifikace integrity a zda `verificationStatus` zní `VERIFIED`. Cílem je zachytit nesrovnalosti způsobené opakovaným spuštěním nástrojů nebo nesprávným ručním kopírováním údajů **před** provedením nezvratných fyzických úkonů s originálním médiem. Pokud brána selže, fyzické úkony se neprovádějí a pracovní postup se vrací do kroku Forenzní imaging.

Konečnou konsolidaci všech zpráv a generování hlavního dokumentu řetězce důkazů provede poslední krok Export a předání. Tento krok je pouze **brána a fyzická akce**, nikoli konečná konsolidace.

## Jak na to

**1. Spuštění bránového ověření:**

Skript automaticky detekuje scénář z předpony `COC-*` a automaticky vyhledá JSON zprávy ve výchozím výstupním adresáři:

```bash
CASE_ID="COC-2025-01-26-001"

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
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_coc_gate.json
```

**2. Výsledek brány:**

Při **PASS** (exit kód 0): pokračujte fyzickými úkony popsanými níže.

Při **FAIL** (exit kód 1): **NEPROVÁDĚJTE fyzické úkony**. Vraťte se do kroku Forenzní imaging nebo Verifikace integrity, vyřešte neshodu hashů a zopakujte bránu. Fyzické označení a uložení média se provádí pouze tehdy, pokud je matematicky prokázáno, že obraz je platný.

**3. Vyplnění formuláře řetězce důkazů (po PASS):**

Vytiskněte formulář řetězce důkazů obsahující:
- **Identifikační sekce:** identifikátor případu, datum příjmu, místo zajištění, jméno analytika, právní základ
- **Popis zařízení:** typ, výrobce, model, sériové číslo, stav při zajištění
- **Kryptografické identifikátory:** `source_hash`, `image_hash`, výsledek ověření (VERIFIED), výsledek křížového ověření bránou
- **Technická dokumentace:** nástroj a verze, datum a čas vytvoření obrazu, potvrzený write-blocker, výsledek čitelnosti média (typ, model a sériové číslo write-blockeru se zaznamenávají manuálně)

Vizuálně ověřte hodnoty hashů z `${CASE_ID}_coc_gate.json` – porovnejte posledních 8 znaků s fyzickými zápisky z kroku Forenzní imaging. Podepište formulář řetězce důkazů s datem a časem.

**4. Fyzické označení zařízení:**

Fotodokumentace v tomto kroku se liší od fotografií z kroku Identifikace zařízení – zachycuje aplikovaný bezpečnostní štítek před uložením do úschovny, nikoli původní stav zařízení.

Vytiskněte bezpečnostní (tamper-evident) štítek obsahující: identifikátor případu, datum označení, jméno a podpis analytika. Nalepte štítek podle pravidel:
- Nesmí zakrývat sériové číslo ani identifikační štítky výrobce
- Nesmí být na konektorech ani pohyblivých částech
- Musí být viditelný bez nutnosti demontáže

Pro malá zařízení (USB, SD karta) použijte štítek na ochranném antistatickém sáčku. Vyfotografujte zařízení s viditelným štítkem z minimálně tří úhlů:

```
COC-2025-01-26-001_label_01.jpg
COC-2025-01-26-001_label_02.jpg
COC-2025-01-26-001_label_03.jpg
```

**5. Uložení do úschovny:**

Vložte zařízení do antistatického sáčku a zatavte ho – elektrostatický výboj může poškodit flash paměti a pevné disky. Na vnější stranu nalepte identifikační štítek s identifikátorem případu. Ověřte podmínky prostředí v úschovně: teplota 15 – 25 °C, vlhkost 40 – 60 %. Zaznamenejte přesné místo uložení (místnost, regál, polička) do registru úschovny.

**6. Aktualizace záznamu případu:**

Skript zapíše do `${CASE_ID}_coc_gate.json` záznam o ověření. Analytik manuálně přidá do `case.json` záznam o fyzických úkonech (skript neví, kdy byl formulář podepsán a štítek aplikován):

```json
{
  "timestamp": "2025-01-26T13:00:00Z",
  "analyst": "Jméno Analytika",
  "action": "Brána řetězce důkazů PASS, formulář podepsán, zařízení označené (3 fotografie), uložené – místo: Místnost B03, Regál 4, Polička 2",
  "labelPhotos": [
    "COC-2025-01-26-001_label_01.jpg",
    "COC-2025-01-26-001_label_02.jpg",
    "COC-2025-01-26-001_label_03.jpg"
  ],
  "storageLocation": "Místnost B03, Regál 4, Polička 2"
}
```

**Poznámka:** Hlavní dokument řetězce důkazů s konsolidovanou časovou osou všech kroků a manifestem vytvoří týž nástroj `ptcocmanager` v posledním kroku (Export a předání), pouze v režimu `consolidate` namísto `gate`.

## Výsledek

Po dokončení kroku existují tyto výstupy:
- `${CASE_ID}_coc_gate.json` – JSON s výsledkem křížového ověření bránou
- Podepsaný formulář řetězce důkazů (manuálně) – kryptografické identifikátory shodné s hashi z brány
- Zařízení fyzicky označené bezpečnostním štítkem s fotodokumentací (3 záběry)
- Originální médium uložené v zabezpečené úschovně se zaznamenaným místem v `case.json`

Pracovní postup pokračuje do kroku Export a předání – exportu dokumentace a předání vyšetřovateli, kde se všechny zprávy konsolidují do hlavního dokumentu řetězce důkazů.

## Reference

ISO/IEC 27037:2012 – Section 5.4.2 (Identification), Section 6.1 (Chain of custody) & Section 6.9 (Preservation of potential digital evidence)

NIST SP 800-86 – Section 3.1 (Data Collection)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 3 (Audit trail) & Principle 4 (Overall responsibility for adherence to law and principles)

Zákon č. 141/1961 Sb. (Trestní řád) – §89 (Důkaz)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)