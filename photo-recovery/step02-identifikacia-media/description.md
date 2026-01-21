# Detaily testu

## Úkol

Vykonať komplexnú identifikáciu úložného média s fotodokumentáciou podľa ISO/IEC 27037:2012 požiadaviek. Zaznamenať všetky fyzické a technické identifikátory potrebné pre Chain of Custody.

## Obtiažnosť

Snadné

## Časová náročnosť

15

## Automatický test

(prázdne - manuálny krok, možná budúca čiastočná automatizácia)

## Popis

Identifikácia média je kritický krok, ktorý zabezpečuje, že každý artefakt v prípade môže byť jednoznačne identifikovaný a odlíšený od iných médií v laboratóriu. Tento proces vytvára základnú dokumentáciu pre forenzný reťazec držania dôkazu (Chain of Custody).

Prečo je tento krok kritický:
- Fyzické identifikátory (sériové číslo, štítky) sú jedinečné pre každé médium
- Fotodokumentácia poskytuje vizuálny záznam stavu média pri prijatí
- Technické parametre sú potrebné pre výber správnej stratégie obnovy
- Dokumentácia viditeľného poškodenia je dôležitá pre hodnotenie úspešnosti
- Informácie o výrobcovi a modeli pomáhajú identifikovať známe problémy

## Jak na to

1. Vyhotov fotodokumentáciu média - celkový záber s mierkou, 6 strán (TOP, BOTTOM, FRONT, BACK, LEFT, RIGHT), detail sériového čísla a viditeľného poškodenia
2. Zaznamenaj fyzické identifikátory - výrobca, model, sériové číslo, farba, materiál púzdra
3. Zmeraj a zaznamej rozmery média (dĺžka, šírka, výška v mm) a kapacitu z nálepky
4. Zdokumentuj fyzický stav - celkový stav, stav nálepiek, stopy používania
5. Pri viditeľnom poškodení popíš typ, lokalizáciu a závažnosť poškodenia
6. Ak je médium pripojiteľné cez write-blocker, vykonaj automatickú detekciu (lsblk, blkid, smartctl)

---

## Výsledek

Médium identifikované a zdokumentované. Vytvorená fotodokumentácia (minimálne 8 fotografií), identifikačný formulár a fyzický štítok s Case ID prilepený na médium.

## Reference

ISO/IEC 27037:2012 - Section 5.2 (Identification of digital evidence)
NIST SP 800-86 - Section 3.1.1 (Collection Phase - Documentation)
ACPO Good Practice Guide - Principle 2 (Recording and preservation)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
