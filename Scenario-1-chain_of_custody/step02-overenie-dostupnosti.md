# Detaily testu

## Úkol

Ověřit fyzickou dostupnost důkazu a vyřešit případ nedostupnosti.

## Obtížnost

Jednoduchá

## Časová náročnost

5–30 minut

## Automatický test

Ne

## Popis

Tento rozhodovací bod ověřuje fyzickou dostupnost zařízení nebo média určeného k forenznímu zpracování. Ověřuje se shoda zařízení s popisem v příkazu nebo dodacím listu a jeho fyzická přítomnost. Pokud důkaz není dostupný, pracovní postup se větví do alternativní cesty zahrnující dokumentaci problému a kontaktování odpovědné osoby. Po vyřešení se proces vrací k ověření dostupnosti.

## Jak na to

**Větev ANO – důkaz dostupný:**

Ověřte fyzickou přítomnost zařízení s odkazem na kontextový záznam z předchozího kroku (Inicializace případu). Zkontrolujte, že zařízení odpovídá popisu v příkazu, dodacím listu nebo klientské dokumentaci – porovnejte typ, sériové číslo a stav obalu. Potvrďte dostupnost zápisem do dokumentace a pokračujte do kroku Identifikace zařízení.

**Větev NE – důkaz nedostupný:**

**1. Dokumentace problému:**

Zaznamenejte důvod nedostupnosti:
- Zařízení nepředané / nesprávné zařízení
- Poškozené v transportu
- Přístup zamítnut
- Jiné (specifikujte)

Vyfotografujte místo, kde mělo být zařízení umístěno. Zaznamenejte čas a okolnosti zjištění do záznamu řetězce důkazů.

**2. Kontaktování odpovědné osoby:**

Identifikujte odpovědnou osobu (nadřízený důstojník, kurýrská společnost, klient). Do záznamu případu zapište čas kontaktu, jméno osoby a dohodnuté řešení.

**3. Čekání a eskalace:**

Proces se pozastaví do vyřešení. Každé opakování ověření musí být zaznamenáno v záznamu řetězce důkazů s časovou značkou. Pokud problém není vyřešitelný v rozumném čase, nastavte stav případu na `PENDING_EVIDENCE` a eskalujte nadřízenému.

```json
{
  "timestamp": "2025-01-26T09:15:00Z",
  "analyst": "Jméno Analytika",
  "action": "Fyzická dostupnost důkazu ověřena – zařízení přítomné, shoda s popisem potvrzena"
}
```

## Výsledek

Při ANO: potvrzení dostupnosti zaznamenáno v záznamu řetězce důkazů. Pracovní postup pokračuje do fyzické identifikace zařízení.

Při NE: dokumentace problému archivována, odpovědná osoba kontaktována, stav případu nastaven na `PENDING_EVIDENCE`. Pracovní postup pozastaven do vyřešení nedostupnosti.

## Reference

ISO/IEC 27037:2012 – Section 5.4.2 (Identification)

NIST SP 800-86 – Section 3.1.1 (Identifying Possible Sources of Data)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 1 (No action taken should change data which may subsequently be relied upon in court)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)