# Detaily testu

## Úkol

Extrahovať a analyzovať EXIF metadáta zo všetkých obnovených fotografií.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

30 minút

## Automatický test

Áno

## Popis

EXIF (Exchangeable Image File Format) sú metadáta embedded priamo v obrazových súboroch. Každý digitálny fotoaparát a smartfón ich automaticky vkladá pri vytváraní fotografie. Pre súbory obnovené cez file carving sú EXIF dáta jediným spoľahlivým zdrojom časových informácií, keďže FS timestamps sa pri carvingu strácajú.

Systém extrahuje EXIF v dávkach pomocou `exiftool -j -G -a -s -n`, analyzuje kľúčové polia (DateTimeOriginal, Make/Model, SerialNumber, ISO, FNumber, GPS) a detekuje upravené fotografie podľa Software tagu a rozdielu medzi DateTimeOriginal a ModifyDate. Výsledkom je EXIF quality score (excellent/good/fair/poor) podľa percenta súborov s DateTimeOriginal, časová os fotografií, zoznam GPS súradníc a CSV export pre ďalšie spracovanie.

Predpokladom je existencia `master_catalog.json` vytvoreného počas konsolidácie.

## Jak na to

**1. Načítanie master katalógu:**

Systém načíta `{case_id}_consolidated/master_catalog.json` a získa zoznam všetkých konsolidovaných súborov.

**2. Dávková extrakcia EXIF:**

Pre každú dávku 50 súborov systém spustí `exiftool -j -G -a -s -n`. Súbory s aspoň jedným zmysluplným poľom (DateTimeOriginal, Make, ISO, GPS, Software) sa považujú za EXIF-pozitívne.

**3. Analýza času a zariadení:**

Systém parsuje DateTimeOriginal, buduje časovú os (fotky zoskupené podľa dátumu) a počíta unikátne kombinácie Make+Model.

**4. GPS a nastavenia:**

Pre každý záznam systém extrahuje GPS súradnice a číselné hodnoty ISO, FNumber a FocalLength pre štatistiku (min/max/avg).

**5. Detekcia úprav a anomálií:**

Software tag sa porovnáva s databázou editačného softvéru (Photoshop, Lightroom, GIMP, Instagram a ďalšie). Detegujú sa anomálie: budúci dátum, neobvyklé ISO (>25600), ModifyDate > DateTimeOriginal.

**6. Export výstupov:**

Systém uloží `exif_database.json` (kompletná databáza), `exif_data.csv` (Excel-kompatibilný export) a `EXIF_REPORT.txt` (textový report pre klienta).

## Výsledek

Kompletná EXIF databáza (`exif_database.json`) s per-file metadátami, časovou osou a GPS zoznamom. CSV export pre ďalšie spracovanie. EXIF quality score: excellent (>90 % DateTimeOriginal), good (70–90 %), fair (50–70 %), poor (<50 %). Workflow pokračuje na validáciu integrity obnovených fotografií.

## Reference

EXIF 2.32 Specification (CIPA DC-008-2019)
ISO 12234-2:2001 – Electronic still-picture imaging
ExifTool Documentation

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Dávkové spracovanie (50 súborov naraz) je kompromis medzi rýchlosťou a limitom dĺžky príkazového riadku. Argument `-n` v exiftool vypíše numerické hodnoty GPS a nastavení namiesto textových popisov – nevyhnutné pre štatistický výpočet.

Quality score je postavený na DateTimeOriginal (nie CreateDate), pretože CreateDate môže byť ovplyvnený editačným softvérom a nemusí odrážať skutočný čas fotografovania.