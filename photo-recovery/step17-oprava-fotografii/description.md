# Detaily testu

## Úkol

Pokúsiť sa opraviť identifikované poškodené fotografie pomocou automatizovaných techník a manuálnych metód.

## Obtiažnosť

Střední

## Časová náročnosť

45

## Automatický test

Čiastočne

## Popis

Oprava fotografií kombinuje automatizované nástroje (PIL, ImageMagick, jpeginfo) s manuálnymi technikami pre obnovenie poškodených súborov. Úspešnosť závisí od typu poškodenia: chybný header/footer (90%+ opraviteľnosť), invalid segment (80%), truncated file (50-70%), fragmentácia (5-15%).

Prečo je tento krok kritický:
- Maximalizácia recovery - každá opravená fotografia zvyšuje finálny počet
- Prioritizácia - rýchle opravy s vysokou úspešnosťou (header/footer) majú prednosť
- Forenzná integrita - oprava len rekonštruuje existujúce dáta, nepridáva nové
- Dokumentácia - jasné zaznamenanie použitých metód a výsledkov

Typy opravy: invalid_header (nahraď SOI marker FF D8 FF), missing_footer (pridaj EOI marker FF D9), invalid_segments (odstráň corrupt APP segmenty), truncated_file (PIL LOAD_TRUNCATED_IMAGES partial recovery).

## Jak na to

1. ANALÝZA - načítaj corrupted súbory z validation/corrupted/, analyzuj JPEG štruktúru (SOI FF D8, EOI FF D9, segmenty), diagnostikuj typ poškodenia, kategorizuj opraviteľnosť (high >80%, medium 50-80%, low <50%)
2. OPRAVA HEADER - pre invalid_header: nahraď prvé 3 bytes validným SOI (FF D8 FF), rekonštruuj JFIF APP0 segment, nájdi Start of Scan (FF DA), zlepi validný header + image data, validuj PIL verify(), úspešnosť 90-95%
3. OPRAVA FOOTER - pre missing_footer: over že chýba FF D9, pridaj b'\xff\xd9', ak zlyhal nájdi posledný FF marker a obreži, validuj ImageMagick identify, úspešnosť 85-90%
4. OPRAVA SEGMENTS - parsuj segmenty, identifikuj corrupt, zachovaj kritické (SOI, SOF, DQT, DHT, SOS, EOI), odstráň poškodené APP segmenty, zrekonštruuj súbor, validuj multi-tool, úspešnosť 80-85%
5. TRUNCATED FILES - PIL LOAD_TRUNCATED_IMAGES = True, load partial image, save as complete JPEG, validuj, úspešnosť 50-70% (čiastočná fotografia)
6. VALIDÁCIA - validuj 3 nástrojmi (PIL verify() + load(), ImageMagick identify, jpeginfo -c), kategorizuj (fully_repaired, partially_repaired, failed), organizuj do repair/repaired/ a repair/failed/

---

## Výsledek

Štatistiky opravy: počet pokusov, úspešne opravené, zlyhané, success rate (cieľ 70-80%). Breakdown by type: missing_footer (90%+), invalid_header (90%+), invalid_segments (80%+), truncated (50-70%). Final count: pred opravou X validných, po oprave Y validných, improvement +Z percentage points. Validácia: všetky opravené multi-tool validated. Organizácia: repair/repaired/ (ready for cataloging), repair/failed/ (unrepairable), repair_report.json s detailami každej opravy.

## Reference

ISO/IEC 10918-1 - JPEG Standard (ITU-T T.81)
JFIF Specification v1.02
NIST SP 800-86 - Section 3.1.4 (Data Recovery and Repair)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)