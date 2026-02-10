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

File System-Based Recovery je preferovaná stratégia obnovy fotografií, pretože využíva informácie zo súborového systému samotného namiesto pomalého vyhľadávania byte signatúr. Táto metóda je možná len vtedy, keď súborový systém bol v Kroku 10 rozpoznaný a adresárová štruktúra je čitateľná. Ak Krok 10 odporučil "file_carving", preskočte tento krok a prejdite priamo na Krok 12B.

Prečo je tento krok kritický? Keď používateľ vymaže súbor, operačný systém nevymaže samotné dáta - len označí priestor ako "voľný" v alokačnej tabuľke a odstráni záznam z viditeľného adresára. Avšak metadata súboru (meno, veľkosť, pozícia inode, timestamps) často zostanú zachované v súborovom systéme do doby, kým nie sú prepísané novými dátami. The Sleuth Kit dokáže pristupovať aj k týmto "vymazaným" záznamom a extrahovať súbory pomocou ich inode čísel.

Výhody oproti file carving (Krok 12B): Zachované pôvodné názvy súborov ako IMG_0001.JPG, DSC_0145.JPG namiesto generických 00000001.jpg. Zachovaná adresárová štruktúra ako DCIM/100CANON/, DCIM/101CANON/ - viete, ktoré fotky boli v ktorom priečinku. Zachované časové značky Created/Modified/Accessed - dôležité pre timeline analýzu. Všetky EXIF metadáta a atribúty súborov zostávajú intaktné - GPS pozície, nastavenia fotoaparátu, dátum snímania. Zachované poradie súborov - dôležité pre sekvenčné fotografie. Rýchlejšia než file carving - 30 min až 2 hodiny vs 2-8 hodín pre 64GB médium. Môže obnoviť aj čiastočne prepísané súbory ak sú metadata stále dostupné.

Princíp fungovania: Použijeme nástroj `fls` (File Listing) z The Sleuth Kit na rekurzívne prečítanie VŠETKÝCH directory entries zo súborového systému vrátane vymazaných súborov (tie sú označené * prefix v listingu). Z výstupu vyfiltrujeme obrazové súbory podľa prípony (.jpg, .png, .tiff, .raw formáty). Pre každý nájdený obrazový súbor získame inode číslo (unique identifikátor súboru v súborovom systéme). Pomocou nástroja `icat` (Inode Cat) extrahujeme obsah súboru priamo cez inode adresu, čím obídeme normálny file API a pristupujeme k dátam aj keď sú "vymazané". Zachováme pôvodnú štruktúru adresárov a rozdelíme súbory do kategórií: active/ (aktívne súbory), deleted/ (vymazané ale obnoviteľné), corrupted/ (čiastočne prepísané).

Úspešnosť obnovy: Pre aktívne súbory typicky >95% (takmer všetky okrem tých, ktoré sú na fyzicky poškodených sektoroch). Pre vymazané súbory 70-90% v závislosti od toho, koľko času uplynulo od vymazania a či boli dáta čiastočne prepísané novými súbormi. Faktory ovplyvňujúce úspešnosť: SSD médiá s aktívnym TRIM príkazom fyzicky odstráňujú vymazané dáta na pozadí (úspešnosť môže klesnúť na <30%). Fragmentácia súborov - FAT32 má nízku fragmentáciu, NTFS/ext4 vyššiu. Wear leveling na flash médiách môže premiestniť bloky.

## Jak na to

Overte, že Krok 10 (Filesystem Analysis) bol dokončený a odporučil metódu "filesystem_scan". Načítajte JSON report z Kroku 10 (`{case_id}_filesystem_analysis.json`), kde nájdete: cestu k forenznom obrazu (`image_file`), informácie o partíciách vrátane offsetov (`partitions[].offset`), typ súborového systému (`partitions[].filesystem.type`), počet očakávaných obrazových súborov (`image_files_found.total`). Ak Krok 10 odporučil "file_carving", PRESKOČTE tento krok a použite Krok 12B.

Nainštalujte potrebné nástroje. The Sleuth Kit (fls, icat): `sudo apt-get install sleuthkit`. ImageMagick (validácia obrázkov): `sudo apt-get install imagemagick`. ExifTool (extrakcia metadát): `sudo apt-get install libimage-exiftool-perl`. Overte inštaláciu: `fls --version`, `icat --version`, `identify --version`, `exiftool -ver`.

Spustite automatický skript `python3 step12a_filesystem_recovery.py {case_id}`. Skript vykoná šesť fáz automaticky:

FÁZA 1 - Skenovanie súborového systému: Pre každú partíciu identifikovanú v Kroku 10 spustí `fls -r -d -p -o {offset} {image_path}`. Parametre: `-r` rekurzívne (prechádza všetky podadresáre), `-d` zobrazuje len vymazané súbory (deleted), `-p` zobrazuje plné cesty, `-o {offset}` začína na danej partícii. Výstup obsahuje riadky formátu: `r/r * 12845:	DCIM/100CANON/IMG_0001.JPG` (vymazaný súbor) alebo `r/r 12846:	DCIM/100CANON/IMG_0002.JPG` (aktívny súbor). Symbol `*` označuje vymazaný súbor, číslo `12845` je inode, `r/r` označuje regular file. Skript parsuje tento výstup a extrahuje: inode číslo, názov súboru, pôvodná cesta, stav (active/deleted).

FÁZA 2 - Filtrovanie obrazových súborov: Z kompletného file listingu vyfiltruje len obrazové súbory pomocou regex na prípony. Podporované formáty: JPEG (.jpg, .jpeg), PNG (.png), TIFF (.tif, .tiff), BMP (.bmp), GIF (.gif), HEIC (.heic, .heif), RAW formáty (.cr2 Canon, .nef Nikon, .arw Sony, .dng Adobe, .orf Olympus, .raf Fuji, .rw2 Panasonic). Rozdelenie súborov do kategórií: active_images (aktívne obrazové súbory), deleted_images (vymazané obrazové súbory). Počítanie štatistík: celkový počet súborov, počet obrazových súborov, rozdelenie podľa typu (JPEG, PNG, RAW...).

FÁZA 3 - Extrakcia súborov pomocou icat: Pre každý nájdený obrazový súbor: Vytvorenie cieľového adresára so zachovaním pôvodnej štruktúry (napr. `recovered/active/DCIM/100CANON/` alebo `recovered/deleted/DCIM/100CANON/`). Spustenie `icat -o {offset} {image_path} {inode} > {output_file}` na extrakciu obsahu súboru cez inode. icat číta priamo z blokov disku na základe inode adresy, funguje aj pre vymazané súbory. Zachovanie pôvodného názvu súboru (IMG_0001.JPG zostáva IMG_0001.JPG). Nastavenie FS timestamps na extrahovanom súbore podľa metadát z fls výstupu (ak sú dostupné). Progress reporting - zobrazenie koľko súborov bolo extrahovaných / celkový počet. Timeout handling - niektoré súbory môžu zlyhať ak sú na poškodených sektoroch.

FÁZA 4 - Validácia obnovených súborov: Pre každý extrahovaný súbor vykonať sériu validačných testov. Test 1 - Kontrola veľkosti súboru: Ak je súbor 0 bajtov, je nevalidný (kompletne prepísaný). Test 2 - file command: Spustenie `file {path}` na detekciu skutočného typu súboru. Overenie, že typ súboru zodpovedá prípone (JPEG súbor má obsahovať "JPEG image data"). Test 3 - ImageMagick identify: Spustenie `identify {path}` na overenie, že súbor je validný obrázok. identify dokáže otvoriť súbor a prečítať jeho štruktúru, zlyhá pre korumpované súbory. Extrakcia rozmerov (width x height), formátu a farebnej hĺbky. Test 4 - EXIF kontrola: Pokus o načítanie EXIF metadát pomocou exiftool. Súbory s intaktnými EXIF sú typicky menej korumpované. Kategorizácia výsledkov: VALID - prešiel všetkými testami, môže sa použiť. CORRUPTED - čiastočne poškodený (otvoriteľný ale s chybami, možno orezaný). INVALID - úplne nevalidný (0 bajtov, nečitateľný, nesprávny formát). Presun nevalidných súborov do `corrupted/` adresára pre manuálnu inšpekciu.

FÁZA 5 - Extrakcia metadát: Pre každý validný súbor extrahujeme dve úrovne metadát. FS metadata (zo súborového systému): File size (veľkosť v bajtoch), Created timestamp (čas vytvorenia - ak je dostupný z FS), Modified timestamp (čas poslednej modifikácie), Accessed timestamp (čas posledného prístupu), Inode číslo (pre referenciu), Original path (pôvodná cesta v súborovom systéme), Deletion timestamp (ak bol súbor vymazaný - kedy). EXIF metadata (embedded v súbore): Spustenie `exiftool -json {path}` na extrakciu všetkých EXIF tagov. Dôležité EXIF polia: DateTimeOriginal (kedy bola fotka vyhotovená), GPS coordinates (latitude/longitude - ak je GPS tag), Camera make/model (Canon EOS 5D Mark IV...), Lens info, Exposure settings (ISO, aperture, shutter speed), Image dimensions, Orientation, Software used. Uloženie metadát do JSON súboru pre každý obrázok: `{filename}_metadata.json` obsahuje FS metadata + EXIF metadata. Vytvorenie master katalógu `{case_id}_metadata_catalog.json` obsahujúceho metadata všetkých obnovených súborov.

FÁZA 6 - Organizácia a reporting: Vytvorenie štruktúry výstupných adresárov. `recovered/active/` - aktívne súbory so zachovanou adresárovou štruktúrou. `recovered/deleted/` - vymazané ale úspešne obnovené súbory so zachovanou štruktúrou. `recovered/corrupted/` - čiastočne poškodené súbory pre manuálnu inšpekciu. `metadata/` - JSON súbory s EXIF a FS metadátami pre každý súbor. Vytvorenie komplexného JSON reportu `{case_id}_recovery_report.json` obsahujúceho: Celkový počet súborov v FS (všetky súbory, nie len obrázky). Počet obrazových súborov nájdených (aktívne + vymazané). Počet úspešne extrahovaných súborov. Počet validných súborov po kontrole. Počet korumpovaných/nevalidných súborov. Rozdelenie podľa typu (JPEG: 340, PNG: 25, RAW: 12...). Success rate (% validných z celkového počtu extrahovaných). Čas trvania každej fázy. Vytvorenie prehľadného textového reportu pre používateľa obsahujúceho štatistiky a zoznam obnovených súborov.

## Výsledek

Kolekcia obnovených obrazových súborov organizovaná do adresárov: `recovered/active/` obsahuje aktívne súbory s pôvodnou adresárovou štruktúrou a názvami ako DCIM/100CANON/IMG_0001.JPG, DCIM/101CANON/DSC_0234.JPG. `recovered/deleted/` obsahuje vymazané ale úspešne obnovené súbory s rovnakou štruktúrou. `recovered/corrupted/` obsahuje čiastočne poškodené súbory pre manuálnu inšpekciu. `metadata/` obsahuje JSON súbory s EXIF a FS metadátami pre každý obnovený súbor.

Typická úspešnosť obnovy: Aktívne súbory >95% (takmer všetky okrem fyzicky poškodených sektorov). Vymazané súbory 70-90% v závislosti od prepísania (závisí od toho, koľko času uplynulo od vymazania a či boli dáta prepísané). HDD médiá majú vyššiu úspešnosť než SSD s aktívnym TRIM (SSD môže fyzicky zmazať dáta). FAT32 súborový systém má jednoduchšiu štruktúru = vyššia úspešnosť. NTFS/ext4 majú komplexnejšiu štruktúru ale lepšie metadata.

Štatistiky v JSON reporte: total_files_in_fs (celkový počet súborov v súborovom systéme), image_files_found (koľko obrazových súborov bolo nájdených), images_extracted (koľko sa podarilo extrahovať), valid_images (koľko prešlo validáciou), corrupted_images (koľko je čiastočne poškodených), invalid_images (koľko je úplne nevalidných), success_rate (% úspešnosti), by_format (rozdelenie podľa formátu - JPEG, PNG, TIFF, RAW), by_status (aktívne, vymazané, korumpované), with_exif (koľko má EXIF metadáta), extraction_duration_seconds (čas trvania extrakcie), validation_duration_seconds (čas trvania validácie).

Zachované informácie: Pôvodné názvy súborov (IMG_0001.JPG zostáva IMG_0001.JPG, nie 00000001.jpg). Adresárová štruktúra (DCIM/100CANON/ zostáva DCIM/100CANON/). FS timestamps (Created, Modified, Accessed - ak sú dostupné z fls). EXIF metadáta (GPS, camera settings, DateTime - embedded v súbore). Atribúty súborov (read-only, hidden - ak sú v FS). Poradie súborov (dôležité pre sekvenčné fotografie).

Stratené informácie pri čiastočne korumpovaných súboroch: Ak bol súbor čiastočne prepísaný, niektoré metadata môžu chýbať. GPS koordináty môžu byť stratené ak bol EXIF header prepísaný. Thumbnail obrázky v EXIF môžu chýbať. Pre kompletne prepísané súbory (0 bajtov) nie je možná obnova.

Workflow automaticky pokračuje do Kroku 13 (EXIF Analysis) kde sa analyzujú extrahované EXIF metadáta na vytvorenie timeline, GPS mapy a štatistík kamery. Alternatívne, ak bol použitý hybridný prístup (Krok 10 odporučil "hybrid"), po dokončení tohto kroku pokračujte do Kroku 12B (File Carving) na obnovu zvyšných súborov, ktoré neboli viditeľné cez súborový systém.

## Reference

ISO/IEC 27037:2012 - Section 7.3 (Data Extraction from digital evidence)
NIST SP 800-86 - Section 3.1.2.2 (File System-Based Recovery methods)
The Sleuth Kit Documentation - fls and icat tools reference
Brian Carrier: File System Forensic Analysis (2005) - Chapter 10

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)