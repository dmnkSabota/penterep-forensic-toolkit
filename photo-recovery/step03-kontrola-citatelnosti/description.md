# Detaily testu

## Úkol

Je médium čítateľné?

## Obtiažnosť

Snadné

## Časová náročnosť

5

## Automatický test

Áno

## Popis

Tento rozhodovací bod určuje kľúčové vetvenie pracovného postupu. Médium môže byť čítateľné (operačný systém detekuje zariadenie a umožňuje čítať sektory) alebo nečítateľné (médium nie je detekované systémom, čítanie vracia chyby hardvéru, vyžaduje fyzickú opravu). Automatický test vykoná sériu kontrolných operácií na určenie stavu média a odporučí optimálny postup pre ďalšie kroky vrátane výberu vhodného nástroja pre imaging.

## Jak na to

Pripojte médium k forenznej stanici výhradne cez write-blocker - toto je povinná požiadavka pre zachovanie integrity dôkazu. Nikdy nepripájajte médium priamo bez write-protection zariadenia.

Spustite automatický test čítateľnosti. Systém vykoná sériu päť diagnostických testov na určenie stavu média a jeho schopnosti poskytovať dáta.

Test prebieha v nasledujúcich fázach. Prvý test overuje detekciu média operačným systémom pomocou nástroja lsblk - ak systém nevidí médium vôbec, test okamžite zlyhá. Druhý test sa pokúsi prečítať prvý sektor média (512 bajtov) pomocou dd príkazu - overuje základnú schopnosť čítania dát z fyzického zariadenia.

Tretí test vykoná sekvenčné čítanie prvého megabajtu dát pre overenie konzistentného sekvenčného prístupu. Štvrtý test vykoná náhodné čítanie z rôznych pozícií na médiu pre detekciu lokalizovaných chýb alebo vadných sektorov. Piaty test meria rýchlosť čítania pre identifikáciu médií s degradovaným výkonom, čo môže indikovať blížiacu sa poruchu.

Na základe výsledkov týchto testov systém automaticky určí stav média. Pri výsledku READABLE (všetky testy úspešné) workflow automaticky pokračuje krokom 5 "Vytvorenie forenzného obrazu" s použitím štandardného nástroja dd. Pri výsledku PARTIAL (niektoré testy zlyhali, ale médium je čiastočne čitateľné) systém odporúča použitie ddrescue namiesto dd a pokračuje krokom 5 s varovaním. Pri výsledku UNREADABLE (kritické testy zlyhali) workflow automaticky vetvuje na krok 4 "Fyzická oprava média".

Overte výsledky testu a skontrolujte vygenerovaný JSON report obsahujúci detailné výstupy každého testu, identifikované problémy a odporúčaný postup.

## Výsledek

Test dokončený, stav média automaticky určený a zaradený do jednej z kategórií: READABLE (workflow pokračuje krokom 5 s dd), PARTIAL (workflow pokračuje krokom 5 s ddrescue a varovaním) alebo UNREADABLE (workflow vetvuje na krok 4 fyzickej opravy). Vygenerovaný JSON report s výsledkami všetkých piatich testov, identifikovanými chybami ak existujú, a jasným odporúčaním nástroja pre nasledujúci krok.

## Reference

ISO/IEC 27037:2012 - Section 6.3 (Acquisition of digital evidence)
NIST SP 800-86 - Section 3.1.1.3 (Data Collection Methodology)
ACPO Good Practice Guide - Principle 1 (No action should change data)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)