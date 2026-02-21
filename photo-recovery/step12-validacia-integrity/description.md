# Detaily testu

## Úkol

Overiť fyzickú integritu všetkých obnovených fotografií a rozdeliť ich do kategórií: validné, poškodené a neopraviteľné.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

30 minút

## Automatický test

Áno

## Popis

Validácia integrity overuje, či sú obnovené súbory skutočne otvárateľné a funkčné. Nie všetky obnovené fotografie sú nutne plne funkčné – môžu byť čiastočne prepísané, fragmentované alebo ide o false positives z file carvingu. Súbory z filesystem-based recovery majú typicky integritu >95 %, súbory z file carvingu 70–85 %. Vymazané súbory majú nižšiu integritu než aktívne, keďže mohli byť čiastočne prepísané.

Systém používa multi-tool prístup: kontrola magic bytes a MIME typu, ImageMagick `identify`, PIL `verify()` + `load()`, a format-specific nástroje (`jpeginfo`, `pngcheck`). Rozhodovacia logika je: ak všetky nástroje prešli → validný, ak aspoň jeden prešiel → poškodený (potenciálne opraviteľný), ak všetky zlyhali → neopraviteľný. Poškodené súbory sú klasifikované podľa typu (truncated, invalid_header, corrupt_segments, corrupt_data) a úrovne opraviteľnosti (L1–L5).

Predpokladom je existencia `master_catalog.json` a nainštalovaná knižnica PIL/Pillow.

## Jak na to

**1. Načítanie master katalógu:**

Systém načíta `{case_id}_consolidated/master_catalog.json` a získa zoznam všetkých konsolidovaných súborov na validáciu.

**2. Kontrola nástrojov:**

PIL/Pillow je povinný (`pip install Pillow`). Voliteľné: `identify` (ImageMagick), `file`, `jpeginfo`, `pngcheck` – systém použije všetky dostupné.

**3. Per-file multi-tool validácia:**

Pre každý súbor systém postupne overí: veľkosť (prázdne súbory = neopraviteľné), magic bytes (JPEG=FFD8FF, PNG=89504E47), MIME typ cez `file -b --mime-type`, štruktúru cez `identify`, čitateľnosť pixelov cez PIL `verify()` + `load()`, a pre JPEG/PNG aj `jpeginfo -c` / `pngcheck -v`.

**4. Organizácia výstupov:**

Súbory sa skopírujú do `{case_id}_validation/valid/`, `corrupted/` alebo `unrecoverable/`. Zdrojové súbory v konsolidovanom adresári zostávajú nedotknuté.

**5. Analýza poškodení a report:**

Pre každý poškodený súbor systém určí typ chyby a úroveň opraviteľnosti. Výstupom sú `{case_id}_validation_report.json` a `VALIDATION_REPORT.txt` so štatistikami a zoznamom súborov odporúčaných na opravu.

## Výsledek

Klasifikácia všetkých fotografií do troch kategórií s integrity score (% validných). Štatistiky podľa formátu a zdroja (fs_based vs carved). Typ a úroveň poškodenia pre každý corrupted súbor: L1 truncated (ľahko opraviteľné), L2 invalid_header/corrupt_segments (opraviteľné), L3 corrupt_data (čiastočne), L4 fragmented (manuálne), L5 false_positive (zahodiť). Výstupné adresáre: `valid/`, `corrupted/`, `unrecoverable/`.

## Reference

ISO/IEC 10918-1 – JPEG Standard
PNG Specification – ISO/IEC 15948:2004
NIST SP 800-86 – Section 3.1.3 (Data Validation)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Poradie nástrojov v pipeline je zámerné: magic bytes a `file` sú rýchle a odfiltrovávajú zjavné false positives pred pomalšími nástrojmi. PIL `verify()` spotrebuje file handle – po nej je nutné súbor znovu otvoriť pred `load()`. Kolízna ochrana pri kopírovaní (`_1`, `_2` sufixy) je nevyhnutná pri súboroch s rovnakými názvami z rôznych zdrojov.