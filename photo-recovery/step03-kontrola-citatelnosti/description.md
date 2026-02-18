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

- READABLE: pokračovať vytvorením forenzného obrazu (krok 5) s nástrojom dd
- PARTIAL: pokračovať vytvorením obrazu (krok 5) s nástrojom ddrescue
- UNREADABLE: vetviť na fyzickú opravu média (krok 4)

KRITICKÉ BEZPEČNOSTNÉ UPOZORNENIE:

Test vykonáva výhradne READ-ONLY operácie, ale používateľ musí pred spustením overiť správne pripojenie write-blockera. Spustenie testu bez write-blockera môže modifikovať dôkazové médium. Pri mechanických HDD s podozrením na fyzické poškodenie môže pokus o čítanie zhoršiť stav zariadenia.

Používateľ musí explicitne potvrdiť bezpečnostné kontroly pred spustením automatických testov.

## Jak na to

**1. Kritický bezpečnostný check:**

Pred spustením testu overte nasledujúce podmienky:
- Write-blocker je fyzicky pripojený
- LED indikátor write-blockera svieti (ak je zariadenie vybavené indikátorom)
- Médium je pripojené cez write-blocker, nie priamo k forenznej stanici
- Pri mechanických HDD: neregistrujete nezvyčajné zvuky (škrabanie, cvakanie)

Ak nie sú splnené všetky podmienky, nepokračujte v teste. Existuje riziko poškodenia dôkazu.

**2. Potvrdenie a spustenie testu:**

Po overení bezpečnosti potvrďte spustenie automatického testu. Systém vykoná sériu piatich diagnostických testov:

Test 1 - Detekcia média:
- Nástroj: lsblk
- Overuje, či operačný systém detekuje zariadenie
- Zlyhanie znamená, že médium nie je vôbec viditeľné systémom

Test 2 - Čítanie prvého sektora:
- Nástroj: dd (čítanie 512 bajtov)
- Overuje základnú schopnosť čítania dát z fyzického zariadenia

Test 3 - Sekvenčné čítanie:
- Čítanie prvého megabajtu dát
- Overuje konzistentný sekvenčný prístup

Test 4 - Náhodné čítanie:
- Čítanie z náhodných pozícií na médiu
- Detekuje lokalizované chyby alebo vadné sektory

Test 5 - Meranie rýchlosti:
- Meria rýchlosť čítania
- Identifikuje médiá s degradovaným výkonom

**3. Vyhodnotenie výsledkov:**

Systém automaticky určí stav média:

READABLE (všetky testy úspešné):
Workflow pokračuje krokom 5 "Vytvorenie forenzného obrazu" s nástrojom dd.

PARTIAL (niektoré testy zlyhali, médium čiastočne čitateľné):
Workflow pokračuje krokom 5 s nástrojom ddrescue a varovaním.

UNREADABLE (kritické testy zlyhali):
Workflow vetvuje na krok 4 "Fyzická oprava média".

**4. Kontrola výsledkov:**

Overte vygenerovaný JSON report obsahujúci detailné výstupy každého testu, identifikované problémy a odporúčaný postup.

## Výsledek

Test dokončený, stav média automaticky určený. Výstupom je klasifikácia média (READABLE, PARTIAL alebo UNREADABLE), JSON report s výsledkami všetkých piatich testov, jasné odporúčanie nástroja pre nasledujúci krok (dd alebo ddrescue) a automatické vetvenie workflow podľa stavu.

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