# Detaily testu

## Úkol
Identifikovat médium a vytvořit fotodokumentaci.

## Obtížnost
Jednoduchá

## Časová náročnost
15 minut

## Automatický test
Ne

## Popis
Fyzická identifikace média je prvním krokem před jakýmkoli kontaktem zařízení s laboratorním vybavením. Zaznamenané fyzické identifikátory – výrobce, model a sériové číslo – tvoří základ pro právně použitelný záznam řetězce důkazů v souladu s ISO/IEC 27037:2012. Všechny výstupy tohoto kroku doplňují JSON záznam případu vytvořený v kroku Přijetí žádosti a jsou navázány na příslušný identifikátor případu.

## Jak na to

**1. Předběžné informace od klienta:**
Zaznamenejte do dokumentace základní informace podle toho, co klient uvádí. Jde o předběžný záznam, který bude v následujících krocích potvrzen nebo korigován fyzickým ověřením:
- **Typ zařízení** – SD karta / microSD / USB flash disk / HDD / SSD / jiné
- **Odhadovaná kapacita** – podle vyjádření klienta
- **Viditelné poškození** – popis nebo žádné

**2. Fotodokumentace:**
Pořiďte komplexní fotodokumentaci média – minimálně 8 záběrů:
- Celkový záběr s měřítkem
- Šest stran zařízení: vrch, spodek, přední strana, zadní strana, levá, pravá
- Makro detail sériového čísla
- Detail každého viditelného poškození nebo anomálie

Fotografie pojmenujte podle schématu `PHOTORECOVERY-2025-01-26-001_photo_01.jpg` atd. a uložte je do adresáře dokumentace případu. Zaznamenejte celkový počet fotografií a potvrďte archivaci v dokumentaci.

**3. Fyzické identifikátory:**
Zaznamenejte ověřené fyzické parametry zařízení přímo z fyzické nálepky a těla zařízení:
- **Výrobce**, **Model**, **Sériové číslo** (úplné)
- **Barva / materiál**
- **Délka (mm)**, **Šířka (mm)**, **Výška (mm)**
- **Kapacita (nálepka)**

Pokud sériové číslo není čitelné (poškozená nebo chybějící nálepka), zaznamenejte hodnotu `"N/A – neidentifikovatelné"` a zdokumentujte důvod. Typ zařízení určuje, které diagnostické nástroje budou relevantní v kroku Kontrola čitelnosti média.

**4. Fyzický stav média:**
Zapište **Stav zařízení** (nové / mírně použité / intenzivně použité / poškozené) a zaznamenejte viditelné stopy používání – škrábance, znečištění, změny barvy, stav nálepek.

**5. Fyzické poškození:**
Pokud je poškození přítomné, zaznamenejte v dokumentaci:
- **Typ poškození** – prasklina pouzdra / zlomený konektor / deformace / koroze kontaktů
- **Lokalizace poškození** – přesné místo na zařízení
- **Závažnost poškození:**
  - Malé – kosmetické, funkčnost neovlivněna
  - Střední – částečně funkční, vyžaduje opravu
  - Kritické – znemožňuje připojení

**6. Viditelné indikátory šifrování:**
Zkontrolujte, zda médium nenese viditelné znaky šifrování – štítek BitLocker od výrobce, nálepka bootloaderu VeraCrypt nebo firemní bezpečnostní štítek. Pokud jsou přítomny, zaznamenejte to v dokumentaci a informujte klienta, že obnovovací klíč nebo heslo bude nezbytné. Technické ověření šifrování proběhne v kroku Kontrola čitelnosti média.

**7. Fyzické označení:**
Nalepte štítek s identifikátorem případu na médium – ne na konektor, ne přes sériové číslo, ne přes původní výrobní nálepky. Potvrďte nalepení v dokumentaci.

**8. Aktualizace záznamu případu:**
Doplňte existující JSON záznam případu o objekt `mediaIdentification` a přidejte druhý záznam do pole `chainOfCustody`. Fyzické detaily (přesné rozměry, lokalizace poškození, seznam názvů fotografií) zůstávají v identifikačním formuláři – do JSON patří pouze identifikační pole potřebná pro řetězec nástrojů a propojení kroků.

Přidávaná pole:
```json
"mediaIdentification": {
  "manufacturer": "SanDisk",
  "model": "Ultra microSDXC",
  "serialNumber": "SN-XXXXXXXX",
  "declaredCapacity": "64 GB",
  "deviceType": "microSD",
  "physicalCondition": "mírně použité",
  "damagePresent": false,
  "encryptionIndicators": false,
  "photoCount": 8,
  "photoArchivePath": "cases/PHOTORECOVERY-2025-01-26-001/photos/"
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T09:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Fyzická identifikace média a fotodokumentace dokončena",
  "mediaSerial": "SN-XXXXXXXX"
}
```

Zkontrolujte, že pole `mediaIdentification` obsahuje všechna povinná pole, a potvrďte krok v dokumentaci.

## Výsledek
Médium je identifikované a zdokumentované. Vytvořené výstupy:
- Fotodokumentace (minimálně 8 fotografií) archivovaná pod identifikátorem případu
- Identifikační formulář s kompletními fyzickými parametry
- Fyzický štítek s identifikátorem případu nalepený na médium
- Pole `mediaIdentification` doplněno do JSON záznamu případu
- Druhý záznam `chainOfCustody` s `mediaSerial` zapsán do záznamu případu

## Reference

ISO/IEC 27037:2012 – Section 5.4.2 (Identification of digital evidence) & Section 6.1 (Chain of custody)

NIST SP 800-86 – Section 3.1.1 (Identifying Possible Sources of Data – including documentation requirements)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 3 (An audit trail or other record of all processes applied to digital evidence should be created and preserved)

## Stav
K otestování

## Nález
(prázdné – vyplní se po testu)