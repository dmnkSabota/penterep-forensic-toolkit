# Detaily testu

## Úkol

Vypočítať SHA-256 hash vytvoreného forenzného obrazu a porovnať so source_hash z imaging procesu pre matematické overenie integrity.

## Obtiažnosť

Snadné

## Časová náročnosť

45

## Automatický test

Áno

## Popis

Overenie integrity forenzného obrazu je druhý a finálny krok dvojfázového procesu zabezpečenia integrity forenzných dát. Prvá fáza (Krok 5) vypočítala source_hash priamo z originálneho média počas imaging procesu. Druhá fáza (tento krok) vypočíta image_hash zo súboru forenzného obrazu uloženého na disku a porovná obe hodnoty. Zhoda hashov matematicky dokazuje, že súbor obrazu je bit-for-bit identický s dátami prečítanými z originálneho média.

Prečo je tento krok kritický? SHA-256 má 2^256 možných hodnôt - pravdepodobnosť náhodnej kolízie je prakticky nulová (0.0000...%), čo znamená že zhoda hashov DOKAZUJE identitu dát s matematickou istotou. Tento dôkaz je akceptovaný v súdnych konaniach podľa Daubert štandardu a je požadovaný forenzými štandardmi NIST SP 800-86 a ISO/IEC 27037:2012. Rozdiel v hashoch by znamenal vážny problém: buď imaging proces zlyhal (I/O chyba počas kopírovania, prerušenie procesu, nedostatok miesta na cieľovom disku), alebo súbor obrazu bol následne modifikovaný (porušenie integrity dôkazu, neoprávnený prístup), alebo došlo ku korupcii súboru na cieľovom úložisku (chyba filesystému, vadný disk).

Tento krok dokončuje integrity verification chain a po úspešnej verifikácii umožňuje bezpečne odpojiť originálne médium a pokračovať v analýze výhradne na forenznom obraze. Originálne médium sa už nikdy nebude čítať - všetky ďalšie operácie sa vykonávajú len na overenom obraze, čím je zaručené, že originál zostáva nemodifikovaný a je právne prípustný ako dôkaz.

Výpočet image_hash prebieha čítaním súboru forenzného obrazu (typicky .dd alebo .raw súbor na SSD disku), nie z originálneho média. Toto je rýchlejšie ako čítanie z originálneho média (moderné SSD: 200-500 MB/s vs USB 2.0 zariadenie: 20-30 MB/s) a nespôsobuje žiadne dodatočné opotrebenie poškodeného originálu. Pre 64GB obraz na SSD trvá výpočet približne 2-5 minút, čo je výrazne rýchlejšie ako opätovné čítanie originálneho média (50+ minút).

## Jak na to

Identifikujte cestu k vytvorenému forenznom obrazu z Kroku 5. Obraz je typicky uložený v `/mnt/user-data/outputs/{case_id}.dd` pre RAW formát alebo `{case_id}.E01` pre Expert Witness Format. Overte, že súbor existuje a má očakávanú veľkosť približne rovnajúcu sa veľkosti originálneho média pomocou príkazu `ls -lh {case_id}.dd`. Skontrolujte voľné miesto na disku - image_hash výpočet nevyžaduje dodatočný priestor, len čítanie existujúceho súboru.

Načítajte source_hash z Kroku 5 zo súboru `{case_id}_imaging.json` v poli `source_hash`. Tento hash bol vypočítaný počas imaging procesu (dc3dd má built-in hashovanie, ddrescue vyžaduje samostatný výpočet po imaging) a reprezentuje kryptografický otisk dát prečítaných z originálneho média. Overte, že source_hash je kompletný 64-znakový hexadecimálny reťazec (0-9, a-f). Ak source_hash chýba alebo je neplatný, Krok 5 nebol dokončený správne a je potrebné ho opakovať.

Pre RAW obrazy (.dd, .raw) vypočítajte SHA-256 hash pomocou príkazu `sha256sum {case_id}.dd`. Proces môže trvať 2-10 minút podľa veľkosti obrazu a rýchlosti cieľového disku - moderné SSD dosahujú 200-500 MB/s, čo znamená približne 2-5 minút pre 64GB obraz. Pre progress monitoring použite `pv {case_id}.dd | sha256sum`, ktorý zobrazuje priebeh v reálnom čase. Výsledok je 64-znakový hexadecimálny image_hash.

Pre E01 obrazy (Expert Witness Format) použite príkaz `ewfverify {case_id}.E01`. E01 formát má integrovanú CRC kontrolu a hash verifikáciu v každom segmente súboru, takže ewfverify automaticky overí integritu celej E01 štruktúry a vypočíta celkový hash. Tento proces je pomalší ako sha256sum kvôli dekompresii E01 formátu, ale poskytuje dodatočnú kontrolu integrity E01 kontajnera (detekuje korupciu segmentov, chýbajúce časti, nesprávnu sekvenciu).

Zaznamenajte výslednú image_hash hodnotu presne tak ako je - 64 hexadecimálnych znakov (0-9, a-f). KRITICKÉ: Skopírujte hash presne, akákoľvek chyba v jednom znaku zmení celú hodnotu. Uložte hash do Case dokumentácie spolu s časovou značkou výpočtu, názvom súboru obrazu, veľkosťou súboru v bajtoch, operátorom ktorý vykonal verifikáciu, a dobou trvania výpočtu.

Automaticky porovnajte source_hash (z Kroku 5) a image_hash (práve vypočítaný). Hashe musia byť ÚPLNE identické vo všetkých 64 znakoch. Zhoda v 63 znakoch z 64 je stále NEZHODA a indikuje problém - pravdepodobne chyba pri kop írovaní/vkladaní hashu, nie skutočná nezhoda dát. Porovnanie vykonajte pomocou Python skriptu alebo manuálne: `if [ "$source_hash" = "$image_hash" ]; then echo "MATCH"; else echo "MISMATCH"; fi`.

Pri ÚPLNEJ ZHODE oboch hashov (source_hash == image_hash): Integrita je matematicky POTVRDENÁ. Vytvorte verification report s výsledkom "VERIFIED", časovou značkou, source_hash, image_hash, a podpisom zodpovednej osoby. Označte Case ako "Integrity Verified - Ready for Analysis". Originálne médium môžete bezpečne odpojiť od write-blockera a zabezpečiť ako dôkaz v evidence room podľa Chain of Custody protokolu. Forenzný obraz je teraz jedinou pracovnou kópiou pre všetky ďalšie analýzy. Médium už nikdy nebude potrebné opätovne čítať. Pokračujte do Kroku 7 (Dokumentácia špecifikácií média) a následne Krok 8 (Analýza súborového systému). Integrity verification je úspešne dokončená.

Pri NEZHODE hashov (source_hash != image_hash): Integrita ZLYHALA - KRITICKÁ CHYBA. Vytvorte incident report s detailmi nezhody (obe hash hodnoty, časové značky, Case ID). Zastavte ďalší proces, NEPOKRAČUJTE v analýze neverifikovaného obrazu. Vykonajte diagnostiku príčiny: Skontrolujte imaging log z Kroku 5 na I/O chyby, timeouty alebo prerušenia procesu. Overte integritu súborového systému cieľového disku pomocou `fsck` alebo SMART testu - možná korupcia súboru na disku. Skontrolujte SMART status originálneho média pomocou `smartctl -a /dev/sdX` - možno sa médium degradovalo počas imaging procesu. Skontrolujte či súbor obrazu nebol modifikovaný po vytvorení - overte file timestamps pomocou `stat {case_id}.dd`, skontrolujte access logs systému, overte že write-blocker bol aktívny po celý čas.

Opravte identifikovaný problém a opakujte Krok 5 (Imaging) s novým pripojením média. Používajte čerstvé USB káble (staré káble môžu spôsobovať data corruption), iný USB port (niektoré porty majú slabšie napájanie), prípadne iný write-blocker (hardware môže byť vadný). Pre média s detekovanými vadnými sektormi použite ddrescue namiesto dc3dd. Vyčistite všetky predchádzajúce súbory obrazu pred novým pokusom. Dokumentujte každý pokus do Case súboru s popisom problému a riešenia. Maximálne 3 pokusy sú povolené - ak všetky tri pokusy zlyhali s nezhodu hashov, eskalujte problém supervízorovi alebo senior forenzikovi pre pokročilú diagnostiku. Možno je potrebná fyzická oprava média (Krok 4), výmena imaging workstation, alebo špeciálne recovery nástroje.

Vytvorte finálny verification report obsahujúci: Case ID, source_hash (z Kroku 5), image_hash (z tohto kroku), výsledok porovnania (MATCH/MISMATCH), časové značky oboch výpočtov, meno operátora, počet pokusov ak boli opakovania, dôvod nezhody ak bol identifikovaný, a podpis zodpovednej osoby. Tento report je súčasťou Chain of Custody dokumentácie a musí byť archivovaný spolu s Case súborom. Pre právne účely je tento report dôkazom integrity forenzného procesu a je požadovaný pri súdnych konaniach.

## Výsledek

SHA-256 hash forenzného obrazu vypočítaný a porovnaný so source_hash z imaging procesu. Výsledok verifikácie: MATCH (zhoda hashov - imaging proces úspešný, súbor obrazu je bit-for-bit identický s dátami prečítanými z originálneho média, dôkaz integrity zabezpečený) alebo MISMATCH (nezhoda - KRITICKÁ CHYBA, imaging proces zlyhal alebo súbor bol modifikovaný, opakuj Krok 5). Pri MATCH workflow pokračuje do Kroku 7 (Dokumentácia špecifikácií média), originálne médium môže byť bezpečne odpojené, zabezpečené a archivované ako dôkaz. Všetky ďalšie analýzy sa vykonávajú výhradne na overenom forenznom obraze. Finálny integrity report vytvorený a archivovaný v Chain of Custody dokumentácii.

## Reference

NIST SP 800-86 - Section 3.1.2 (Examination Phase - Data Integrity Verification)
ISO/IEC 27037:2012 - Section 7.2 (Verification of integrity of digital evidence)
RFC 6234 - US Secure Hash Algorithms (SHA-256 specification)
NIST FIPS 180-4 - Secure Hash Standard (SHA-256 algorithm)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)