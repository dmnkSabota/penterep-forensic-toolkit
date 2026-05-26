# Detaily testu

## Úkol

Provést fyzickou opravu poškozeného média.

## Obtížnost

Střední až vysoká

## Časová náročnost

30–180 minut

## Automatický test

Ne

## Popis

Krok je manuálny a jeho rozsah závisí od hardvérových kapacít laboratória.
K fyzické opravě přistupujeme pouze tehdy, když krok Klasifikácia čitateľnosti
klasifikuje médium jako UNREADABLE. Oprava se provádí ve třech úrovních podle
rozsahu poškození: jednoduchá (čištění kontaktů), střední (výměna konektoru)
nebo komplexní (přenos paměťového čipu – chip-off). Oprava mění fyzický stav
důkazu, proto musí být každý zásah kompletně zdokumentován v řetězci důkazů
v souladu s ISO/IEC 27037:2012. Před zahájením jakékoli opravy je povinný
písemný informovaný souhlas klienta.

## Jak na to

**1. Informovaný souhlas klienta:**

Připravte souhlasný formulář obsahující:
- Oprava může nenávratně zničit zbývající data
- Úspěch není garantován
- Klient uznává, že médium je již poškozené

Nechte podepsat před fyzickým zásahem. Fyzickou kopii formuláře uložte do dokumentace případu, naskenovanou verzi archivujte digitálně pod identifikátorem případu.

**2. Fotodokumentace před opravou (min. 3 fotografie):**

- Celkový záběr média s měřítkem
- Detail oblasti poškození (konektor, prasklina, koroze)
- Pracoviště s připraveným nářadím

Pojmenujte `CASE-ID_repair_before_01.jpg` a archivujte do dokumentace případu.

**3. Vyhodnocení a provedení opravy:**

Vyhodnoťte typ a rozsah poškození na základě vizuální inspekce z kroku Identifikace média a diagnostických testů z kroku Kontrola čitelnosti. Použijte ESD ochranu a zaznamenejte každý provedený krok do dokumentace.

Pokud diagnostika naznačuje softwarový problém místo hardwarového poškození, fyzická oprava není potřeba – pokračujte přímo do kroku Vytvoření obrazu.

Typické scénáře oprav:

| Typ poškození | Postup |
|---|---|
| Znečištěné / zoxidované kontakty | Čištění izopropylalkoholem (IPA 99 %), antistatický kartáček |
| Zlomený konektor USB / microSD | Výměna konektoru pájením – vyžaduje pájecí set |
| Prasklina plošného spoje (PCB) | Vizuální inspekce, vodivé lepidlo nebo propojovací drát |
| Poškozený NAND čip | Procedura chip-off – mimo kapacity standardní laboratoře, doporučte specialistu |

**4. Fotodokumentace po opravě (min. 3 fotografie):**

Stejné záběry jako před opravou (stejný úhel, oblast, měřítko) – umožňuje porovnání před/po.
Pojmenujte `CASE-ID_repair_after_01.jpg` a archivujte.

**5. Zápis záznamu opravy:**

Přidávaný objekt `mediaRepair`:
```json
"mediaRepair": {
  "timestamp": "2025-01-26T11:15:00Z",
  "repairType": "hardwarová",
  "repairDescription": "Stručný popis provedené opravy nebo diagnostiky",
  "consentSigned": true,
  "toolsUsed": ["seznam použitých nástrojů nebo diagnostických postupů"],
  "photosBeforeCount": 3,
  "photosAfterCount": 3,
  "photosArchived": true,
  "technician": "Jméno Technika",
  "repairSuccessful": true,
  "retestResult": "READABLE",
  "retestTimestamp": "2025-01-26T11:30:00Z",
  "notes": "Poznámky o průběhu opravy a zjištěních"
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T11:15:00Z",
  "analyst": "Jméno Analytika",
  "action": "Fyzická oprava média dokončena – typ: střední (výměna USB konektoru)",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**6. Ověření opravy – opakovaný test čitelnosti:**

Připojte opravené médium přes write-blocker a zopakujte test čitelnosti:
```bash
ptmediareadability /dev/sdX CASE-ID --analyst "Jméno Analytika" --json-out repair_verification.json
```

Výsledek zapište do `mediaRepair.retestResult` a pokračujte:
- **READABLE** nebo **PARTIAL** → krok Vytvoření obrazu
- **UNREADABLE** → Zapište neúspěšný výsledek do dokumentace. Informujte
  klienta o možnostech (specializovaná laboratoř / ukončení). Aktualizujte
  stav případu na `PHYSICAL_REPAIR_FAILED` a přidejte závěrečný záznam
  do `chainOfCustody`.

**7. Informování klienta:**

Kontaktujte klienta s výsledkem opravy. Zpráva musí obsahovat: výsledek opravy (úspěšná / neúspěšná), provedený zásah, aktuální stav média a další postup. Zaznamenejte komunikaci do dokumentace.

## Výsledek

- Fotodokumentace před/po (min. 3+3 fotografie) archivována pod identifikátorem případu
- Podepsaný souhlasný formulář archivován (fyzická + digitální kopie)
- Objekt `mediaRepair` a nový záznam `chainOfCustody` přidány do JSON dokumentace případu
- Výsledek ověřovacího testu po opravě zapsán do dokumentace

Při úspěšné opravě pracovní postup pokračuje zpět na krok Klasifikácia
čitateľnosti (opakovaný test). Při neúspěšné opravě případ ukončen
eskalačním stavem `PHYSICAL_REPAIR_FAILED`.

## Reference

ISO/IEC 27037:2012 – Section 5.4.3 (Collection) & Section 6.5 (Use reasonable care)

NIST SP 800-86 – Section 3.1.1 (Identifying Possible Sources of Data)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 2 (Persons accessing original data must be competent and able to give evidence explaining their actions)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)