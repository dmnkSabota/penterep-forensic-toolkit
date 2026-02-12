# Detaily testu

## Úkol

Využiť funkčný súborový systém na identifikáciu a obnovu všetkých obrazových súborov (aktívnych aj vymazaných) so zachovaním pôvodných názvov, adresárovej štruktúry a metadát.

## Obtiažnosť

Střední

## Časová náročnosť

60

## Automatický test

Áno

## Popis

File System-Based Recovery je preferovaná stratégia obnovy, pretože využíva informácie zo súborového systému samotného. Keď sa súbor vymaže, obsah zostane na disku, len sa označí priestor ako "voľný". Metadata súboru (meno, veľkosť, pozícia) zostanú v adresárovom zázname.

Prečo je tento krok kritický:
- Zachová pôvodné názvy súborov (IMG_0001.JPG, DSC_0145.JPG)
- Zachová adresárovú štruktúru (DCIM/100CANON/, DCIM/101CANON/)
- Zachová časové značky (Created, Modified, Accessed)
- Zachová všetky EXIF metadáta a atribúty súborov
- Zachová poradie súborov
- Rýchlejšia než file carving (30 min - 2 hod vs 2-8 hod)
- Môže obnoviť čiastočne prepísané súbory

Princíp: pomocou fls prečítame zoznam všetkých súborov vrátane vymazaných (značených * v listingu), vyfiltrujeme obrazové formáty (jpg, png, tiff, raw), pomocou icat extrahujeme obsah podľa inode/metadata adresy. Fungovanie závisí od toho, či metadata sú intaktné.

## Jak na to

1. SKENOVANIE - overiť že Krok 10 odporučil "filesystem_scan", načítať partition offset, spusti `fls -r -d -p -o {offset} image.dd` na rekurzívne získanie kompletného file listingu vrátane vymazaných súborov (označené *)
2. FILTROVANIE - z listingu vyfiltruj obrazové súbory pomocou regex na prípony (jpg|jpeg|png|tif|tiff|gif|bmp|raw|cr2|nef|arw|dng|heic), rozdeľ na aktívne a vymazané
3. EXTRAKCIA - pre každý súbor: parse inode z listingu (formát: r/r 123: /path/file.jpg), spusti `icat -o {offset} image.dd {inode}`, ulož do cieľového adresára so zachovaním pôvodnej cesty
4. VALIDÁCIA - skontroluj extrahované súbory pomocou `file` command a `identify` z ImageMagick, roztried do valid/corrupted/invalid, vymaž prázdne a neplatné
5. METADATA - pre každý validný súbor: extrahuj FS metadata (timestamps, size, atribúty), extrahuj EXIF pomocou `exiftool -json`, ulož do metadata katalógu (JSON)
6. ORGANIZÁCIA - zachovaj pôvodnú adresárovú štruktúru, vytvor podsložky active/ a deleted/, ulož štatistiky (počet nájdených, extrahovaných, validných, s EXIF)

---

## Výsledek

Kolekcia obnovených súborov s pôvodnými názvami a adresárovou štruktúrou. Aktívne súbory v active/, vymazané v deleted/, poškodené v corrupted/. Úspešnosť typicky >95% pre aktívne súbory, 70-90% pre vymazané (závisí od prepísania). Štatistiky: celkový počet záznamov FS, aktívne vs vymazané, obrazové súbory nájdené, úspešne extrahované, validné, s EXIF metadátami. Metadata katalóg obsahuje FS timestamps a EXIF pre ďalšiu analýzu. Zachované: názvy, štruktúra, timestamps, EXIF, atribúty.

## Reference

ISO/IEC 27037:2012 - Section 7.3 (Data Extraction)
NIST SP 800-86 - Section 3.1.2.2 (File System Recovery)
The Sleuth Kit Documentation (fls, icat)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)