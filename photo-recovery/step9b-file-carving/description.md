# Detaily testu

## Úkol

Obnoviť obrazové súbory priamym vyhľadávaním byte signatúr (magic bytes) v raw dátach forenzného obrazu bez závislosti na súborovom systéme.

## Obtiažnosť

Stredná

## Časová náročnosť

240 minút

## Automatický test

Áno

## Popis

File Carving je technika obnovy dát, ktorá ignoruje súborový systém a namiesto toho hľadá priamo byte signatúry súborov v raw dátach média. Každý typ súboru má charakteristické signatúry – JPEG začína FF D8 FF a končí FF D9, PNG začína 89 50 4E 47. Táto metóda funguje aj bez súborového systému (naformátované, poškodené, nerozpoznané médium) a dokáže nájsť súbory, ktoré filesystem-based recovery nevidí. EXIF metadáta zostávajú zachované, pretože sú embedded priamo v súboroch. Na druhej strane sa strácajú pôvodné názvy súborov, adresárová štruktúra a FS timestamps.

Implementácia využíva PhotoRec – open-source nástroj s podporou fragmentovaných súborov a paranoid módom pre maximálne pokrytie. Carved súbory prechádzajú trojfázovou validáciou (veľkosť → `file` command → ImageMagick `identify`) a SHA-256 deduplikáciou. Výsledné súbory sú premenované systematicky na `{case_id}_{typ}_{seq}.ext` a organizované do podadresárov podľa formátu.

Predpokladom je úspešný výsledok Kroku 8 (Analýza súborového systému) s odporúčanou metódou `file_carving` alebo `hybrid`. Pri `filesystem_scan` sa namiesto tohto kroku pokračuje Krokom 9.

## Jak na to

**1. Načítanie výsledkov Kroku 8:**

Systém načíta súbor `{case_id}_filesystem_analysis.json`. Ak odporúčaná metóda je `filesystem_scan`, skript odmietne pokračovať bez `--force`. Pri `hybrid` pokračuje normálne – file carving dopĺňa Krok 9.

**2. Overenie nástrojov:**

Systém overí dostupnosť `photorec` (balíček testdisk), `file`, `identify` (ImageMagick), `exiftool`. Inštalácia: `sudo apt-get install testdisk imagemagick libimage-exiftool-perl`.

**3. PhotoRec carving:**

Systém vygeneruje konfiguráciu (povolí len obrazové formáty, aktivuje paranoid a expert mód) a spustí `photorec /log /d photorec_work/ /cmd {image.dd} search`. Proces trvá 2–8 hodín. PhotoRec ukladá výsledky do `recup_dir.*` adresárov.

**4. Validácia a deduplikácia:**

Pre každý carved súbor systém overí minimálnu veľkosť (100 B), typ cez `file -b` a čitateľnosť cez `identify`. Validné súbory prechádzajú SHA-256 deduplikáciou – typicky 20–30 % sú duplikáty. Výsledky sa triedia do `organized/`, `corrupted/`, `quarantine/`, `duplicates/`.

**5. EXIF extrakcia a organizácia:**

Pre každý unikátny súbor systém extrahuje EXIF (`exiftool -json`) a uloží metadata do `metadata/`. Súbory sú presunuté do podadresárov podľa formátu (`jpg/`, `png/`, `tiff/`, `raw/`, `other/`) a premenované na `{case_id}_{typ}_{seq:06d}.ext`.

## Výsledek

Kolekcia obnovených obrazových súborov s automaticky generovanými názvami organizovaná podľa formátu v `{case_id}_carved/`. Zachované: EXIF metadáta a obsah fotografií. Stratené: pôvodné názvy, adresárová štruktúra, FS timestamps. Úspešnosť validácie typicky 50–65 %, 20–30 % duplikátov. JSON report `{case_id}_carving_report.json` a textový `CARVING_REPORT.txt` obsahujú štatistiky a katalóg súborov. Workflow pokračuje do Kroku 11 (Katalogizácia fotografií).

## Reference

NIST SP 800-86 – Section 3.1.2.3 (Data Carving)
Brian Carrier: File System Forensic Analysis – Chapter 14
PhotoRec Documentation (https://www.cgsecurity.org/wiki/PhotoRec)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Konfigurácia PhotoRec sa generuje ako dávkový súbor `photorec.cmd` – tým sa eliminuje interaktívne menu a zaručuje reprodukovateľný forenzný postup. Paranoid mód zapína prísnejšiu validáciu signatúr (menej false positives, mierne pomalší sken). Expert mód umožňuje skenovanie celého obrazu vrátane unallocated space.

Streaming výstupu PhotoRec (`Popen` s čítaním stdout v reálnom čase) je zámerný – bez toho by timeout na 24-hodinovom procese nefungoval správne a používateľ by nevidel priebeh. SHA-256 deduplikácia prebieha priamo počas validácie v jednom prechode zoznamom carved súborov.