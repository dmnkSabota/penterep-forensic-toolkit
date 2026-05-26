# Detaily testu

## Úkol

Provést fyzickou identifikaci zařízení a fotodokumentaci.

## Obtížnost

Jednoduchá

## Časová náročnost

15 minut

## Automatický test

Ne

## Popis

Fyzická identifikace zařízení zajišťuje jeho jednoznačné odlišení od ostatních artefaktů a vytváří základ pro dokumentaci řetězce důkazů v souladu s ISO/IEC 27037:2012. Identifikace musí být natolik kompletní, aby umožňovala jednoznačné určení zařízení i bez jeho fyzické přítomnosti – například při soudním řízení. Všechny záznamy jsou přímo propojené s identifikátorem případu z předchozího kroku (Inicializace případu).

## Jak na to

**1. Fyzické identifikátory:**

Zaznamenejte přímo z fyzické nálepky a těla zařízení:
- Typ zařízení (notebook, desktop, telefon, tablet, externí disk, USB, SD karta)
- Výrobce, přesný model, sériové číslo
- Barva a materiál
- Pro mobilní zařízení: IMEI (`*#06#`) a MAC adresy síťových adaptérů

**2. Fotodokumentace (minimálně 8 záběrů):**

Postupujte v tomto pořadí:
- Celkový záběr s referenčním měřítkem
- Šest stran zařízení: vrch, spodek, přední strana, zadní strana, levá, pravá
- Makro detail sériového čísla a výrobních štítků
- Detail každého viditelného poškození nebo anomálie

Fotografie pojmenujte podle schématu `COC-2025-01-26-001_photo_01.jpg` a archivujte do dokumentace případu.

**3. Stav zařízení při zajištění:**

Zaznamenejte:
- Stav napájení: zapnuté / vypnuté / pohotovostní režim / nabíjení – převezměte z úvodního kroku
- Stav baterie (je-li to relevantní)
- Přítomnost externích médií: vložená SIM, SD karta, USB
- Viditelné stopy opotřebení nebo poškození

**4. Související příslušenství:**

Zaznamenejte a vyfotografujte veškeré příslušenství zajištěné spolu se zařízením: nabíječky, kabely, pouzdro, případné fyzické poznámky nebo hesla. Každá položka příslušenství musí být propojena se stejným identifikátorem případu.

**5. Aktualizace záznamu případu:**

Přidejte objekt `deviceIdentification` a nový záznam do `chainOfCustody`:

```json
"deviceIdentification": {
  "type": "notebook",
  "manufacturer": "Dell",
  "model": "Latitude 5520",
  "serialNumber": "ABCD1234",
  "color": "černá",
  "powerState": "vypnuté",
  "externalMedia": [],
  "photos": [
    "COC-2025-01-26-001_photo_01.jpg",
    "COC-2025-01-26-001_photo_02.jpg"
  ]
}
```

```json
{
  "timestamp": "2025-01-26T09:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Fyzická identifikace zařízení a fotodokumentace dokončena – SN: ABCD1234"
}
```

## Výsledek

Po dokončení kroku existují tyto výstupy:
- Identifikační formulář s kompletními fyzickými a technickými parametry zařízení
- Fotodokumentace (minimálně 8 fotografií) archivována v dokumentaci případu
- Záznam `chainOfCustody` zapsán s odkazem na sériové číslo

## Reference

ISO/IEC 27037:2012 – Section 5.4.2 (Identification of digital evidence)

NIST SP 800-86 – Section 3.1.1 (Identifying Possible Sources of Data)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 3 (An audit trail or other record of all processes applied to digital evidence should be created and preserved)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)