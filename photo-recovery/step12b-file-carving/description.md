# Detaily testu

## Úkol

Obnoviť obrazové súbory priamym vyhľadávaním byte signatúr (magic bytes) v raw dátach forenzného obrazu bez závislosti na súborovom systéme.

## Obtiažnosť

Střední

## Časová náročnosť

240

## Automatický test

Áno

## Popis

File Carving je technika obnovy dát, ktorá ignoruje súborový systém a namiesto toho hľadá priamo byte signatúry súborov v raw dátach média. Každý typ súboru má charakteristické signatúry - JPEG začína FF D8 FF a končí FF D9, PNG začína 89 50 4E 47.

Prečo je tento krok kritický:
- Funguje aj bez súborového systému (naformátované, poškodené, nerozpoznané)
- Dokáže nájsť súbory, ktoré FS-based recovery nevidí
- Môže obnoviť čiastočne prepísané súbory
- EXIF metadáta zostávajú zachované (sú embedded v súboroch)
- Stratia sa pôvodné názvy súborov (generujú sa nové: CASEID_jpg_000001.jpg)
- Stratí sa adresárová štruktúra a časové značky súborového systému
- Veľmi pomalý proces (2-8 hodín na 64GB médium)

Používame PhotoRec (open-source, najpopulárnejší, nájde najviac súborov, má rekonštrukciu fragmentov). Carved súbory musia byť validované (ImageMagick identify) a deduplikované (SHA-256 hash).

## Jak na to

1. KONFIGURÁCIA - overiť že Krok 10 je dokončený, načítať cestu k obrazu, vytvoriť PhotoRec config (povoliť len image formáty: jpg, png, tiff, gif, bmp, heic, cr2, nef, arw, dng), nastaviť paranoid mode
2. PHOTOREC CARVING - spusti `photorec /d output/ /cmd image.dd search`, čakaj 2-8 hodín, PhotoRec skenuje celé médium byte-po-byte a hľadá signatúry, ukladá do recup_dir.1, recup_dir.2, ... adresárov
3. VALIDÁCIA - pre každý carved súbor: skontroluj veľkosť (min 100 bajtov), spusti `file` command, spusti `identify` z ImageMagick, roztried do valid/corrupted/invalid
4. DEDUPLIKÁCIA - vypočítaj SHA-256 hash pre každý validný súbor, odstráň duplikáty (typicky 20-30%), presun duplikáty do duplicates/ adresára
5. EXIF EXTRAKCIA - pre každý unikátny súbor spusti `exiftool -json`, ulož metadata do JSON súborov, počítaj koľko má EXIF, GPS coordinates
6. ORGANIZÁCIA - roztrieď podľa typu (jpg/, png/, tiff/, raw/, other/), premenuj systematicky (CASEID_jpg_000001.jpg), vytvor katalóg a JSON report

---

## Výsledek

Kolekcia obnovených obrazových súborov s automaticky generovanými názvami organizovaná podľa typu. Zachované: EXIF metadáta a obsah fotografií. Stratené: pôvodné názvy, adresárová štruktúra, časové značky FS. Štatistiky: počet carved súborov (raw), validných po kontrole, unikátnych po deduplikácii, úspešnosť validácie 50-65%. Typicky 20-30% duplikátov. Report obsahuje trvanie jednotlivých fáz a katalóg súborov.

## Reference

NIST SP 800-86 - Section 3.1.2.3 (Data Carving)
Brian Carrier: File System Forensic Analysis - Chapter 14
PhotoRec Documentation

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)