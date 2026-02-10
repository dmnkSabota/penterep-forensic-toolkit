# Detaily testu

## Úkol

Zaznamenať technické špecifikácie média a špeciálne okolnosti, ktoré môžu ovplyvniť proces obnovy dát.

## Obtiažnosť

Snadné

## Časová náročnosť

10

## Automatický test

Nie - manuálny krok vyžadujúci odborné posúdenie

## Popis

Dokumentácia technických špecifikácií média je kritická pre identifikáciu potenciálnych limitácií a rizík pri obnovovaní dát. Rôzne typy médií majú špecifické vlastnosti, ktoré zásadne ovplyvňujú stratégiu obnovy a jej úspešnosť. Bez tejto dokumentácie môže dôjsť k trvalej strate dát nesprávnym postupom.

Prečo je tento krok kritický? SSD disky s aktívnym TRIM príkazom fyzicky odstraňujú vymazané dáta na pozadí - pripojenie SSD k systému bez write-blockera môže viesť k trvalej strate všetkých vymazaných súborov v priebehu minút. HDD so zlým SMART statusom (vysoký počet realokovaných sektorov, pending sektory) môžu kedykoľvek úplne zlyhať - je potrebné minimalizovať čas pripojenia a vykonať imaging čo najskôr. Flash médiá (USB, SD karty) majú obmedzený počet zápisových cyklov a износ vplýva na úspešnosť recovery. Šifrované médiá (BitLocker, LUKS, FileVault) sú bez recovery kľúča alebo hesla úplne neprístupné. RAID polia vyžadujú všetky disky a znalosti o konfigurácii - chýbajúci disk alebo nesprávne zostavenie môže viesť k strate dát.

Tento krok je často integrovaný do Kroku 2 (Identifikácia média), ale je vyčlenený ako samostatný krok pre dôkladnejšiu dokumentáciu špecifických technických parametrov a rizikových faktorov, ktoré priamo ovplyvňujú stratégiu a postup obnovy.

## Jak na to

Identifikujte typ média pomocou príkazov `lsblk`, `fdisk -l` a `lsusb`. Zistite, či ide o SSD (Solid State Drive), HDD (mechanický disk), USB flash disk, SD kartu, alebo špeciálne zariadenie ako RAID pole. Typ média určuje, ktoré diagnostické nástroje a parametre sú relevantné.

Pre SSD disky zaznamenajte TRIM support status pomocou `hdparm -I /dev/sdX | grep TRIM`. Ak je TRIM podporovaný a aktívny, zaznamenajte KRITICKÉ varovanie - vymazané dáta môžu byť automaticky fyzicky odstránené počas pripojenia média. Zistite stav Garbage Collection a Wear Leveling pomocou `smartctl -a /dev/sdX`. Skontrolujte Wear Level Indicator (zostávajúca životnosť SSD) a Media Wearout Indicator. Odporúčanie: SSD médiá minimalizovať čas pripojenia k systému, vykonať imaging čo najskôr, pred imaging vypnúť TRIM ak je to možné cez BIOS/firmware.

Pre HDD mechanické disky vykonajte kompletnú SMART diagnostiku pomocou `smartctl -a /dev/sdX`. Zaznamenajte kritické SMART atribúty: Reallocated Sector Count (počet realokovaných sektorov - ak >50, disk kriticky poškodený), Current Pending Sector Count (sektory čakajúce na realokovanie - ak >0, disk aktívne zlyháva), Uncorrectable Sector Count (neopraviteľné sektory), Spin Retry Count (problémy s roztočením platní), Temperature (teplota - ak >45°C, problém s chladením). Počúvajte zvuky disku: cvakanie = poškodené hlavičky (okamžite imaging), škripanie = poškodený motor, ticho = disk sa neroztočí (potrebná fyzická oprava). Zaznamenajte Power-On Hours (najazdené hodiny) a Start/Stop Count pre odhad opotrebenia.

Pre Flash médiá (USB disky, SD/microSD karty) zistite informácie o Wear Leveling a Bad Block Management pomocou `smartctl -a /dev/sdX` ak podporuje SMART, inak použite `badblocks -sv /dev/sdX` na detekciu poškodených blokov (POZOR: read-only test, nie write test!). Zaznamenajte počet bad blocks - ak >100 blokov, médium silno opotrebované. Flash médiá typicky neposkytujú podrobné SMART údaje, preto sa spoliehame na Readability Test z Kroku 3. Odhadnite životnosť média na základe veku, intenzity používania a výsledkov testov.

Pre špeciálne prípady identifikujte typ a zaznamenajte kritické informácie. Šifrované médiá: Zistite typ šifrovania (BitLocker - Windows, LUKS - Linux, FileVault - macOS, VeraCrypt). Zaznamenajte KRITICKÉ: Bez recovery kľúča alebo hesla sú dáta úplne neprístupné. Opýtajte sa klienta na heslo/kľúč PRED začatím imaging procesu. Pre BitLocker: `manage-bde -status`. Pre LUKS: `cryptsetup luksDump /dev/sdX`. RAID polia: Zistite RAID level (0, 1, 5, 6, 10) pomocou `mdadm --detail /dev/mdX`, počet diskov v poli, stripe size, metadáta. Zaznamenajte KRITICKÉ: Potrebné všetky disky z RAID poľa, chýbajúci disk môže znemožniť recovery. Netypické súborové systémy: BTRFS, ZFS, ReFS vyžadujú špeciálne nástroje pre analýzu a recovery. Zaznamenajte verziu súborového systému a konfiguráciu (compression, snapshots, RAID-like features).

Vytvorte technickú dokumentáciu do Case súboru obsahujúcu: Typ média (SSD/HDD/Flash), kapacita, model, sériové číslo, SMART status alebo Readability Test výsledky, špeciálne vlastnosti (TRIM, šifrovanie, RAID), identifikované riziká (zlyhaný disk, opotrebované flash, aktívny TRIM), odporúčania pre imaging proces (minimalizovať čas pripojenia, použiť ddrescue namiesto dd, disable TRIM), prognóza úspešnosti recovery (vysoká/stredná/nízka). Tieto poznámky sú kritické pre Krok 5 (Imaging) a ďalšie kroky.

Vytvorte zhrnutie limitácií pre klienta: Informujte klienta o technických limitáciách, ktoré môžu ovplyvniť úspešnosť obnovy. Napríklad: "SSD disk má aktívny TRIM - vymazané súbory mohli byť fyzicky odstránené, obnova nemusí byť úplná", "HDD má 500+ realokovaných sektorov - disk môže kedykoľvek úplne zlyhať, časový tlak na imaging", "BitLocker šifrovanie - bez recovery kľúča sú dáta neprístupné". Transparentná komunikácia limitácií predchádza neskôr sklamaniu a právnym sporom.

## Výsledek

Technická dokumentácia média kompletná s identifikovanými limitáciami, rizikami a odporúčaniami. Case súbor obsahuje: typ média, SMART/Readability status, špeciálne vlastnosti (TRIM/šifrovanie/RAID), kritické upozornenia, odporúčaný postup pre imaging, prognóza úspešnosti recovery. Klient informovaný o technických limitáciách. Workflow pripravený pokračovať do Kroku 3 (Readability Test) alebo Kroku 4 (Fyzická oprava) podľa stavu média.

## Reference

ISO/IEC 27037:2012 - Section 5.3 (Documentation and chain of custody)
NIST SP 800-86 - Section 3.1.1.3 (Media characteristics and documentation)
SMART Attribute Reference - ATA/ATAPI Command Set specifications

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)