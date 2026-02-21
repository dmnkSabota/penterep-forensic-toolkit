# Detaily testu

## Úkol

Využiť funkčný súborový systém na identifikáciu a obnovu všetkých obrazových súborov (aktívnych aj vymazaných) so zachovaním pôvodných názvov, adresárovej štruktúry a metadát.

## Obtiažnosť

Stredná

## Časová náročnosť

60 minút

## Automatický test

Áno

## Popis

Filesystem-based recovery je preferovaná stratégia obnovy, pretože využíva informácie zo súborového systému samotného. Keď sa súbor vymaže, obsah zostane na disku – len sa označí priestor ako voľný, zatiaľ čo metadata (meno, veľkosť, pozícia na disku) zostanú v adresárovom zázname. Pomocou `fls` prečítame zoznam všetkých súborov vrátane vymazaných, vyfiltrujeme obrazové formáty a pomocou `icat` extrahujeme obsah podľa inode adresy.

Oproti file carvingu (Krok 10B) táto metóda zachováva pôvodné názvy súborov, adresárovú štruktúru, časové značky aj EXIF metadáta. Je tiež výrazne rýchlejšia. Predpokladom je úspešný výsledok Kroku 8 (Analýza súborového systému) s odporúčanou metódou `filesystem_scan` alebo `hybrid`.

## Jak na to

**1. Načítanie výsledkov Kroku 8:**

Systém načíta súbor `{case_id}_filesystem_analysis.json` (výstup Kroku 8). Overí odporúčanú metódu – pri `file_carving` sa pokračuje Krokom 10B namiesto tohto kroku. Pri `hybrid` sa vykoná filesystem scan a následne aj Krok 10B.

**2. Overenie nástrojov:**

Systém overí dostupnosť `fls` a `icat` (The Sleuth Kit), `file` (detekcia typu), `identify` (ImageMagick – validácia), `exiftool` (EXIF). Inštalácia: `sudo apt-get install sleuthkit imagemagick libimage-exiftool-perl`.

**3. Skenovanie súborového systému (fls):**

`fls -r -d -p -o {offset} {image.dd}` rekurzívne vypíše všetky záznamy vrátane vymazaných (označené `*`). Výsledok sa prefiltruje na obrazové prípony (.jpg, .png, .tiff, .raw, .cr2, .nef, .arw, .dng a ďalšie) a rozdelí na aktívne a vymazané súbory.

**4. Extrakcia (icat) a validácia:**

Pre každý súbor systém spustí `icat -o {offset} {image.dd} {inode}` a uloží výstup so zachovaním pôvodnej adresárovej cesty. Každý extrahovaný súbor sa validuje v troch fázach: nenulová veľkosť → `file -b` potvrdí typ obrazu → `identify` potvrdí čitateľnú štruktúru. Výsledok je zatriedený do `active/`, `deleted/`, `corrupted/` alebo `invalid` (vymazaný).

**5. Extrakcia metadát:**

Pre každý validný súbor systém extrahuje FS timestamps (mtime, atime, ctime) a EXIF metadáta (`exiftool -json`). Metadata sa uložia ako individuálny JSON súbor do `metadata/`.

**6. Záverečný report:**

Systém uloží `{case_id}_recovery_report.json` so štatistikami a zoznamom obnovených súborov, a `RECOVERY_REPORT.txt` pre čitateľný prehľad.

## Výsledek

Kolekcia obnovených súborov uložená v `{case_id}_recovered/`: aktívne súbory v `active/`, vymazané v `deleted/`, čiastočne poškodené v `corrupted/`. Úspešnosť typicky >95 % pre aktívne súbory, 70–90 % pre vymazané (závisí od miery prepísania). JSON report obsahuje štatistiky a zoznam obnovených súborov, textový report `RECOVERY_REPORT.txt` pre klienta. Zachované: pôvodné názvy, adresárová štruktúra, FS timestamps, EXIF. Workflow pokračuje do Kroku 10 (File Carving) ak bol odporúčaný `hybrid`, alebo priamo do Kroku 11 (Katalogizácia fotografií).

## Reference

ISO/IEC 27037:2012 – Section 7.3 (Data Extraction)
NIST SP 800-86 – Section 3.1.2.2 (File System Recovery)
The Sleuth Kit Documentation (fls, icat)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Skript načítava výsledky z Kroku 8 (ptfilesystemanalysis) cez `{case_id}_filesystem_analysis.json`. Ak bol výsledok Kroku 8 `file_carving`, skript odmietne pokračovať bez `--force` – tým sa predchádza spusteniu nesprávnej metódy. Pri `hybrid` pokračuje normálne, ale vypíše upozornenie aby bol spustený aj Krok 10B.

Extrakcia je zámerne sekvenčná (nie paralelná) – súbežný prístup na forenzný obraz by mohol spôsobiť problémy s read pozíciou a je ťažko auditovateľný. Rýchlosť pri typickej SD karte (8–32 GB) je 500–2000 súborov za minútu.