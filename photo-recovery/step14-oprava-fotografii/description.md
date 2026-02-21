# Detaily testu

## Úkol

Oprava identifikovaných poškodených fotografií pomocou automatizovaných techník.

## Obtiažnosť

Stredná

## Časová náročnosť

45 minút

## Automatický test

Čiastočne

## Popis

Oprava fotografií kombinuje automatizované nástroje (PIL, ImageMagick, jpeginfo) s JPEG binárnou rekonštrukciou pre obnovenie poškodených súborov. Úspešnosť závisí od typu poškodenia: chybný header/footer (90 %+), invalid_segments (80 %), truncated (50–70 %), fragmentácia (5–15 %).

Systém smeruje každý súbor k príslušnej technike podľa typu poškodenia: `missing_footer` → pridanie EOI markeru (FF D9), `invalid_header` → rekonštrukcia SOI + JFIF APP0, `corrupt_segments` → odstránenie poškodených APP segmentov pri zachovaní kritických (SOF0, DQT, DHT), `truncated` / `corrupt_data` → PIL čiastočná obnova cez `LOAD_TRUNCATED_IMAGES`. Po každej oprave prebehne trojnástrojová validácia (PIL, ImageMagick, jpeginfo).

Forenzná integrita je zachovaná: oprava len rekonštruuje existujúce dáta, nepridáva nové. Zdrojové súbory v `corrupted/` zostávajú nedotknuté – oprava pracuje na kópii.

Predpokladom je existencia `{case_id}_validation_report.json` a nainštalovaná knižnica PIL/Pillow.

## Jak na to

**1. Načítanie zoznamu opraviteľných súborov:**

Systém načíta `{case_id}_validation_report.json` a extrahuje `filesNeedingRepair` – zoznam súborov s typom poškodenia a odporúčanou technikou.

**2. Kontrola nástrojov:**

PIL/Pillow je povinný (`LOAD_TRUNCATED_IMAGES = True`). Voliteľné: `identify` (ImageMagick), `jpeginfo`.

**3. Smerovanie a oprava:**

Pre každý súbor systém vytvorí pracovnú kópiu a aplikuje príslušnú techniku. Výsledok opravy je validovaný trojicou nástrojov.

**4. Organizácia výstupov:**

Úspešne opravené súbory sa presunú do `{case_id}_repair/repaired/`, neúspešné do `failed/`. Originál v `corrupted/` zostáva nedotknutý.

**5. Report:**

Systém uloží `{case_id}_repair_report.json` a `REPAIR_REPORT.txt` so štatistikami podľa typu poškodenia a detailom každej opravy.

## Výsledek

Štatistiky: počet pokusov, úspešne opravené, zlyhané, success rate (cieľ 70–80 %). Breakdown podľa typu: missing_footer (90 %+), invalid_header (90 %+), invalid_segments (80 %+), truncated (50–70 %). Organizácia: `repair/repaired/` (ready for cataloging), `repair/failed/`. `repair_report.json` s detailom každej opravy vrátane použitej techniky a výsledku validácie.

## Reference

ISO/IEC 10918-1 – JPEG Standard (ITU-T T.81)
JFIF Specification v1.02
NIST SP 800-86 – Section 3.1.4 (Data Recovery and Repair)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

PIL `LOAD_TRUNCATED_IMAGES = True` je globálny flag – musí byť nastavený pred prvým `Image.open()`. Pri `repair_invalid_segments` sa odstraňujú APP segmenty (EXIF, XMP, ICC profil) – metadata sa stratia, pixelové dáta zostávajú. Ak je oprava potrebná spolu s EXIF analýzou, EXIF sa musí extrahovať pred opravou.