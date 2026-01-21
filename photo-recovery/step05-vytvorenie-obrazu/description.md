# Detaily testu

## Úkol

Vytvoriť presný bit-for-bit forenzný obraz úložného média. Zabezpečiť, že originál zostane neporušený a všetky dáta vrátane vymazaných súborov a nealokovaného priestoru sú zachytené.

## Obtiažnosť

Snadné (proces je automatizovaný)

## Časová náročnosť

120

## Automatický test

Áno - Python skript automaticky vytvorí forenzný obraz pomocou dc3dd, ddrescue alebo ewfacquire (podľa stavu média)

## Popis

Forenzný imaging je proces vytvárania presnej bitovej kópie úložného média. Na rozdiel od bežného kopírovania súborov, forenzný obraz zachytáva absolútne všetko - aktívne súbory, vymazané súbory, slack space, unallocated space, metadata.

Prečo je tento krok kritický:
- Originál zostáva neporušený - všetky analýzy sa robia na kópii
- Zachytáva všetky dáta vrátane vymazaných súborov
- Možnosť vytvorenia viacerých kópií bez opätovného prístupu k originálu
- Súdna prípustnosť dôkazu
- Reprodukovateľnosť procesu

Výber nástroja: dc3dd (perfektné médium), ddrescue (poškodené médium s vadnými sektormi), ewfacquire (E01 formát s kompresiou a metadátami).

## Jak na to

1. Overenie write-blockera - test zápisu musí zlyhať (zariadenie read-only)
2. Príprava cieľového úložiska - musí mať aspoň 110% veľkosti média
3. Výber imaging nástroja - dc3dd (ak Readability score ≥90), ddrescue (ak <90), ewfacquire (pre E01 formát)
4. Spustenie imaging procesu - vytvorenie bit-for-bit kópie celého média
5. Monitoring priebehu - sledovanie rýchlosti, času, chybových sektorov
6. Generovanie log súboru - zaznamenanie detailov imaging procesu (nástroj, trvanie, chyby)

---

## Výsledek

Forenzný obraz vytvorený (.dd, .raw alebo .E01 formát). Imaging log obsahuje detaily procesu. Originálne médium zostáva neporušené. Obraz je pripravený na verifikáciu integrity (Kroky 6, 8, 9).

## Reference

ISO/IEC 27037:2012 - Section 6.3 (Acquisition of digital evidence)
NIST SP 800-86 - Section 3.1.1 (Collection Phase)
ACPO Good Practice Guide - Principle 1 & 2

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
