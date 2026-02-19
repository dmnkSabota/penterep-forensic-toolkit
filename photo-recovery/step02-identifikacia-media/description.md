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

Fyzická identifikácia média zabezpečuje jeho jednoznačné odlíšenie od ostatných artefaktov v laboratóriu a vytvára základ pre Chain of Custody dokumentáciu v súlade s ISO/IEC 27037:2012. Všetky záznamy z tohto kroku sú priamo prepojené s Case ID z kroku 1.

## Jak na to

**1. Fotodokumentácia:**

Vyhotovte komplexnú fotodokumentáciu média – minimálne 8 záberov:
- Celkový záber s mierkou
- Šesť strán zariadenia: vrch, spodok, predná strana, zadná strana, ľavá, pravá
- Makro detail sériového čísla
- Detail každého viditeľného poškodenia alebo anomálie

**2. Fyzické identifikátory:**

Zaznamenajte do formulára: výrobcu, typové označenie modelu, úplné sériové číslo, farbu a materiál púzdra, presné rozmery v mm (merajte posuvným meradlom) a kapacitu z nálepky zariadenia.

**3. Fyzický stav média:**

Zdokumentujte celkový stav zariadenia (nové / mierne použité / intenzívne použité / poškodené), stav nálepiek a štítkov, a viditeľné stopy používania – škrabance, znečistenie, zmeny farby.

**4. Fyzické poškodenie (ak je prítomné):**

Detailne popíšte typ poškodenia (prasklina púzdra, zlomený konektor, deformácia, korózia kontaktov), presnú lokalizáciu na zariadení a závažnosť:
- Malé – kozmetické, funkčnosť neovplyvnená
- Stredné – čiastočne funkčné, vyžaduje opravu
- Kritické – znemožňuje pripojenie

Klasifikácia závažnosti poškodenia priamo vstupuje do rozhodovacieho bodu v kroku 3.

**5. Fyzické označenie:**

Nalepte štítok s Case ID na médium – nie na konektor, nie cez sériové číslo, nie cez pôvodné výrobné nálepky.

**6. Archivácia:**

Všetky fotografie a formuláre uložte do dokumentácie Case pod príslušným Case ID.

## Výsledek

Médium je identifikované a zdokumentované. Vytvorené výstupy:
- Fotodokumentácia (minimálne 8 fotografií)
- Identifikačný formulár s kompletnými fyzickými parametrami
- Fyzický štítok s Case ID nalepený na médium

Workflow postupuje do kroku 3 "Je médium čitateľné?".

## Reference

ISO/IEC 27037:2012 – Section 5.2 (Identification of digital evidence)
NIST SP 800-86 – Section 3.1.1 (Collection Phase – Documentation)
ACPO Good Practice Guide – Principle 2 (Recording and preservation)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Teoretická časť (Kapitola 3.3.2, Krok 4) pokrýva fyzický popis, sériové čísla a fotodokumentáciu zo všetkých strán. Implementácia tieto požiadavky zachováva a dopĺňa o niekoľko praktických prvkov.

Presné meranie rozmerov posuvným meradlom a štandardizovaná klasifikácia fyzického stavu (nové / použité / poškodené) pridávajú technickú presnosť, ktorá je pri laboratórnej práci s viacerými médiami naraz nevyhnutná. Trojstupňová škála závažnosti poškodení (malé / stredné / kritické) priamo podporuje rozhodovanie v nasledujúcom kroku. Fyzické označenie štítkom je prevzaté zo scenára 1 a zabezpečuje jednoznačnú identifikáciu média počas celého priebehu prípadu. Technická detekcia nástrojmi je zámerene presunutá do kroku 3, kde sa čitateľnosť priamo overuje a výstupy majú okamžitý kontext.

Tieto rozšírenia budú zdôvodnené v implementačnej kapitole diplomovej práce.