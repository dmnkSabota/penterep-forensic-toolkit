# Detaily testu

## Úkol

Spojiť obnovené fotografie z filesystem recovery a file carvingu do jedného deduplikovaného datasetu a vytvoriť master katalóg.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

30 minút

## Automatický test

Áno

## Popis

Recovery consolidation je proces zjednotenia výsledkov z rôznych metód obnovy do jedného organizovaného datasetu. V závislosti od použitej stratégie máme výstupy z Kroku 9 (FS-based recovery), Kroku 10 (file carving), alebo z oboch pri hybridnej metóde.

Kľúčovým prvkom je SHA-256 deduplikácia naprieč zdrojmi – FS-based recovery a file carving môžu obnoviť identické súbory, pretože oba pristupujú k rovnakým dátam na médiu. Pri konflikte má FS-based kópia prioritu, pretože zachováva pôvodný názov a FS timestamps. Typicky 15–25 % súborov pri hybridnom prístupe sú duplikáty. Výsledkom je master katalóg (JSON) s kompletným inventárom všetkých súborov a štatistikami.

## Jak na to

**1. Detekcia zdrojov:**

Systém overí existenciu `{case_id}_recovered/` (Krok 9) a `{case_id}_carved/organized/` (Krok 10). Ak žiadny zdroj neexistuje, skript odmietne pokračovať.

**2. Inventarizácia:**

Pre každý zdroj systém rekurzívne naskenuje obrazové súbory (`.jpg`, `.png`, `.raw` a ďalšie) a zaznamenáva cestu, veľkosť, príponu a zdroj (`fs_based` / `carved`).

**3. SHA-256 hashovanie a deduplikácia:**

Pre každý súbor sa vypočíta SHA-256 odtlačok. Ak rovnaký hash existuje v oboch zdrojoch, FS-based kópia zostane a carved kópia sa presunie do `duplicates/` pre auditný zámer.

**4. Kopírovanie a organizácia:**

Unikátne súbory sa skopírujú do `{case_id}_consolidated/`. FS-based súbory zachovávajú pôvodný názov (s kolíznou ochranou), carved súbory dostanú systematický názov `{case_id}_{typ}_{seq:06d}.ext`. Oba zdroje sa triedia do podadresárov podľa formátu (`jpg/`, `png/`, `tiff/`, `raw/`, `other/`).

**5. Master katalóg:**

Systém uloží `master_catalog.json` s kompletným inventárom (ID, názov, hash, veľkosť, formát, zdroj, cesta) a štatistikami. Textový report `CONSOLIDATION_REPORT.txt` obsahuje prehľad pre klienta.

## Výsledek

Konsolidovaný dataset v `{case_id}_consolidated/`: `fs_based/` a `carved/` s podadresármi podľa formátu, `duplicates/` pre auditné kópie. `master_catalog.json` obsahuje kompletný inventár. Štatistiky: celkový počet, z FS-based, z file carving, počet odstránených duplikátov, veľkosť datasetu. Workflow pokračuje do Kroku 12 (EXIF analýza).

## Reference

ISO/IEC 27037:2012 – Section 7.3 (Data consolidation)
NIST SP 800-86 – Section 3.1.3 (Analysis)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Skript číta z `{case_id}_recovered/` a `{case_id}_carved/organized/` – oba sú výstupy predchádzajúcich krokov. Kopíruje (nie presúva) súbory z pôvodných adresárov, čím zachováva forenzné originály. Duplikáty sa tiež len kopírujú do `duplicates/` – nie mažú – aby bola k dispozícii auditná stopa.

Priority pravidlo pri dedupu je zámerné: FS-based kópia má pôvodný názov a FS timestamps, čo je cennejšie pre forenzný report ako systematicky premenovaná carved kópia s rovnakým obsahom.