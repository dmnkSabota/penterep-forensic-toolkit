# Detaily testu

## Úkol

Vytvoriť forenzný obraz média a automaticky vypočítať SHA-256 hash počas procesu imaging.

## Obtiažnosť

Snadné

## Časová náročnosť

120

## Automatický test

Áno

## Popis

Forenzný imaging je proces vytvárania presnej bitovej kópie úložného média s automatickým výpočtom kryptografického hashu počas jedného priechodu dátami. Na rozdiel od bežného kopírovania súborov, forenzný obraz zachytáva absolútne všetko - aktívne súbory, vymazané súbory, slack space, nealokovaný priestor a metadata súborového systému, pričom je bit-for-bit identický s originálom. Moderné forenzné nástroje ako dc3dd vypočítavajú SHA-256 hash súčasne s kopírovaním dát, čím eliminujú potrebu opätovného čítania média a šetria čas aj opotrebenie zariadenia.

Prečo je tento krok kritický? Originálne médium zostáva po celý proces pripojené výhradne cez write-blocker a všetky budúce analýzy sa vykonávajú na vytvorenej kópii, čím je zabezpečená súdna prípustnosť dôkazu a reprodukovateľnosť procesu. Výpočet hashu počas imaging procesu (na rozdiel od dodatočného výpočtu po vytvorení obrazu) poskytuje matematický dôkaz integrity - hash reprezentuje presný stav dát v momente kopírovania. Výber imaging nástroja závisí od stavu média - dc3dd pre bezvadné médiá (rýchle, s integrovaným hashovaním), ddrescue pre médiá s vadnými sektormi (recovery režim s mapovaním chýb), alebo ewfacquire pre E01 formát s kompresiou a metadátami.

Simultánne hashovanie počas imaging procesu je kľúčovou optimalizáciou - namiesto dvoch priečodov médií (kopírovanie + hashovanie) vykonáme jeden priechod s oboma operáciami súčasne. Pre 64GB médium to znamená úsporu približne 50 minút času a polovičné opotrebenie poškodeného média. Výsledný source_hash slúži ako referenčná hodnota pre verifikáciu integrity v Kroku 6.

## Jak na to

Overte funkčnosť write-blockera pred začatím imaging procesu. Vykonajte test zápisu na pripojené médium - pokus o zápis musí zlyhať s chybovou hláškou "read-only" alebo "permission denied", čím je potvrdené, že médium je skutočne v režime read-only a nemôže dôjsť k jeho modifikácii. Bez tejto verifikácie nikdy nepokračujte - akýkoľvek prístup k médiu bez write-blocker ochrany môže zmeniť metadata súborového systému (last access timestamps) a znehodnotiť forenzný proces.

Pripravte cieľové úložisko pre forenzný obraz. Uistite sa, že dostupný priestor je minimálne 110% kapacity zdrojového média - extra 10% je rezerva pre metadata, log súbory a prípadné chybové logy z ddrescue. Pre 64GB SD kartu potrebujete minimálne 70GB voľného miesta. Používajte rýchle SSD disky alebo RAID systém pre optimálnu rýchlosť imaging procesu. Pomalé cieľové úložisko (starý HDD) môže výrazne predĺžiť čas imaging.

Systém automaticky vyberie vhodný imaging nástroj na základe výsledku Readability Test z Kroku 3. Ak médium dosiahlo skóre READABLE (všetky testy prešli, žiadne vadné sektory), použije sa dc3dd nástroj vytvárajúci čistý bit-stream obraz s priebežným SHA-256 hashovaním v reálnom čase. dc3dd číta dáta z média, súčasne ich zapisuje do obrazu a vypočítava hash - všetko v jednom priechode. Ak médium dosiahlo PARTIAL (niektoré testy zlyhali, detekované vadné sektory), použije sa ddrescue nástroj optimalizovaný pre recovery z poškodených médií s možnosťou preskočenia nečitateľných blokov a vytvorením mapfile dokumentujúceho umiestnenie chybných sektorov. Pre archiváciu alebo prípady vyžadujúce kompresiu je možné explicitne vybrať ewfacquire nástroj vytvárajúci E01 formát s metadátami a CRC kontrolami.

Spustite imaging proces pomocí automatického skriptu alebo manuálne. Pre dc3dd je príkaz: `dc3dd if=/dev/sdX of=image.dd hash=sha256 log=imaging.log bs=1M progress=on`. Parametre: if (input file = zdrojové zariadenie), of (output file = cieľový obraz), hash=sha256 (vypočítaj SHA-256 hash počas kopírovania), log (zaznamenaj proces do logu), bs=1M (veľkosť bloku 1 megabyte pre rýchlosť), progress=on (zobraz priebeh). Pre ddrescue: `ddrescue -f -v /dev/sdX image.dd mapfile`. Po dokončení ddrescue imaging je potrebné vypočítať hash samostatne pomocou `dd if=/dev/sdX bs=1M status=none | sha256sum`, pretože ddrescue nemá integrované hashovanie.

Monitorujte priebeh imaging procesu v reálnom čase. Systém zobrazuje aktuálnu rýchlosť čítania (MB/s - typicky 20-50 MB/s pre HDD, 50-150 MB/s pre SSD cez USB 3.0), celkový prebežný čas, odhadovaný zostávajúci čas, množstvo skopírovaných dát v GB, a pri ddrescue aj počet chybných sektorov a mapa ich umiestnenia. Pri veľmi pomalej rýchlosti (pod 1 MB/s) zvážte, či médium nie je kriticky poškodené a či nie je potrebná fyzická oprava v Kroku 4. dc3dd zobrazuje hash progress každých niekoľko GB.

Po dokončení imaging procesu dc3dd automaticky vypíše vypočítaný SHA-256 hash do konzoly aj do log súboru. Tento hash je source_hash - kryptografický otisk dát prečítaných z originálneho média počas imaging procesu. Zaznamenajte tento hash presne ako je - 64 hexadecimálnych znakov (0-9, a-f). KRITICKÉ: Skopírujte hash presne, akákoľvek chyba v jednom znaku zmení celú hodnotu. Systém automaticky uloží tento hash do JSON súboru `{case_id}_imaging.json` v poli `source_hash` pre použitie v Kroku 6.

Vygenerujte detailný imaging log obsahujúci: Case ID, zdrojové zariadenie (napr. /dev/sdb) a cieľový súbor (napr. CASE-001.dd), použitý nástroj a verziu (dc3dd 7.2.646 alebo ddrescue 1.26), presný príkaz ktorý bol spustený, časové značky začiatku a konca procesu, trvanie v sekundách a minútach, celková veľkosť skopírovaných dát v GB, priemerná rýchlosť čítania v MB/s, počet chybných blokov ak existujú (pre ddrescue), SHA-256 source_hash zdrojového média, a exit code procesu (0 = success). Tento log je kritický pre Chain of Custody dokumentáciu a audit trail.

Archivujte vytvorený forenzný obraz, imaging log, source_hash súbor a prípadný mapfile (ddrescue) do Case dokumentácie. Súbory by mali byť: `{case_id}.dd` (forenzný obraz), `{case_id}_imaging.json` (obsahuje source_hash a metadata), `{case_id}_imaging.log` (detailný log procesu), `{case_id}.dd.sha256` (hash v štandardnom formáte pre kompatibilitu), `{case_id}.mapfile` (len pre ddrescue - mapa chybných sektorov). Originálne médium ponechajte pripojené cez write-blocker pre nasledujúci krok verifikácie integrity (Krok 6), kde sa overí že súbor obrazu na disku je identický so source_hash vypočítaným počas imaging.

## Výsledek

Forenzný obraz úspešne vytvorený v jednom z formátov: .dd alebo .raw pre raw bit-stream (dc3dd/ddrescue), alebo .E01 pre Expert Witness Format (ewfacquire). SHA-256 source_hash automaticky vypočítaný počas imaging procesu a zaznamenaný v JSON súbore aj samostatnom .sha256 súbore. Vygenerovaný imaging log obsahuje kompletné detaily procesu vrátane použitého nástroja, trvania, priemernej rýchlosti, počtu chybných sektorov a source_hash hodnoty. Originálne médium zostáva neporušené a pripojené pre verifikáciu v Kroku 6. Workflow automaticky postúpi do Kroku 6 (Overenie integrity obrazu) kde sa vypočíta hash súboru obrazu a porovná so source_hash pre matematické potvrdenie, že imaging proces vytvoril bit-for-bit identickú kópiu.

## Reference

ISO/IEC 27037:2012 - Section 6.3 (Acquisition of digital evidence)
NIST SP 800-86 - Section 3.1.1 (Collection Phase - Forensic Imaging)
ACPO Good Practice Guide - Principle 1 & 2 (Evidence preservation)
NIST FIPS 180-4 - Secure Hash Standard (SHA-256 algorithm specification)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)