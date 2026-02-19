# Detaily testu

## Úkol

Je médium čitateľné?

## Obtiažnosť

Jednoduchá

## Časová náročnosť

5 minút

## Automatický test

Poloautomatický (vyžaduje potvrdenie spustenia)

## Popis

Tento rozhodovací bod určuje kľúčové vetvenie pracovného postupu podľa diagramu 3.2 v diplomovej práci. Automatický diagnostický test vykoná sériu READ-ONLY kontrol na určenie stavu média a jeho schopnosti poskytovať dáta. Na základe výsledkov systém automaticky odporučí optimálny postup:

- **READABLE** – všetky testy úspešné → krok 5 s nástrojom dc3dd
- **PARTIAL** – niektoré testy zlyhali, médium čiastočne čitateľné → krok 5 s nástrojom ddrescue
- **UNREADABLE** – kritické testy zlyhali → krok 4 (fyzická oprava)

KRITICKÉ BEZPEČNOSTNÉ UPOZORNENIE:

Test vykonáva výhradne READ-ONLY operácie, ale používateľ musí pred spustením overiť správne pripojenie write-blockera. Spustenie testu bez write-blockera môže modifikovať dôkazové médium. Pri mechanických HDD s podozrením na fyzické poškodenie môže pokus o čítanie zhoršiť stav zariadenia.

Používateľ musí explicitne potvrdiť bezpečnostné kontroly pred spustením automatických testov.

## Jak na to

**1. Pripojenie média a predbežná detekcia:**

Pripojte médium cez write-blocker a overte, že systém zariadenie vidí:
- `lsblk` – zoznam blokových zariadení a ich veľkostí
- `blkid` – identifikácia súborového systému a partícií
- `smartctl -a /dev/sdX` – SMART údaje (dostupné pre HDD/SSD)

Výstupy týchto nástrojov zaznamenajte do dokumentácie Case – sú súčasťou CoC záznamu.

**2. Bezpečnostný check pred spustením diagnostiky:**

Pred spustením automatického testu potvrďte:
- Write-blocker je fyzicky pripojený a médium je zapojené cez neho, nie priamo
- LED indikátor write-blockera svieti
- Pri mechanických HDD: žiadne nezvyčajné zvuky zo zariadenia (škrabanie, cvakanie)

Ak niektorá podmienka nie je splnená, nepokračujte – existuje riziko poškodenia dôkazu.

**3. Spustenie diagnostického testu:**

Po potvrdení bezpečnosti spustite automatický skript `ptmediareadability`. Systém vykoná päť testov v poradí:

- **Test 1 – Detekcia média** (lsblk): overuje, či OS zariadenie vôbec vidí
- **Test 2 – Čítanie prvého sektora** (dd, 512 B): overuje základnú schopnosť čítania
- **Test 3 – Sekvenčné čítanie** (dd, 1 MB): overuje konzistentný prístup k dátam
- **Test 4 – Náhodné čítanie**: detekuje lokalizované vadné sektory
- **Test 5 – Meranie rýchlosti**: identifikuje médiá s degradovaným výkonom, ktoré by spôsobovali problémy pri imagingu

**4. Kontrola výsledkov:**

Systém automaticky určí stav média a odporučí nástroj pre nasledujúci krok. Skontrolujte vygenerovaný JSON report – obsahuje výsledky každého testu, identifikované problémy a odôvodnenie finálnej klasifikácie.


## Výsledek

Stav média je klasifikovaný ako READABLE, PARTIAL alebo UNREADABLE. JSON report zachytáva výsledky všetkých piatich testov vrátane identifikovaných chýb a výstupy predbežnej detekcie (lsblk, blkid, smartctl) sú zaradené do CoC dokumentácie. Workflow automaticky vetvuje podľa výsledku – do kroku 5 s príslušným nástrojom, alebo do kroku 4.


## Reference

ISO/IEC 27037:2012 - Section 6.3 (Acquisition of digital evidence)
NIST SP 800-86 - Section 3.1.1.3 (Data Collection Methodology)
ACPO Good Practice Guide - Principle 1 (No action should change data)

## Stav

K otestovaniu

## Nález

(prázdne - vyplní sa po teste)

--------------------------------------------------------------------------
## Poznámky k implementácii

Praktické rozšírenia oproti teoretickému návrhu v diplomovej práci:

Teoretická časť (Kapitola 3.3.2, Krok 3) uvádza len verifikáciu čitateľnosti média pripojením k forenznému počítaču cez write-blocker a pri nečitateľnom médiu vetvenie k fyzickej oprave.

Implementácia rozširuje tento krok o:

1. Poloautomatický proces - používateľ musí explicitne potvrdiť bezpečnostné kontroly pred spustením
2. Automatizovaný testovací protokol - namiesto manuálnej verifikácie systém vykonáva štandardizovanú sériu piatich testov
3. Diagnostické testy - lsblk (detekcia), dd (prvý sektor), sekvenčné čítanie (1MB), náhodné čítanie (vadné sektory), meranie rýchlosti (degradácia)
4. Trojstupňová klasifikácia - READABLE, PARTIAL, UNREADABLE namiesto binárnej áno/nie
5. Automatický výber nástroja - systém odporúča dd pre READABLE, ddrescue pre PARTIAL médium
6. JSON report - štruktúrovaný výstup s detailnými výsledkami každého testu
7. Stav PARTIAL - nová kategória pre médiá s čiastočnými chybami, ktoré vyžadujú špeciálny nástroj ale nepotrebujú fyzickú opravu
8. Bezpečnostné kontroly - explicitná verifikácia write-blockera pred spustením testov

Tieto rozšírenia budú doplnené do implementačnej kapitoly diplomovej práce s odôvodnením ich potreby pre štandardizáciu diagnostického procesu, reprodukovateľnosť testovania naprieč rôznymi prípadmi, objektívne rozhodovanie o ďalšom postupe, dokumentáciu technického stavu média pre forenzné účely a ochranu integrity dôkazového materiálu.