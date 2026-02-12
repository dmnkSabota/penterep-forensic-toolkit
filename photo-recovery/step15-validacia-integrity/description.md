# Detaily testu

## Úkol

Overiť fyzickú integritu všetkých obnovených fotografií a rozdeliť ich do kategórií: validné (plne funkčné), poškodené (čiastočne čitateľné, opraviteľné), neopraviteľné (nekompletné, false positives).

## Obtiažnosť

Snadné

## Časová náročnosť

30

## Automatický test

Áno

## Popis

Validácia integrity je kritický krok pred odovzdaním fotografií klientovi. Nie všetky obnovené súbory sú nutne plne funkčné - môžu byť čiastočne prepísané, fragmentované alebo false positives z file carvingu.

Prečo je tento krok kritický:
- Overenie že fotografie sú skutočne otvárateľné a funkčné
- Identifikácia poškodených súborov ktoré potrebujú opravu (krok 17)
- Eliminácia false positives (súbory ktoré nie sú fotografie)
- Kategorizácia pre ďalšie kroky (validné → katalogizácia, poškodené → oprava)
- Pri FS-based (12A) očakávame >95% validných, pri File Carving (12B) 70-85%
- Vymazané súbory majú nižšiu integritu než aktívne (čiastočne prepísané)

Typy poškodenia: chybný header (opraviteľné), chybný footer (opraviteľné), stredové bloky poškodené (čiastočne opraviteľné), fragmentácia (ťažké), false positive (neopraviteľné), nekompletný súbor (zriedka opraviteľné). Používame multi-tool approach: ImageMagick + PIL + format-specific (jpeginfo, pngcheck).

## Jak na to

1. ZÁKLADNÁ VALIDÁCIA - načítaj master_catalog.json z Kroku 13, pre každý súbor: `file` command (MIME type check), magic bytes signature (JPEG=FFD8FF, PNG=89504E47), kontrola veľkosti (vyraď prázdne)
2. DETAILNÁ VALIDÁCIA - spusti `identify -verbose` z ImageMagick (test štruktúry), Python PIL `Image.open()` + `verify()` + `load()` (test dekódovania pixelov), format-specific: `jpeginfo -c` pre JPEG, `pngcheck -v` pre PNG
3. ROZHODOVACIA LOGIKA - ak všetky nástroje OK → validný, ak aspoň jeden nástroj OK → poškodený (opraviteľný), ak všetky FAIL → neopraviteľný, zaznamenaj typ chyby (truncated, corrupt_data, invalid_header)
4. KATEGORIZÁCIA - skopíruj súbory do: validation/valid/ (plne funkčné), validation/corrupted/ (pokus o opravu v kroku 17), validation/unrecoverable/ (false positives)
5. ANALÝZA POŠKODENÍ - pre poškodené súbory identifikuj typ chyby z error messages, urči opraviteľnosť (Level 1: header/footer = ľahko, Level 2: segments = stredne, Level 3: pixel data = čiastočne)
6. ŠTATISTIKY - vypočítaj integrity score (% validných), porovnaj aktívne vs vymazané (ak 12A), vytvor JSON report, ulož zoznam opraviteľných pre krok 17

---

## Výsledek

Klasifikácia všetkých fotografií. Štatistiky: počet validných (cieľ >90%), poškodených (opraviteľných), neopraviteľných (false positives). Integrity score: % validných (FS-based >95%, File Carving 70-85%). Porovnanie aktívne vs vymazané: aktívne ~99% validné, vymazané ~78% (čiastočne prepísané). Analýza typov poškodení: truncated files, invalid segments, corrupt data. Organizované adresáre: validation/valid/, validation/corrupted/, validation/unrecoverable/. Report obsahuje pre každý poškodený súbor: typ chyby, nástroj ktorý detekoval, opraviteľnosť, odporúčanú techniku opravy.

## Reference

ISO/IEC 10918-1 - JPEG Standard
PNG Specification - ISO/IEC 15948:2004
NIST SP 800-86 - Section 3.1.3 (Data Validation)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)