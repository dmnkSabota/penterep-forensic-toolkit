# Detaily testu

## Úkol

Extrahovať a analyzovať EXIF metadáta zo všetkých obnovených fotografií pre získanie časových značiek, informácií o fotoaparáte, nastavení, GPS súradníc a detekciu upravených fotografií.

## Obtiažnosť

Snadné

## Časová náročnosť

30

## Automatický test

Áno

## Popis

EXIF (Exchangeable Image File Format) sú metadáta embedded priamo v obrazových súboroch. Väčšina digitálnych fotoaparátov a smartfónov automaticky vkladá EXIF dáta do každej fotografie. Pri File Carving (12B) sme stratili FS timestamps, takže DateTimeOriginal je jediná spoľahlivá časová informácia.

Prečo je tento krok kritický:
- Časové informácie - DateTimeOriginal umožňuje vytvoriť presný timeline fotografií
- Identifikácia zariadenia - Make + Model + SerialNumber identifikujú konkrétny fotoaparát/telefón
- GPS lokalizácia - ak sú GPS dáta → geografická mapa kde bola fotka vytvorená
- Detekcia úprav - Software tag a rozdiel medzi DateTimeOriginal a ModifyDate indikujú úpravu
- Nastavenia fotoaparátu - ISO, clona, ohnisková vzdialenosť pre technickú analýzu
- Pri FS-based (12A) máme FS timestamps, pri File Carving (12B) len EXIF

Typické EXIF tagy: DateTimeOriginal (čas vytvorenia), Make/Model (fotoaparát), SerialNumber, ISO, FNumber (clona), ExposureTime, FocalLength, GPSLatitude/GPSLongitude, Software (editing).

## Jak na to

1. EXTRAKCIA - načítaj master_catalog.json z Kroku 13, spusti `exiftool -j -G -a -s -n` na každý súbor, parsuj JSON output s EXIF dátami
2. ANALÝZA ČASU - pre každú fotografiu: načítaj DateTimeOriginal/CreateDate, zisti časové rozpätie (earliest→latest), deteknuj fotky bez časových tagov, deteknuj ModifyDate > DateTimeOriginal (upravené)
3. ANALÝZA FOTOAPARÁTOV - zisti unikátne kombinácie Make+Model, zisti unikátne sériové čísla, vytvor distribúciu (top 5 fotoaparátov), identifikuj či sú fotky z viacerých zariadení
4. NASTAVENIA A GPS - analyzuj rozsah ISO/clona/ohnisková vzdialenosť (min/max/avg), spočítaj fotky s GPS súradnicami, vytvor GPS zoznam pre mapu
5. DETEKCIA ÚPRAV - deteknuj Software tag (Photoshop, Lightroom, GIMP, Instagram), deteknuj anomálie (chýbajúce EXIF, budúce dátumy, neobvyklé ISO), klasifikuj kvalitu EXIF dát
6. TIMELINE A REPORT - vytvor timeline (fotky zoskupené podľa dátumu), vygeneruj štatistiky, vytvor JSON databázu a CSV pre Excel, vytvor textový report

---

## Výsledek

Komplexná databáza EXIF metadát (JSON + CSV). Štatistiky: % fotografií s DateTimeOriginal (cieľ >90%), časové rozpätie (dni), počet unikátnych fotoaparátov, rozsah nastavení (ISO, clona), % fotografií s GPS, % upravených fotografií. EXIF quality score: excellent (>90% DateTimeOriginal), good (70-90%), fair (50-70%), poor (<50%). Timeline organized by date. GPS coordinates list (if available). Interpretácia: vysoké % DateTimeOriginal = úspešná obnova, viacero fotoaparátov = normálne, GPS len na niektorých = smartphone vs fotoaparát.

## Reference

EXIF 2.32 Specification (CIPA DC-008-2019)
ISO 12234-2:2001 - Electronic still-picture imaging
ExifTool Documentation

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)