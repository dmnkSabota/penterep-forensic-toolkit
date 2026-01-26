# Detaily testu

## Úkol

Vytvoriť forenzný obraz média.

## Obtiažnosť

Snadné

## Časová náročnosť

120

## Automatický test

Áno

## Popis

Forenzný imaging je proces vytvárania presnej bitovej kópie úložného média, ktorá zachytáva absolútne všetko - aktívne súbory, vymazané súbory, slack space, nealokovaný priestor a metadata súborového systému. Na rozdiel od bežného kopírovania súborov, forenzný obraz je bit-for-bit identický s originálom. Originálne médium zostáva po celý proces pripojené cez write-blocker a všetky budúce analýzy sa vykonávajú výhradne na vytvorenej kópii, čím je zabezpečená súdna prípustnosť dôkazu a reprodukovateľnosť procesu. Výber imaging nástroja závisí od stavu média - dc3dd pre bezvadné médiá, ddrescue pre médiá s vadnými sektormi, alebo ewfacquire pre E01 formát s kompresiou.

## Jak na to

Overte funkčnosť write-blockera pred začatím imaging procesu. Vykonajte test zápisu na pripojené médium - pokus o zápis musí zlyhať s chybovou hláškou, čím je potvrdené, že médium je skutočne v režime read-only a nemôže dôjsť k jeho modifikácii. Bez tejto verifikácie nikdy nepokračujte.

Pripravte cieľové úložisko pre forenzný obraz. Uistite sa, že dostupný priestor je minimálne 110% kapacity zdrojového média - extra 10% je rezerva pre metadata, log súbory a prípadné chybové logy. Pre 64GB SD kartu potrebujete minimálne 70GB voľného miesta. Používajte rýchle SSD disky alebo RAID systém pre optimálnu rýchlosť imaging procesu.

Systém automaticky vyberie vhodný imaging nástroj na základe výsledku Readability Test z Kroku 3. Ak médium dosiahlo skóre READABLE (všetky testy prešli), použije sa dc3dd nástroj vytvárajúci čistý bit-stream obraz s priebežným hashovaním. Ak médium dosiahlo PARTIAL (niektoré testy zlyhali, detekované vadné sektory), použije sa ddrescue nástroj optimalizovaný pre recovery z poškodených médií s možnosťou preskočenia nečitateľných blokov. Pre archiváciu alebo prípady vyžadujúce kompresiu je možné explicitne vybrať ewfacquire nástroj vytvárajúci E01 formát s metadátami a CRC kontrolami.

Spustite imaging proces. Systém automaticky zostaví príkaz s optimálnymi parametrami - veľkosť bloku (typicky 1MB pre rýchlosť, 64KB pre poškodené médiá), cieľová cesta, a hash algoritmy (SHA-256 povinný, MD5 a SHA-1 voliteľné pre spätnú kompatibilitu). Imaging prebieha v jednom prechode, počas ktorého sú dáta kopírované a súčasne hashované.

Monitorujte priebeh imaging procesu v reálnom čase. Systém zobrazuje aktuálnu rýchlosť čítania (MB/s), celkový prebežný čas, odhadovaný zostávajúci čas, množstvo skopírovaných dát, a pri ddrescue aj počet chybných sektorov a mapa ich umiestnenia. Pri veľmi pomalej rýchlosti (pod 1 MB/s) zvážte, či médium nie je kriticky poškodené.

Po dokončení imaging procesu systém automaticky vygeneruje detailný log súbor. Log obsahuje identifikáciu Case ID, zdrojové zariadenie a cieľový súbor, použitý nástroj a verziu, presný príkaz ktorý bol spustený, časové značky začiatku a konca, trvanie v sekundách, celkovú veľkosť skopírovaných dát, priemerná rýchlosť, počet chybných blokov ak existujú, SHA-256 hash zdrojového média (vypočítaný počas imaging), a exit code procesu. Tento log je kritický pre Chain of Custody dokumentáciu.

Archivujte vytvorený forenzný obraz, imaging log a hash súbory do Case dokumentácie. Originálne médium ponechajte pripojené cez write-blocker pre nasledujúci krok verifikácie integrity (Krok 6).

## Výsledek

Forenzný obraz úspešne vytvorený v jednom z formátov: .dd alebo .raw pre raw bit-stream (dc3dd/ddrescue), alebo .E01 pre Expert Witness Format (ewfacquire). Vygenerovaný imaging log obsahuje kompletné detaily procesu vrátane použitého nástroja, trvania, rýchlosti a počtu chybných sektorov. SHA-256 hash zdrojového média vypočítaný a zaznamenaný. Originálne médium zostáva neporušené a pripojené pre verifikáciu. Workflow automaticky postúpi do Kroku 6 (Výpočet hashu originálneho média) pre overenie integrity.

## Reference

ISO/IEC 27037:2012 - Section 6.3 (Acquisition of digital evidence)
NIST SP 800-86 - Section 3.1.1 (Collection Phase)
ACPO Good Practice Guide - Principle 1 & 2

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)