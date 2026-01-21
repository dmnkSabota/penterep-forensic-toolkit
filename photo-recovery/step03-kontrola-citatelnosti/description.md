# Detaily testu

## Úkol

Automaticky otestovať, či je možné pripojiť médium a čítať z neho dáta. Na základe výsledku testu určiť, či môžeme pokračovať priamo na vytvorenie forenzného obrazu alebo je potrebná fyzická oprava.

## Obtiažnosť

Snadné

## Časová náročnosť

5

## Automatický test

Áno - Python skript vykonáva 5 testov čítateľnosti (detekcia OS, prvý sektor, sekvenčné čítanie 1MB, náhodné čítanie, rýchlosť)

## Popis

Tento rozhodovací bod určuje kľúčové vetvenie pracovného postupu. Médium môže byť ČÍTATEĽNÉ (operačný systém detekuje médium, je možné čítať sektory) alebo NEČÍTATEĽNÉ (médium nie je detekované OS, čítanie vracia chyby, potrebná fyzická oprava).

Prečo je tento krok kritický:
- Zabráni zbytočným pokusom o imaging nečítateľných médií
- Včas identifikuje potrebu fyzickej opravy
- Dokumentuje technický stav média
- Optimalizuje workflow podľa stavu média
- Pri PARTIAL výsledkoch odporúča použiť ddrescue namiesto dd

## Jak na to

1. Pripoj médium k forenznej stanici CEZ WRITE-BLOCKER (povinné!)
2. Spusti automatický test čítateľnosti - skript vykoná 5 testov
3. Test 1: Detekcia OS (lsblk) - overí, či systém vidí médium
4. Test 2: Čítanie prvého sektora (dd 512 bajtov) - test základnej čitateľnosti
5. Test 3-5: Sekvenčné čítanie 1MB, náhodné čítanie z rôznych pozícií, meranie rýchlosti
6. Na základe výsledkov systém automaticky určí: ČÍTATEĽNÉ → Krok 5 alebo NEČÍTATEĽNÉ → Krok 4

---

## Výsledek

Test dokončený, stav média určený. Pri ČÍTATEĽNOM médiu pokračuj Krokom 5 (Vytvorenie forenzného obrazu). Pri NEČÍTATEĽNOM médiu pokračuj Krokom 4 (Fyzická oprava média). Vygenerovaný JSON report s výsledkami všetkých testov a odporúčaným nástrojom pre imaging.

## Reference

ISO/IEC 27037:2012 - Section 6.3 (Acquisition of digital evidence)
NIST SP 800-86 - Section 3.1.1.3 (Data Collection Methodology)
ACPO Good Practice Guide - Principle 1 (No action should change data)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
