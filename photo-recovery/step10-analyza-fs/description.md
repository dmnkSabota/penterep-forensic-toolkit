# Detaily testu

## Úkol

Analyzovať forenzný obraz média a určiť typ súborového systému, jeho stav (rozpoznaný/poškodený), partície a metadáta potrebné pre výber optimálnej stratégie obnovy fotografií.

## Obtiažnosť

Snadné

## Časová náročnosť

10

## Automatický test

Áno

## Popis

Analýza súborového systému je prvý krok forenznej analýzy po vytvorení a overení forenzného obrazu. Tento krok určuje, ako budeme pristupovať k obnove dát na základe stavu súborového systému. Súborový systém je "organizačná štruktúra" média - určuje, ako sú súbory uložené, pomenované, organizované do adresárov a ako sa spravujú metadáta.

Prečo je tento krok kritický? Určuje, ktorá stratégia obnovy bude použitá v Kroku 11. Rozpoznaný súborový systém s intaktnou štruktúrou umožňuje použiť filesystem-based recovery, ktorý je rýchlejší a zachováva pôvodné názvy súborov, umiestnenie v adresároch, časové značky a metadáta. Poškodený alebo nerozpoznaný súborový systém vyžaduje file carving - pomalšiu metódu, ktorá hľadá súbory na základe signatúr v raw dátach, ale stráca pôvodné názvy a štruktúru.

Analýza zahŕňa päť fáz: analýza partícií (mmls tool na detekciu partičnej tabuľky - DOS/MBR, GPT alebo superfloppy bez partícií), analýza súborového systému (fsstat tool na detekciu typu FS ako FAT32, exFAT, NTFS, ext4 a metadát), test adresárovej štruktúry (fls tool na overenie čitateľnosti directory entries), identifikácia obrazových súborov (vyhľadanie .jpg, .png, .raw, .cr2, .nef súborov), a vyhodnotenie stratégie (automatické určenie optimálnej metódy obnovy).

Výstupom je komplexný JSON report obsahujúci informácie o partíciách, type súborového systému, jeho stave, čitateľnosti adresárov, počte nájdených obrazových súborov a odporúčanú stratégiu obnovy. Tento report je vstupom pre Krok 11 (Rozhodnutie o stratégii obnovy), kde sa automaticky vyberie medzi filesystem-based scan (Krok 12A) alebo file carving (Krok 12B).

## Jak na to

Overte, že forenzný obraz bol úspešne vytvorený a overený v predchádzajúcich krokoch. Skript automaticky načíta cestu k obrazu zo Step 6 JSON výstupu (`{case_id}_hash_verification.json`), kde je uložená ako `image_path`. Ak súbor neexistuje alebo cesta k obrazu chýba, skript ohlási chybu a vyžaduje dokončenie Krokov 5 a 6.

Nainštalujte The Sleuth Kit (TSK) nástroje, ktoré sú základom forenznej analýzy súborových systémov. Na Ubuntu/Debian: `sudo apt-get install sleuthkit`. Overte inštaláciu pomocou `mmls --version`, `fsstat --version` a `fls --version`. Tieto nástroje musia byť dostupné v PATH. TSK podporuje prakticky všetky bežné súborové systémy: FAT12/16/32, exFAT, NTFS, ext2/3/4, HFS+, APFS, ISO 9660 a ďalšie.

Spustite automatický skript `python3 step10_analyze_filesystem.py {case_id}`. Skript vykoná nasledujúce fázy automaticky:

FÁZA 1 - Analýza partícií: Spustí `mmls {image_path}` na detekciu partičnej tabuľky. Identifikuje typ tabuľky (DOS/MBR pre staršie médiá, GPT pre moderné disky, alebo žiadna partičná tabuľka pre superfloppy - flash médiá formátované priamo bez partícií). Pre každú partíciu zaznamenáva: offset (počiatočný sektor), veľkosť v sektoroch, typ partície (primárna/rozšírená/logická), a deskriptor. Ak mmls zlyhá, predpokladá sa superfloppy formát (typické pre USB flash disky a SD karty), kde celé médium je jeden súborový systém bez partičnej tabuľky.

FÁZA 2 - Analýza súborového systému: Pre každú identifikovanú partíciu (alebo celé médium ak superfloppy) spustí `fsstat -o {offset} {image_path}`. fsstat extrahuje metadáta súborového systému: typ FS (FAT32, exFAT, NTFS, ext4...), stav FS (rozpoznaný/poškodený), veľkosť sektora (typicky 512 alebo 4096 bajtov), veľkosť klastra/bloku (určuje granularitu alokácie), volume label (meno média), UUID/serial number, počet celkových blokov a voľných blokov, root directory inode. Úspešné dokončenie fsstat bez chýb znamená rozpoznaný súborový systém. Chyby alebo nemožnosť identifikovať FS typ znamená poškodený alebo nerozpoznaný FS.

FÁZA 3 - Test adresárovej štruktúry: Spustí `fls -r -o {offset} {image_path}` na rekurzívne listovanie adresárovej štruktúry. fls zobrazuje directory entries vrátane: aktívnych súborov (bežné súbory v súborovom systéme), vymazaných súborov (označené * prefix, stále majú directory entry), allocated/unallocated/orphaned súbory, plné cesty súborov. Skript počíta počet aktívnych a vymazaných súborov. Ak fls uspeje a vráti aspoň nejaké directory entries, adresárová štruktúra je čitateľná. Ak fls zlyhá alebo vráti prázdny výstup, štruktúra je nečitateľná (súborový systém poškodený).

FÁZA 4 - Identifikácia obrazových súborov: Parsuje výstup z fls a hľadá súbory s obrazovými príponami. Podporované formáty: .jpg/.jpeg (JPEG komprimované), .png (PNG lossless), .gif (GIF animácie), .bmp (bitmap), .tiff/.tif (TIFF), .raw/.cr2/.nef/.arw/.dng (RAW formáty z fotoaparátov Canon/Nikon/Sony/Adobe), .heic (Apple HEIF format), .webp (Google WebP). Počíta počet súborov podľa typu a stavu (aktívne vs vymazané). Vytvára zoznam nájdených obrazových súborov s metadátami (cesta, veľkosť, timestamp, inode).

FÁZA 5 - Vyhodnotenie stratégie obnovy: Na základe výsledkov predchádzajúcich fáz automaticky určí optimálnu stratégiu. Rozhodovacia logika: Ak súborový systém je rozpoznaný (fsstat success) A adresárová štruktúra je čitateľná (fls success), potom odporúčaná metóda je "filesystem_scan" (Krok 12A). Ak súborový systém nie je rozpoznaný (fsstat failed) ALEBO adresárová štruktúra nie je čitateľná (fls failed alebo empty), potom odporúčaná metóda je "file_carving" (Krok 12B). Ak súborový systém je čiastočně rozpoznaný (fsstat success ale fls partial), odporúča sa kombinovaný prístup "hybrid" (najprv filesystem scan, potom carving na unallocated space).

Vygenerujte komplexný JSON report obsahujúci: Case ID, cesta k forenznom obrazu, timestamp analýzy, informácie o partíciách (pre každú partíciu: číslo, offset, veľkosť, typ FS, stav FS, label, UUID, metadata), celkový počet nájdených obrazových súborov (rozdelené podľa typu a stavu), čitateľnosť adresárovej štruktúry (true/false), odporúčanú metódu obnovy (filesystem_scan/file_carving/hybrid), odporúčaný nástroj (fls+icat pre FS scan, photorec/foremost pre carving), odhadovanú časovú náročnosť obnovy, a poznámky/varovania.

Výstupný JSON uložte do `/mnt/user-data/outputs/{case_id}_filesystem_analysis.json`. Tento súbor slúži ako vstup pre Krok 11 (Rozhodnutie o stratégii) a dokumentácia pre Chain of Custody. Vytlačte prehľadný report do konzoly s farebným zvýraznením (zelená = rozpoznaný FS, žltá = čiastočne rozpoznaný, červená = nerozpoznaný).

## Výsledek

Komplexný report o stave súborového systému vytvorený a uložený ako JSON. Identifikovaný typ súborového systému (FAT32, exFAT, NTFS, ext4 alebo iný), stav FS (rozpoznaný/čiastočne rozpoznaný/nerozpoznaný), počet partícií, čitateľnosť adresárovej štruktúry (áno/nie), počet nájdených obrazových súborov (celkovo a rozdelené podľa typu a stavu - aktívne/vymazané). Automaticky určená odporúčaná stratégia obnovy: pri rozpoznanom FS → Krok 12A (filesystem-based scan pomocou fls+icat), pri nerozpoznanom FS → Krok 12B (file carving pomocou photorec/foremost), pri čiastočne rozpoznanom → hybridný prístup (kombinácia oboch metód). Report obsahuje aj odhad časovej náročnosti obnovy a poznámky o špeciálnych okolnostiach (šifrovanie, fragmentácia, viacero partícií). Workflow automaticky pokračuje do Kroku 11 (Rozhodnutie o stratégii obnovy) s JSON reportom ako vstupom.

## Reference

ISO/IEC 27037:2012 - Section 7 (Analysis of digital evidence)
NIST SP 800-86 - Section 3.1.2 (Examination Phase - Filesystem analysis)
The Sleuth Kit Documentation - mmls, fsstat, fls tools
Brian Carrier: File System Forensic Analysis (2005)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)