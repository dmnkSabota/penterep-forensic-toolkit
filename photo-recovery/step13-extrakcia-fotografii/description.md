# Detaily testu

## Úkol

Konsolidovať výstupy z krokov 12A (FS-based recovery) a/alebo 12B (file carving) do jedného organizovaného datasetu obnovených fotografií s master katalógom.

## Obtiažnosť

Snadné

## Časová náročnosť

30

## Automatický test

Áno

## Popis

Extrakcia a konsolidácia je proces zjednotenia výsledkov z rôznych metód obnovy do jedného organizovaného datasetu. V závislosti od použitých krokov máme výstupy buď z kroku 12A (FS-based), alebo z kroku 12B (file carving), alebo z oboch (hybridná stratégia).

Prečo je tento krok kritický:
- Zjednotenie výsledkov z rôznych metód do jedného miesta
- Odstránenie duplikátov (FS-based a carving môžu nájsť tie isté súbory)
- Vytvorenie master katalógu so všetkými metadátami
- Štandardizácia názvov a organizácie súborov
- Príprava pre ďalšie kroky (EXIF analýza, validácia)
- Štatistiky: koľko súborov z každej metódy, koľko duplikátov

V prípade hybridnej stratégie: súbory z FS-based majú prioritu (zachované názvy a metadáta), carved súbory dopĺňajú čo FS-based nenašlo. Typicky 15-25% duplikátov pri hybridnom prístupe.

## Jak na to

1. ZBER ZDROJOV - identifikuj ktoré recovery adresáre existujú ({case_id}_recovered/ z kroku 12A, {case_id}_carved/ z kroku 12B), naskenuj všetky obrazové súbory v každom zdroji
2. INVENTARIZÁCIA - pre každý súbor: vypočítaj SHA-256 hash, zisti veľkosť, typ (MIME), zaznamenaj zdroj (fs_based alebo file_carving), načítaj existujúce metadáta ak sú dostupné
3. DETEKCIA DUPLIKÁTOV - porovnaj hashe medzi zdrojmi, ak hash existuje v oboch → je to duplikát, označ ktorý zachovať (fs_based má prioritu kvôli zachovaným názvom)
4. KOPÍROVANIE - skopíruj všetky unikátne súbory do consolidated/ adresára, zachovaj pôvodný názov ak je z FS-based, použij systematický názov ak je carved
5. ORGANIZÁCIA - vytvor podadresáre: fs_based/ (zachované názvy a štruktúra), carved/ (carved súbory), duplicates/ (odstránené duplikáty pre audit), roztrieď podľa typu (jpg/, png/, raw/)
6. KATALOGIZÁCIA - vytvor master_catalog.json s kompletným zoznamom: ID, názov, hash, veľkosť, typ, zdroj, cesta, EXIF preview, štatistiky (total, z FS, z carving, duplikáty odstránené)

---

## Výsledek

Konsolidovaný dataset obnovených fotografií v štruktúrovanej organizácii. Master katalóg (JSON) obsahuje kompletný inventár všetkých súborov s metadátami. Štatistiky: celkový počet obnovených, z FS-based recovery, z file carving, počet odstránených duplikátov. Pri hybridnej stratégii typicky 15-25% duplikátov. Súbory pripravené pre ďalšie kroky - EXIF analýza a validácia integrity. Výstupná štruktúra: consolidated/fs_based/, consolidated/carved/, consolidated/duplicates/, master_catalog.json.

## Reference

ISO/IEC 27037:2012 - Section 7.3 (Data consolidation)
NIST SP 800-86 - Section 3.1.3 (Analysis)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)