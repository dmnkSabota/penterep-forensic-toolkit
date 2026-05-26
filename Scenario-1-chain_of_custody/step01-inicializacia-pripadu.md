# Detaily testu

## Úkol

Inicializovat případ, vytvořit identifikátor případu a zaznamenat kontextové informace z místa zajištění.

## Obtížnost

Jednoduchá

## Časová náročnost

20 minut

## Automatický test

Ne

## Popis

První krok forenzního procesu zajištění digitálních důkazů spojuje administrativní inicializaci případu se zaznamenáním operativních informací z místa zajištění. Analytik vytvoří jedinečný identifikátor případu, zaznamená kontextové informace a inicializuje záznam řetězce důkazů v souladu s ISO/IEC 27037:2012. Identifikátor případu slouží jako primární klíč pro všechny dokumenty, soubory, hashe a fyzické štítky v průběhu celého procesu.

Krok funguje stejně na místě zajištění (domovní prohlídka, zadržení) i při příjmu kurýrsky doručeného média v laboratoři. Při laboratorním příjmu se kontextové informace přebírají z dodacího listu nebo klientské dokumentace.

## Jak na to

**1. Vytvoření identifikátoru případu:**

Vytvořte identifikátor případu podle formátu `COC-RRRR-MM-DD-XXX` a vyplňte jej do formuláře scénáře:
- `COC` – pevná předpona identifikující typ scénáře
- `RRRR-MM-DD` – aktuální datum (rok-měsíc-den), například `2025-01-26`
- `XXX` – trojciferné pořadové číslo případu v daný den, začíná od `001`

Příklad prvního případu dne 26. ledna 2025: `COC-2025-01-26-001`

Zkontrolujte archiv existujících případů a ověřte, že toto ID ještě nebylo použito.

**2. Základní údaje případu:**

Zaznamenejte identifikační a organizační informace analytika:
- Jméno a číslo odznaku analytika
- Pracoviště a laboratoř
- Právní základ zajištění: domovní prohlídka §83 TŘ / příkaz k prohlídce jiných prostor §83a TŘ / zajištění věci §78 TŘ / dobrovolné předání / komerční příjem
- Referenční číslo vyšetřovacího spisu (je-li dostupné)

**3. Záznam kontextu zajištění:**

Při zajištění na místě zaznamenejte:
- Přesnou adresu a místo (místnost, nábytek, poloha zařízení)
- Jména a funkce všech přítomných osob
- Stav zařízení při nálezu (zapnuté / vypnuté / pohotovostní režim / nabíjení)
- Okolnosti zajištění a případná vyjádření vlastníka

Při laboratorním příjmu zaznamenejte:
- Odesílatele a referenci na klientskou dokumentaci nebo dodací list
- Datum a čas příjmu
- Stav obalu při převzetí (neporušený / poškozený / bez obalu)

**4. Inicializace záznamu případu:**

Vytvořte JSON záznam případu se stavem `INITIATED` a prvním záznamem `chainOfCustody`. Uložte jej do dokumentace případu pod příslušným identifikátorem případu.

```json
{
  "caseId": "COC-2025-01-26-001",
  "status": "INITIATED",
  "legalBasis": "§83 TŘ – domovní prohlídka",
  "analyst": "Jméno Analytika",
  "chainOfCustody": [
    {
      "timestamp": "2025-01-26T09:00:00Z",
      "analyst": "Jméno Analytika",
      "action": "Případ inicializován, záznam kontextu zajištění vytvořen"
    }
  ]
}
```

**5. Finalizace:**

Zkontrolujte, že záznam případu obsahuje všechna povinná pole: `caseId`, `status`, `legalBasis`, první záznam v poli `chainOfCustody`. Vytiskněte příjmový lístek s identifikátorem případu pro fyzickou evidenci.

## Výsledek

Po dokončení kroku existují tyto výstupy:
- Záznam případu (JSON) se stavem `INITIATED` a prvním záznamem `chainOfCustody` uložený v dokumentaci
- Příjmový lístek s identifikátorem případu vytištěný pro fyzickou evidenci

## Reference

ISO/IEC 27037:2012 – Section 5.4.2 (Identification) & Section 6.1 (Chain of custody)

NIST SP 800-86 – Section 3.1 (Data Collection)

ACPO Good Practice Guide for Digital Evidence v5 (2011/2012) – Principle 3 (An audit trail or other record of all processes applied to digital evidence should be created and preserved)

Zákon č. 141/1961 Sb. (Trestní řád) – §78 (Povinnost k předložení nebo vydání věci), §83 (Příkaz k domovní prohlídce), §83a (Příkaz k prohlídce jiných prostor a pozemků)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)