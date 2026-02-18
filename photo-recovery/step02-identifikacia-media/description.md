# Detaily testu

## Úkol

Identifikovať médium a vytvoriť fotodokumentáciu.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

15 minút

## Automatický test

Nie

## Popis

Identifikácia média je kritický krok, ktorý zabezpečuje jednoznačnú identifikáciu každého artefaktu v prípade a odlíšenie od iných médií v laboratóriu. Tento proces vytvára základnú dokumentáciu pre forenzný reťazec držania dôkazu (Chain of Custody) v súlade s ISO/IEC 27037:2012.

## Jak na to

**1. Fotodokumentácia:**

Vyhotovte komplexnú fotodokumentáciu média:
- Celkový záber s mierkou pre stanovenie veľkosti
- Šesť strán zariadenia: vrch (TOP), spodok (BOTTOM), predná strana (FRONT), zadná strana (BACK), ľavá strana (LEFT), pravá strana (RIGHT)
- Detailné makro zábery sériového čísla
- Detaily všetkých viditeľných poškodení alebo anomálií

**2. Fyzické identifikátory:**

Zaznamenajte do formulára:
- Výrobca (napr. SanDisk, Samsung, Kingston)
- Presné typové označenie modelu
- Kompletné sériové číslo
- Farba púzdra a materiál (plast, kov, keramika)
- Presné rozmery v mm (dĺžka × šírka × výška) - merajte posuvným meradlom
- Kapacita z nálepky zariadenia

**3. Fyzický stav média:**

Zdokumentujte:
- Celkový stav: nové / mierne použité / intenzívne použité / poškodené
- Stav štítkov a nálepiek: nepoškodené / opotrebované / chýbajúce / zmenené
- Viditeľné stopy používania: škrabance, odtlačky prstov, znečistenie, zmeny farby

**4. Fyzické poškodenie (ak je prítomné):**

Detailne popíšte:
- Typ poškodenia: prasklina púzdra, zlomený konektor, deformácia, vypálené komponenty, korózia kontaktov
- Presná lokalizácia na zariadení
- Závažnosť:
  - Malé (kozmetické, nefunkčné)
  - Stredné (čiastočne funkčné, vyžaduje opravu)
  - Kritické (znemožňuje pripojenie)

**5. Technická detekcia (ak je médium čitateľné):**

Ak médium umožňuje pripojenie cez write-blocker a systém ho rozpoznáva:
- `lsblk` - zobrazenie blokovej štruktúry
- `blkid` - identifikácia súborového systému a partícií
- `smartctl` - čítanie SMART údajov (ak sú dostupné)

Zaznamenajte výstupy týchto nástrojov.

**6. Fyzické označenie:**

Vytvorte fyzický štítok s Case ID a nalepte ho na médium tak, aby:
- Nezasahoval do konektorov
- Neprekrýval sériové číslo
- Nepoškodil pôvodné výrobné nálepky

**7. Archivácia:**

Archivujte všetky fotografie a záznamy do dokumentácie Case.

## Výsledek

Médium je identifikované a zdokumentované:
- Fotodokumentácia (minimálne 8 fotografií: celkový záber, 6 strán, detail SN, detaily poškodení)
- Vyplnený identifikačný formulár s kompletnými fyzickými a technickými parametrami
- Fyzický štítok s Case ID nalepený na médium
- Výstupy technických nástrojov (ak bolo médium čitateľné)

Workflow postupuje do rozhodovacieho bodu "Je médium čitateľné?".

## Reference

ISO/IEC 27037:2012 - Section 5.2 (Identification of digital evidence)
NIST SP 800-86 - Section 3.1.1 (Collection Phase - Documentation)
ACPO Good Practice Guide - Principle 2 (Recording and preservation)

## Stav

K otestovaniu

## Nález

(prázdne - vyplní sa po teste)

------------------------------------------------------------------------
## Poznámky k implementácii

**Praktické rozšírenia oproti teoretickému návrhu v diplomovej práci:**

Teoretická časť (Kapitola 3.3.2, Krok 4) uvádza:
- Fyzický popis (typ, výrobca, model, viditeľné poškodenie)
- Technické identifikátory (sériové čísla)
- Fotodokumentácia zariadenia zo všetkých strán

**Implementácia rozširuje tento krok o:**

1. **Detailný protokol fotodokumentácie** - presná špecifikácia 6 strán + celkový záber + makro detaily
2. **Meranie presných rozmerov** - použitie posuvného meradla pre presné technické údaje
3. **Klasifikácia fyzického stavu** - štandardizované kategórie (nové/použité/poškodené)
4. **Klasifikácia závažnosti poškodení** - trojstupňová škála (malé/stredné/kritické) pre rozhodovanie o fyzickej oprave
5. **Technická detekcia nástrojmi** - lsblk, blkid, smartctl pre získanie doplňujúcich technických informácií
6. **Fyzické označenie štítkom** - Chain of Custody prvok prevzatý zo scenára 1 (Policajný výsluch)
7. **Štruktúrované podkroky 1-7** - detailný návod na vykonanie kroku v praxi

Tieto rozšírenia budú doplnené do implementačnej kapitoly diplomovej práce s odôvodnením ich potreby pre jednoznačnú identifikáciu médií a štandardizáciu procesu dokumentácie v laboratórnom prostredí.