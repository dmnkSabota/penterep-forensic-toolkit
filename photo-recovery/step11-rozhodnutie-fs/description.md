# Detaily testu

## Úkol

Na základe výsledkov analýzy súborového systému (krok 10) rozhodnúť, ktorá stratégia obnovy bude použitá: File System-Based Recovery (krok 12A) alebo File Carving (krok 12B).

## Obtiažnosť

Snadné

## Časová náročnosť

1

## Automatický test

Áno - Python skript automaticky vyhodnotí podmienky (FS rozpoznaný, adresáre čitateľné, súbory nájdené) a zvolí optimálnu stratégiu obnovy

## Popis

Toto je kritický rozhodovací bod vo workflow, ktorý určuje celý ďalší priebeh obnovy fotografií. Rozhodnutie je založené na troch kľúčových otázkach: Je súborový systém rozpoznaný? Je adresárová štruktúra čitateľná? Sú viditeľné nejaké súbory?

Prečo je tento krok kritický:
- Určuje, či môžeme zachovať pôvodné názvy súborov a adresárovú štruktúru
- Určuje, či môžeme zachovať časové značky a EXIF metadáta
- Ovplyvňuje rýchlosť obnovy (FS-based = rýchlejšie, file carving = pomalšie)
- Ovplyvňuje kvalitu výsledkov (FS-based = vyššia kvalita s metadátami)
- Pri optimálnom stave (FS rozpoznaný + adresáre čitateľné) → krok 12A
- Pri probléme (FS poškodený alebo nerozpoznaný) → krok 12B

Automatická rozhodovacia logika vyhodnotí 4 možné scenáre: Ideálny stav (všetko funguje), Formátované médium (prázdny FS), Poškodený FS (nečitateľné adresáre), Nerozpoznaný FS (neznámy typ).

## Jak na to

1. VSTUP - načítaj JSON výsledky z kroku 10 (fs_recognized, directory_readable, file_count, image_count)
2. PRAVIDLO 1 - ak FS rozpoznaný AND adresáre čitateľné AND súbory nájdené (file_count > 0) → stratégia "filesystem_based" → krok 12A
3. PRAVIDLO 2 - ak FS rozpoznaný AND adresáre čitateľné BUT žiadne súbory (file_count = 0) → pravdepodobne formátované médium → stratégia "file_carving" → krok 12B
4. PRAVIDLO 3 - ak FS rozpoznaný BUT adresáre NEČITATEĽNÉ → poškodený FS → stratégia "file_carving" → krok 12B
5. PRAVIDLO 4 - ak FS NEROZPOZNANÝ → stratégia "file_carving" agresívny režim → krok 12B
6. VÝSTUP - ulož rozhodnutie do JSON (stratégia, ďalší krok, dôvod, očakávaná kvalita, očakávaná rýchlosť, čo sa zachová/stratí)

---

## Výsledek

Automaticky určená stratégia obnovy s odôvodnením. Pri FS-based recovery (krok 12A): zachová názvy, adresáre, časové značky, EXIF, rýchlejšia obnova. Pri File Carving (krok 12B): stratia sa názvy a časové značky, pomalšia obnova, ale funguje aj pri poškodenom FS. Rozhodnutie s istotou (high/medium/low) a odporúčaním ďalšieho kroku. Pri manuálnom prepísaní automatického rozhodnutia vyžaduje sa odôvodnenie a schválenie.

## Reference

ISO/IEC 27037:2012 - Section 7.2 (Analysis methodology)
NIST SP 800-86 - Section 3.1.2.1 (File System Analysis)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
- Hľadá súbory podľa signatúr

**Nevýhody:**
- Obnovené súbory nemajú pôvodné názvy
- Stratená štruktúra adresárov
- Pomalší proces

**Nástroje:**
- PhotoRec
- Scalpel
- Foremost

## Automatizovaná logika

```python
def decide_recovery_method(fs_analysis):
    """
    Rozhodnutie na základe analýzy z kroku 10
    """
    if fs_analysis['state'] == 'RECOGNIZED':
        return {
            'method': 'filesystem_scan',
            'next_step': '12A',
            'tool': 'fls_icat',
            'reason': 'Filesystem je rozpoznaný a čitateľný'
        }
    
    elif fs_analysis['state'] == 'DAMAGED':
        return {
            'method': 'hybrid',
            'next_step': '12A+12B',
            'tool': 'fls_icat + photorec',
            'reason': 'Poškodený FS - použiť obe metódy'
        }
    
    else:  # UNRECOGNIZED
        return {
            'method': 'file_carving',
            'next_step': '12B',
            'tool': 'photorec',
            'reason': 'FS nerozpoznaný - použiť signature carving'
        }
```

## Hybridný prístup
V prípade **poškodeného** FS:
1. Najprv skúsiť krok 12A (získať čo sa dá cez FS)
2. Potom spustiť krok 12B (carving pre zvyšok)
3. Deduplicovať výsledky

## Výstupný report
```json
{
  "case_id": "2026-01-21-001",
  "decision": {
    "method": "filesystem_scan",
    "next_step": "12A",
    "tools": ["fls", "icat"],
    "reasoning": "FAT32 filesystem fully recognized",
    "expected_success_rate": "high"
  },
  "timestamp": "2026-01-21T16:20:00Z"
}
```

## Špeciálne prípady

### Viacero partícií
- Každá partícia sa analyzuje samostatne
- Rôzne partície môžu použiť rôzne metódy

### Šifrované partície
- Najprv dešifrovať (vyžaduje kľúč)
- Potom analyzovať FS

### RAID
- Rekonštruovať RAID
- Potom analyzovať FS

## Poznámky
- Rozhodnutie je plne automatizované
- Možnosť manuálneho override pre špecifické prípady
- Dokumentovať dôvod rozhodnutia pre audit trail
