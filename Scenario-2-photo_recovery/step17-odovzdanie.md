# Detaily testu

## Úkol

Předat všechny výsledky klientovi, uzavřít řetězec důkazů a finalizovat případ.

## Obtížnost

Střední

## Časová náročnost

90 minut

## Automatický test

Ne

## Popis

Předání klientovi je závěrečný krok celého procesu obnovy fotografií. Zahrnuje přípravu závěrečného balíku, kontaktování klienta, samotné předání, uzavření řetězce důkazů a archivaci případu.

Fyzické předání důkazního materiálu s ověřením totožnosti, získání podpisů a uzavření řetězce důkazů jsou právní úkony vyžadující lidskou odpovědnost – není možné je nahradit softwarem.

## Jak na to

**1. Příprava závěrečného balíku:**

Zkompletujte následující soubory z dokumentace případu:

| Obsah | Zdroj |
|-------|-------|
| Obnovené fotografie | `{CASE_ID}_validation/valid/` |
| Opravené fotografie (pokud proběhla oprava) | `{CASE_ID}_repair/repaired/` |
| Závěrečná zpráva | `{CASE_ID}_final_report/FINAL_REPORT.json` + `.pdf` |
| Pokyny pro klienta | `{CASE_ID}_final_report/README.txt` |
| Kontrolní seznam | `{CASE_ID}_final_report/delivery_checklist.json` |

Ručně vytvořte `MANIFEST.json` se seznamem všech předávaných souborů a jejich kontrolními součty SHA-256 – klient jím může kdykoli ověřit integritu přijatých dat.

**2. Kontaktování klienta:**

Informujte klienta o výsledcích: počet obnovených fotografií, hodnocení kvality obnovy a dohodnutý způsob předání. Při nedostatečné odpovědi kontaktujte znovu po 3 dnech.

**3. Samotné předání:**

**Osobní předání:**
- Ověřte totožnost klienta (občanský průkaz)
- Předejte závěrečný balík i původní médium
- Vysvětlete obsah závěrečné zprávy a `README.txt`
- Získejte podpis předávacího protokolu

**Kurýrská přeprava:**
- Dvojité balení, pojištění zásilky
- Zaznamenejte číslo sledování
- Potvrďte převzetí podpisem při doručení

**Elektronické předání:**
- Zabezpečený odkaz s heslem zaslaným samostatnou cestou
- Platnost odkazu 7 dní
- Klient ověří integritu pomocí `MANIFEST.json`
- Původní médium předejte kurýrem

**4. Uzavření řetězce důkazů:**

Přidejte závěrečný záznam do `case.json`:
```json
{
  "timestamp": "2025-01-26T18:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Případ uzavřen – balík předán klientovi, původní médium vráceno, stav: CLOSED",
  "mediaSerial": "SN-XXXXXXXX"
}
```

Ověřte úplnost záznamu – nesmí existovat časové mezery bez odpovědné osoby. Nastavte stav případu na `CLOSED`.

**5. Archivace případu:**

Archivujte všechny soubory případu v souladu s platnými právními předpisy o uchovávání záznamů. Archivace zahrnuje:
- Forenzní obraz média (`{CASE_ID}.dd` + `.sha256`)
- Všechny JSON výstupy jednotlivých kroků
- Závěrečnou zprávu a podepsaný předávací protokol
- `MANIFEST.json` s kontrolními součty předaného balíku

**6. Závěrečná kontrola:**

Před uzavřením ověřte:
- Předávací protokol podepsán oběma stranami
- Původní médium vráceno klientovi
- Řetězec důkazů bez mezer, stav `CLOSED`
- Všechny soubory archivované
- `MANIFEST.json` uložen v dokumentaci případu

## Výsledek

Závěrečný balík předán klientovi. Obsah: obnovené fotografie, závěrečná technická zpráva, `README.txt` a `MANIFEST.json` s kontrolními součty SHA-256. Řetězec důkazů uzavřen se stavem `CLOSED`. Všechny soubory archivované v souladu s platnými právními předpisy.

## Reference

ISO/IEC 27037:2012 – Section 5.4.5 (Preservation) & Section 6.1 (Chain of custody)

NIST SP 800-86 – Section 3.4 (Reporting)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 4 (Overall responsibility for compliance with the principles)

GDPR (Nařízení EU 2016/679) – Článek 30 (Záznamy o činnostech zpracování)

## Stav

K otestování

## Nález

(prázdné – vyplní se po předání)