# Detaily testu

## Úkol

Zaznamenať technické špecifikácie média a špeciálne okolnosti, ktoré môžu ovplyvniť proces obnovy dát.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

10 minút

## Automatický test

Nie

## Popis

Dokumentácia technických špecifikácií média je kritická pre identifikáciu potenciálnych limitácií a rizík pri obnovovaní dát. Rôzne typy médií majú špecifické vlastnosti, ktoré zásadne ovplyvňujú stratégiu obnovy a jej úspešnosť.

SSD disky s aktívnym TRIM príkazom fyzicky odstraňujú vymazané dáta na pozadí – pripojenie SSD bez write-blockera môže viesť k trvalej strate všetkých vymazaných súborov v priebehu minút. HDD so zlým SMART statusom môžu kedykoľvek úplne zlyhať. Šifrované médiá sú bez recovery kľúča alebo hesla úplne neprístupné. RAID polia vyžadujú všetky disky a znalosti o konfigurácii.

Výstupy tohto kroku slúžia ako podklad pre Krok 8 (Analýza súborového systému) a pre informovanie klienta o reálnych limitáciách obnovy.

## Jak na to

**1. Identifikácia typu média:**

Pomocou príkazov `lsblk`, `fdisk -l` a `lsusb` zistite, či ide o SSD, HDD, USB flash disk, SD kartu alebo špeciálne zariadenie (RAID pole). Typ média určuje, ktoré diagnostické nástroje sú relevantné.

**2. Diagnostika SSD:**

Zaznamenajte TRIM support status: `hdparm -I /dev/sdX | grep TRIM`. Ak je TRIM aktívny, zaznamenajte kritické varovanie – vymazané dáta môžu byť automaticky fyzicky odstránené. Skontrolujte Wear Level Indicator a Media Wearout Indicator pomocou `smartctl -a /dev/sdX`.

**3. Diagnostika HDD:**

Vykonajte kompletnú SMART diagnostiku: `smartctl -a /dev/sdX`. Zaznamenajte kritické atribúty: Reallocated Sector Count (ak >50 – disk kriticky poškodený), Current Pending Sector Count (ak >0 – disk aktívne zlyháva), Uncorrectable Sector Count, Spin Retry Count a teplotu (ak >45°C). Počúvajte zvuky disku: cvakanie = poškodené hlavičky, škripanie = poškodený motor.

**4. Diagnostika Flash médií:**

Pre USB a SD karty použite `smartctl -a /dev/sdX` ak zariadenie podporuje SMART, inak `badblocks -sv /dev/sdX` (len read-only test). Ak je počet bad blocks >100, médium je silne opotrebované. Odhadnite životnosť na základe veku a výsledkov testov.

**5. Špeciálne prípady:**

Pre šifrované médiá zistite typ šifrovania (BitLocker: `manage-bde -status`, LUKS: `cryptsetup luksDump /dev/sdX`, FileVault, VeraCrypt) a zaznamenajte kritické upozornenie: bez recovery kľúča alebo hesla sú dáta úplne neprístupné – opýtajte sa klienta na kľúč pred pokračovaním.

Pre RAID polia zistite RAID level, počet diskov a stripe size pomocou `mdadm --detail /dev/mdX`. Zaznamenajte kritické upozornenie: chýbajúci disk môže znemožniť recovery.

Pre netypické súborové systémy (BTRFS, ZFS, ReFS) zaznamenajte verziu a konfiguráciu – vyžadujú špecializované nástroje.

**6. Vytvorenie technickej dokumentácie a informovanie klienta:**

Zdokumentujte do Case súboru: typ média, kapacitu, model, sériové číslo, SMART status, špeciálne vlastnosti (TRIM, šifrovanie, RAID), identifikované riziká a odporúčania pre ďalší postup. Informujte klienta o technických limitáciách – napríklad aktívny TRIM na SSD, kritický SMART status HDD alebo požiadavka na BitLocker recovery kľúč. Transparentná komunikácia predchádza neskoršiemu sklamaniu a právnym sporom.

## Výsledek

Technická dokumentácia média kompletná. Case súbor obsahuje typ média, SMART/Readability status, špeciálne vlastnosti (TRIM, šifrovanie, RAID), kritické upozornenia a odporúčaný postup. Klient informovaný o technických limitáciách a prognóze úspešnosti obnovy. Workflow pokračuje do Kroku 8 (Analýza súborového systému).

## Reference

ISO/IEC 27037:2012 – Section 5.3 (Documentation and chain of custody)
NIST SP 800-86 – Section 3.1.1.3 (Media characteristics and documentation)
SMART Attribute Reference – ATA/ATAPI Command Set specifications

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Tento krok je v niektorých forenzných metodológiách integrovaný do Kroku 2 (Identifikácia média). V tejto implementácii je vyčlenený ako samostatný krok po verifikácii integrity (Krok 6), kedy sú k dispozícii kompletné výsledky readability testu a imaging procesu, čo umožňuje presnejšiu dokumentáciu technického stavu média a reálnejšiu prognózu úspešnosti obnovy.

Krok nemá automatizovaný skript – vyžaduje odborné posúdenie technika, keďže niektoré indikátory (zvuky disku, vizuálne poškodenie) nie je možné automatizovane vyhodnotiť. Dokumentácia sa zapisuje priamo do Case súboru.