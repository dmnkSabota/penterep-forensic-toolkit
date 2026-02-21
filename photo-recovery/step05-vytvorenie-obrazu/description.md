# Detaily testu

## Úkol

Vytvoriť forenzný obraz média a automaticky vypočítať SHA-256 hash počas procesu imaging.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

120 minút

## Automatický test

Áno

## Popis

Forenzný imaging je proces vytvárania presnej bitovej kópie úložného média. Na rozdiel od bežného kopírovania súborov, forenzný obraz zachytáva absolútne všetko – aktívne súbory, vymazané súbory, slack space, nealokovaný priestor a metadata súborového systému, pričom je bit-for-bit identický s originálom.

SHA-256 hash sa vypočítava súčasne s kopírovaním dát v jednom priechode – eliminuje potrebu opätovného čítania média a poskytuje matematický dôkaz integrity. Výber nástroja závisí od stavu média určeného v Kroku 3: dc3dd pre READABLE médiá (rýchle, s integrovaným hashovaním), ddrescue pre PARTIAL médiá (recovery režim s mapovaním chybných sektorov).

Originálne médium zostáva po celý čas pripojené výhradne cez write-blocker. Všetky budúce analýzy sa vykonávajú na vytvorenej kópii, čím je zabezpečená súdna prípustnosť dôkazu.

## Jak na to

**1. Overenie write-blockera:**

Pred spustením imagingu overte fyzický stav write-blockera – LED indikátor musí svietiť (PROTECTED) a médium musí byť zapojené výlučne cez write-blocker. Systém vyžiada explicitné interaktívne potvrdenie pred pokračovaním.

**2. Kontrola dostupného miesta:**

Uistite sa, že cieľové úložisko má dostatok miesta – minimálne 110% kapacity zdrojového média (rezerva pre metadata, logy a mapfile). Systém toto overí automaticky.

**3. Spustenie imagingu:**

Systém automaticky vyberie nástroj na základe výsledku Kroku 3:

- **READABLE → dc3dd:** `dc3dd if=/dev/sdX of=CASE.dd hash=sha256 log=imaging.log bs=1M progress=on`
- **PARTIAL → ddrescue:** `ddrescue -f -v /dev/sdX CASE.dd CASE.mapfile`

Pri ddrescue sa SHA-256 hash vypočíta samostatne po dokončení imagingu, keďže ddrescue nemá integrované hashovanie.

**4. Monitorovanie priebehu:**

Systém zobrazuje aktuálnu rýchlosť čítania (MB/s), odhadovaný zostávajúci čas, množstvo skopírovaných dát, a pri ddrescue počet chybných sektorov. Pri rýchlosti pod 1 MB/s zvážte, či médium nevyžaduje fyzickú opravu (Krok 4).

**5. Zaznamenanie source_hash a aktualizácia CoC:**

Po dokončení dc3dd automaticky vypíše SHA-256 hash do konzoly aj do log súboru. Tento hash je source_hash – referenčná hodnota pre verifikáciu v Kroku 6. Zaznamenajte ho presne (64 hexadecimálnych znakov). Aktualizujte Chain of Custody log o záznam vykonaného imagingu.

**6. Archivácia výstupov:**

Archivujte do Case dokumentácie:
- `{case_id}.dd` – forenzný obraz
- `{case_id}_imaging.json` – source_hash a metadata
- `{case_id}_imaging.log` – detailný log procesu
- `{case_id}.dd.sha256` – hash v štandardnom formáte
- `{case_id}.mapfile` – len pre ddrescue, mapa chybných sektorov

## Výsledek

Forenzný obraz vytvorený vo formáte .dd. SHA-256 source_hash vypočítaný a zaznamenaný v JSON súbore aj samostatnom .sha256 súbore. Imaging log obsahuje kompletné detaily – nástroj, trvanie, priemernú rýchlosť, počet chybných sektorov a source_hash. CoC log aktualizovaný o záznam imagingu. Originálne médium zostáva neporušené a pripojené pre verifikáciu v Kroku 6.

## Reference

ISO/IEC 27037:2012 – Section 6.3 (Acquisition of digital evidence)
NIST SP 800-86 – Section 3.1.1 (Collection Phase – Forensic Imaging)
ACPO Good Practice Guide – Principle 1 & 2 (Evidence preservation)
NIST FIPS 180-4 – Secure Hash Standard (SHA-256 specification)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Teoretická časť (Kapitola 3.3.2, Krok 5) pokrýva forenzný imaging ako jednokrokový proces s výberom nástroja podľa stavu média.

Implementácia rozširuje tento krok o:

Automatické načítanie výsledku Kroku 3 z JSON reportu – nástroj sa vyberie na základe uloženého mediaStatus bez potreby manuálneho zadávania. Verifikácia write-blockera je interaktívna s explicitnými otázkami o fyzickom stave – nie automatický pokus o zápis, ktorý by pri nefunkčnom write-blockeri poškodil dôkazové médium. Kontrola dostupného miesta pred spustením imagingu predchádza prerušeniu procesu počas kopírovania. Pre ddrescue sa SHA-256 hash vypočíta samostatným príkazom po dokončení imagingu cez bezpečné Popen reťazenie bez shell=True.