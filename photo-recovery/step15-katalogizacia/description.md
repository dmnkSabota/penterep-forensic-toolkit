# Detaily testu

## Úkol

Zozbierať všetky validné fotografie, organizovať ich do prehľadnej štruktúry a vytvoriť katalóg s metadátami pripravený na odovzdanie klientovi.

## Obtiažnosť

Stredná

## Časová náročnosť

45 minút

## Automatický test

Áno

## Popis

Katalogizácia je finálny organizačný krok pred vytvorením reportu. Systém konsoliduje validné fotografie z adresárov `validation/valid/` a `repair/repaired/`, priraďuje jednotné pomenovanie `{case_id}_{seq:04d}.{ext}`, vytvára 3 veľkosti thumbnailov (150 px, 300 px, 600 px) a generuje interaktívny HTML katalóg s vyhľadávaním, filtrovaním a lightboxom.

EXIF metadáta sú načítané z `exif_database.json` (ak existuje) – každý záznam sa matchuje podľa pôvodného názvu súboru. Výstupom je adresár `{case_id}_catalog/` kompletný na odovzdanie s `README.txt`.

Vstupom sú: `{case_id}_validation/valid/` (validné fotografie) a `{case_id}_repair/repaired/` (opravené fotografie). PIL/Pillow je povinný pre generovanie thumbnailov.

## Jak na to

**1. Zber fotografií:**

Systém rekurzívne prehľadá `validation/valid/` a `repair/repaired/`, skopíruje všetky obrazové súbory do `catalog/photos/` s jednotným pomenovaním a uloží mapovanie do `metadata/collection_index.json`.

**2. Tvorba thumbnailov:**

Pre každý súbor PIL vytvorí 3 veľkosti s LANCZOS resamplingom (quality=85, optimize=True). Thumbnaily sa uložia do `catalog/thumbnails/{small,medium,large}/`.

**3. Konsolidácia metadát:**

Systém načíta `exif_database.json` a namapuje EXIF záznamy podľa pôvodného názvu. Výstup: `metadata/complete_catalog.json` a `metadata/catalog.csv`.

**4. Tvorba indexov:**

Tri indexy: chronologický (podľa DateTimeOriginal), by_camera (zoskupené podľa Make+Model), GPS (len súbory s GPS súradnicami).

**5. HTML katalóg:**

`photo_catalog.html` s grid layoutom (medium thumbnaily), vyhľadávaním, filtrovaním podľa zdroja, triedením (ID, dátum, fotoaparát, MP) a lightbox modalom. Kompletne offline bez externých závislostí.

**6. Záverečný report:**

`catalog_summary.json` a `README.txt` so štatistikami a inštrukciami pre klienta.

## Výsledek

Adresár `{case_id}_catalog/` s: `photos/` (jednotné pomenovanie), `thumbnails/` (3 veľkosti), `metadata/` (JSON + CSV), `indexes/` (chronologický, camera, GPS), `photo_catalog.html` (interaktívny offline), `catalog_summary.json`, `README.txt`. Metriky: catalog completeness 100 %, EXIF coverage >90 %, thumbnail success >95 %.

## Reference

ISO/IEC 27037:2012 – Section 7.7 (Documentation)
NIST SP 800-86 – Section 3.3 (Reporting)
Dublin Core Metadata Standard

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

HTML katalóg nepoužíva žiadne externé CDN ani JavaScript knižnice – všetko je inline pre garantovanú offline funkčnosť. Thumbnaily sa konvertujú na JPEG bez ohľadu na pôvodný formát (PNG, TIFF, RAW) pre maximálnu kompatibilitu prehliadačov. PIL `Image.Resampling.LANCZOS` vyžaduje Pillow ≥ 9.1; pre staršie verzie treba použiť `Image.LANCZOS`.