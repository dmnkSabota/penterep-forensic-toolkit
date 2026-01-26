# Detaily testu

## Úkol

Identifikovať médium a vytvoriť fotodokumentáciu.

## Obtiažnosť

Snadné

## Časová náročnosť

15

## Automatický test

Nie

## Popis

Identifikácia média je kritický krok, ktorý zabezpečuje, že každý artefakt v prípade môže byť jednoznačne identifikovaný a odlíšený od iných médií v laboratóriu. Tento proces vytvára základnú dokumentáciu pre forenzný reťazec držania dôkazu (Chain of Custody). Fyzické identifikátory ako sériové číslo sú jedinečné pre každé médium, fotodokumentácia poskytuje vizuálny záznam stavu pri prijatí, a technické parametre sú potrebné pre výber správnej stratégie obnovy.

## Jak na to

Vyhotovte komplexnú fotodokumentáciu média. Začnite celkovým záberom s mierkou pre stanovenie veľkosti, následne odfotografujte všetkých šesť strán zariadenia - vrch (TOP), spodok (BOTTOM), prednú stranu (FRONT), zadnú stranu (BACK), ľavú stranu (LEFT) a pravú stranu (RIGHT). Vytvorte detailné makro zábery sériového čísla a všetkých viditeľných poškodení alebo anomálií.

Zaznamenajte fyzické identifikátory média do formulára. Zapíšte výrobcu (napríklad SanDisk, Samsung, Kingston), presné typové označenie modelu, kompletné sériové číslo bez skratiek, farbu púzdra a použitý materiál (plast, kov, keramika). Zmerajte presné rozmery média posuvným meradlom - dĺžka, šírka a výška v milimetroch. Zapíšte kapacitu z nálepky zariadenia (nie odhadovanú kapacitu od klienta).

Zdokumentujte fyzický stav média. Popíšte celkový stav ako nové, mierne použité, intenzívne použité alebo poškodené. Zaznamenajte stav originálnych štítkov a nálepiek - nepoškodené, opotrebované, chýbajúce alebo zmenené. Všimnite si viditeľné stopy používania ako škrabance, odtlačky prstov, znečistenie alebo zmeny farby.

Ak je prítomné viditeľné fyzické poškodenie, detailne ho popíšte. Špecifikujte typ poškodenia (prasklina púzdra, zlomený konektor, deformácia, vypálené komponenty, korózia kontaktov), presnú lokalizáciu na zariadení a závažnosť - malé (kozmetické, nefunkčné), stredné (čiastočne funkčné, vyžaduje opravu) alebo kritické (znemožňuje pripojenie).

Ak je médium v stave umožňujúcom pripojenie cez write-blocker a systém ho rozpoznáva, vykonajte automatickú technickú detekciu. Použite nástroje ako lsblk na zobrazenie blokovej štruktúry, blkid pre identifikáciu súborového systému a partícií, a smartctl pre čítanie SMART údajov ak sú dostupné. Zaznamenajte výstupy týchto nástrojov.

Vytvorte fyzický štítok s Case ID a nalepte ho na médium na miesto, kde nebude zasahovať do konektorov, nebude prekrývať sériové číslo ani nepoškodí pôvodné výrobné nálepky. Archivujte všetky fotografie a záznamy do dokumentácie Case.

## Výsledek

Médium je identifikované a zdokumentované. Vytvorená fotodokumentácia obsahuje minimálne 8 kvalitných fotografií (celkový záber, 6 strán, detail sériového čísla, detaily poškodení ak sú prítomné). Vyplnený identifikačný formulár s kompletným fyzickými a technickými parametrami. Na médium je prilepený fyzický štítok s Case ID. Workflow postúpi do rozhodovacieho bodu "Je médium čitateľné?".

## Reference

ISO/IEC 27037:2012 - Section 5.2 (Identification of digital evidence)
NIST SP 800-86 - Section 3.1.1 (Collection Phase - Documentation)
ACPO Good Practice Guide - Principle 2 (Recording and preservation)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)