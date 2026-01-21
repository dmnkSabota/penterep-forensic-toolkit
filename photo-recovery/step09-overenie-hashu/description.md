# Detaily testu

## Úkol

Automaticky porovnať hash hodnoty originálneho média a forenzného obrazu. Rozhodnúť o ďalšom postupe na základe zhody hashov.

## Obtiažnosť

Snadné

## Časová náročnosť

2

## Automatický test

Áno - Python skript porovná dva hashe a určí zhodu/nezhodu

## Popis

Overenie zhody hashov je finálny krok trojfázového procesu zabezpečenia integrity. Automatické porovnanie matematicky overí, že forenzný obraz je identický s originálnym médiom. Toto je kritický rozhodovací bod - len pri zhode hashov môžeme pokračovať s analýzou.

Prečo je tento krok kritický:
- Potvrdzuje, že imaging proces prebehol bez chýb
- Matematicky dokazuje, že obraz je presná kópia
- Zabezpečuje súdnu prípustnosť dôkazu
- Detekuje akékoľvek problémy pri vytváraní obrazu

ROZHODNUTIE: ÁNO (zhoda) → Krok 10 (Analýza FS), NIE (nezhoda) → Diagnostika → Návrat ku Kroku 5

## Jak na to

1. Načítaj hash originálneho média z Kroku 6
2. Načítaj hash forenzného obrazu z Kroku 8
3. Spusti automatické porovnanie - Python skript porovná oba hashe (porovnanie stringov)
4. Pri ZHODE (original_hash == image_hash): Integrita POTVRDENÁ → pokračuj Krokom 10, originál môžeš bezpečne odpojiť a zabezpečiť
5. Pri NEZHODE (original_hash != image_hash): Integrita ZLYHALA → diagnostikuj príčinu (vadné sektory, prerušené pripojenie, write-blocker zlyhal?), oprav problém, vráť sa na Krok 5
6. Maximálne 3 pokusy - ak 3× zlyhal, kontaktuj zodpovednú osobu

---

## Výsledek

Hashe porovnané. Pri zhode: Integrita potvrdená, pokračuj Krokom 10. Pri nezhode: Opakuj imaging proces (max 3 pokusy). Vygenerovaný verification report.

## Reference

NIST SP 800-86 - Section 3.1.2 (Data Integrity Verification)
ISO/IEC 27037:2012 - Section 7.2 (Verification procedures)
ACPO Good Practice Guide - Principle 3 (Audit trail)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
1. **Chyba počas imaging procesu**
   - I/O chyby
   - Prerušenie procesu
   - Nedostatok miesta na disku

2. **Poškodené médium**
   - Chybové sektory sa menili počas procesu
   - Nestabilné pripojenie

3. **Hardware problémy**
   - Chybný USB kábel
   - Problém s read/write head (HDD)

### Diagnostické kroky:
1. Skontrolovať logy z kroku 5 (imaging)
2. Overiť integritu obrazu súboru
3. Skontrolovať SMART status média
4. Otestovať hardware (káble, porty)

### Ďalší postup:
- **NÁVRAT ku kroku 5** - opakovať imaging
- Použiť iný nástroj (napr. ddrescue pre poškodené médiá)
- Dokumentovať všetky pokusy a výsledky

## Výstupný report
```json
{
  "verification_status": "PASS" | "FAIL",
  "case_id": "2026-01-21-001",
  "original_hash": "a1b2c3d4...",
  "image_hash": "a1b2c3d4...",
  "match": true | false,
  "timestamp": "2026-01-21T16:00:00Z",
  "action": "proceed_to_analysis" | "repeat_imaging"
}
```

## Právne dôsledky
- Zhoda hashov je právny dôkaz integrity
- V prípade rozdielu nemožno pokračovať v analýze
- Všetky pokusy musia byť dokumentované

## Chain of Custody
Tento krok je **kritický kontrolný bod**:
- Zaznamenať výsledok verifikácie
- Podpísať zodpovednou osobou
- Časová značka pre audit trail
