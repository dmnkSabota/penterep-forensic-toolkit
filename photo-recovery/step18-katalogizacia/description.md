# Detaily testu

## Úkol

Zozbierať všetky validné fotografie, organizovať ich do prehľadnej štruktúry, vytvoriť katalóg s metadata a pripraviť ich na odovzdanie klientovi.

## Obtiažnosť

Střední

## Časová náročnosť

45

## Automatický test

Áno

## Popis

Katalogizácia je finálny organizačný krok pred vytvorením reportu. Cieľom je systematicky usporiadať všetky validné fotografie, priradiť jednotné pomenovanie, vytvoriť náhľady a pripraviť komplexný katalóg s metadátami.

Prečo je tento krok kritický:
- Poskytuje klientovi prehľadný katalóg všetkých obnovených fotografií
- Umožňuje rýchlu navigáciu cez thumbnaily a vyhľadávanie
- Zachováva všetky metadata (EXIF, GPS, camera info) v prehľadnej forme
- Vytvára chronologický timeline a indexy podľa fotoaparátu
- Pripravuje fotografie na delivery v profesionálnej forme

Katalogizácia konsoliduje validné fotografie, vytvára 3 veľkosti thumbnailov (150x150, 300x300, 600x600), extrahuje kompletné EXIF metadata (cieľ >90% pokrytie), generuje interaktívny HTML katalóg s vyhľadávaním a filtrovaním.

## Jak na to

1. ZBER FOTOGRAFIÍ - identifikuj zdroje: validation/valid/ z kroku 15, repair/repaired/ z kroku 17 (ak existuje), skopíruj do catalog/photos/ s jednotným pomenovaním CASEID_0001.jpg až CASEID_NNNN.jpg, zachovaj mapovanie v collection_index.json
2. THUMBNAILY - Python PIL vytvor 3 veľkosti (small 150px, medium 300px, large 600px), LANCZOS resampling, quality=85 optimize=True, ulož do catalog/thumbnails/{size}/, vytvor thumbnail_index.json
3. METADATA - načítaj EXIF data z kroku 14, konsoliduj s validation a repair info, vytvor metadata_catalog.json a CSV pre Excel
4. INDEXY - chronologický (podľa DateTimeOriginal), by_camera (zoskupené podľa fotoaparátu), GPS (len s GPS súradnicami), ulož do catalog/indexes/
5. HTML KATALÓG - interaktívny photo_catalog.html: grid layout s medium thumbnailami, vyhľadávanie, filtrovanie, lightbox modal, responzívny dizajn
6. FINÁLNY REPORT - vytvor catalog_summary.json: počet fotografií, metadata coverage, date range, zoznam fotoaparátov, completeness 100%

---

## Výsledek

Komplexný katalóg všetkých validných fotografií. Štruktúra: catalog/photos/ (jednotné pomenovanie), catalog/thumbnails/ (3 veľkosti), catalog/metadata/ (JSON a CSV), catalog/indexes/ (chronologický, camera, GPS), photo_catalog.html (interaktívny). Metriky: catalog completeness 100%, metadata coverage >90%, thumbnail success rate >95%, 2-3 fotoaparáty detekované. HTML funkcie: search, filter by camera, sort by date/ID, lightbox view, responsive, offline. Delivery package pripravený na odovzdanie s README.

## Reference

ISO/IEC 27037:2012 - Section 7.7 (Documentation)
NIST SP 800-86 - Section 3.3 (Reporting)
Dublin Core Metadata Standard

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)