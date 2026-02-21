# Detaily testu

## Úkol

Analyzovať forenzný obraz média a určiť typ súborového systému, jeho stav (rozpoznaný/poškodený), partície a metadáta potrebné pre výber optimálnej stratégie obnovy fotografií.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

10 minút

## Automatický test

Áno

## Popis

Analýza súborového systému je prvý krok forenznej analýzy po vytvorení a overení forenzného obrazu. Tento krok určuje, ako budeme pristupovať k obnove dát na základe stavu súborového systému.

Výsledok analýzy priamo určuje stratégiu obnovy v Kroku 11: rozpoznaný súborový systém s čitateľnou adresárovou štruktúrou umožňuje filesystem-based recovery (zachováva pôvodné názvy súborov a metadáta), poškodený alebo nerozpoznaný súborový systém vyžaduje file carving (pomalšia metóda hľadajúca súbory podľa signatúr v raw dátach).

Analýza využíva nástroje The Sleuth Kit: `mmls` pre detekciu partičnej tabuľky, `fsstat` pre identifikáciu typu a metadát súborového systému, a `fls` pre overenie čitateľnosti adresárovej štruktúry.

## Jak na to

**1. Načítanie cesty k forenzném obrazu:**

Systém automaticky načíta cestu k obrazu zo súboru `{case_id}_verification.json` (výstup Kroku 6). Ak súbor neexistuje, Kroky 5 a 6 neboli dokončené.

**2. Overenie dostupnosti nástrojov TSK:**

Systém overí dostupnosť `mmls`, `fsstat` a `fls`. Ak niektorý chýba: `sudo apt-get install sleuthkit`.

**3. Analýza partičnej tabuľky (mmls):**

`mmls {image_path}` detekuje typ tabuľky (DOS/MBR, GPT) a zoznam partícií s ich offsetmi. Ak mmls zlyhá, predpokladá sa superfloppy formát – celé médium je jeden súborový systém bez partičnej tabuľky (typické pre USB flash disky a SD karty).

**4. Analýza súborového systému (fsstat):**

Pre každú partíciu systém spustí `fsstat -o {offset} {image_path}`. Úspešné dokončenie bez chýb znamená rozpoznaný súborový systém. Extrahujú sa metadáta: typ FS (FAT32, exFAT, NTFS, ext4...), volume label, UUID, veľkosť sektora a klastra.

**5. Test adresárovej štruktúry (fls):**

`fls -r -o {offset} {image_path}` rekurzívne listuje adresárovú štruktúru vrátane vymazaných súborov (označené `*`). Ak fls uspeje, systém spočíta aktívne a vymazané obrazové súbory (.jpg, .png, .raw, .cr2, .nef a ďalšie).

**6. Určenie stratégie obnovy:**

Na základe výsledkov systém automaticky určí odporúčanú metódu: `filesystem_scan` (rozpoznaný FS + čitateľná štruktúra), `file_carving` (nerozpoznaný FS), alebo `hybrid` (rozpoznaný FS ale poškodená štruktúra). Výsledok sa uloží do JSON reportu pre Krok 11.

## Výsledek

Report o stave súborového systému uložený ako `{case_id}_filesystem_analysis.json`. Identifikovaný typ FS, stav (rozpoznaný/čiastočne/nerozpoznaný), počet partícií, čitateľnosť adresárovej štruktúry, počet nájdených obrazových súborov (aktívne aj vymazané). Automaticky určená stratégia obnovy: `filesystem_scan` → Krok 12A, `file_carving` → Krok 12B, `hybrid` → kombinácia oboch. Workflow pokračuje do Kroku 11 (Rozhodnutie o stratégii obnovy).

## Reference

ISO/IEC 27037:2012 – Section 7 (Analysis of digital evidence)
NIST SP 800-86 – Section 3.1.2 (Examination Phase – Filesystem analysis)
The Sleuth Kit Documentation – mmls, fsstat, fls tools
Brian Carrier: File System Forensic Analysis (2005)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Teoretická časť (Kapitola 3.3.2, Krok 8) pokrýva analýzu súborového systému ako jednokrokový proces s rozhodnutím o stratégii obnovy.

Implementácia rozširuje tento krok o automatické načítanie cesty k forenzném obrazu z výstupu Kroku 6, multi-partičnú analýzu v jednej slučke, a identifikáciu obrazových súborov priamo z výstupu fls. Podpora superfloppy formátu (bez partičnej tabuľky) je kritická pre SD karty a USB flash disky, ktoré sú najčastejším zdrojom fotografií v forenznej praxi.