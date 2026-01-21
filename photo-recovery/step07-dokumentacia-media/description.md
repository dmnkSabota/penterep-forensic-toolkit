# Detaily testu

## Úkol

Zaznamenať technické špecifikácie média a špeciálne okolnosti, ktoré môžu ovplyvniť proces obnovy dát.

## Obtiažnosť

Snadné

## Časová náročnosť

10

## Automatický test

(prázdne - manuálny krok s odborným posúdením)

## Popis

Dokumentácia technických špecifikácií média je dôležitá pre identifikáciu potenciálnych limitácií a rizík pri obnovovaní dát. Rôzne typy médií majú špecifické vlastnosti, ktoré môžu ovplyvniť úspešnosť obnovy.

Prečo je tento krok kritický:
- SSD disky s TRIM môžu fyzicky odstrániť vymazané dáta
- HDD so zlým SMART statusom vyžadujú špeciálny prístup
- Flash médiá majú obmedzený počet zápisových cyklov
- Šifrované médiá potrebujú recovery key/heslo
- RAID polia vyžadujú všetky disky

POZNÁMKA: Tento krok je často integrovaný do Kroku 2 (Identifikácia média), ale je vyčlenený pre dôkladnejšiu dokumentáciu.

## Jak na to

1. Pre SSD disky - zaznamenaj TRIM support (áno/nie), Garbage Collection status, Wear Leveling info, odporúčanie: minimalizovať čas pripojenia
2. Pre HDD disky - zisti SMART status (smartctl -a /dev/sdX), zaznamenaj počet realokovaných/pending sektorov, teplotu, zvuky disku
3. Pre Flash médiá (USB, SD karty) - zaznamenaj wear leveling info, počet bad blocks, odhad životnosti
4. Špeciálne prípady - šifrované médiá (BitLocker, LUKS), RAID polia (typ, stripe size), exotické FS (BTRFS, ZFS)
5. Použij nástroje: smartctl, hdparm, lsusb pre zber technických údajov
6. Vytvor poznámky o limitáciách a upozornenia pre ďalšie kroky

---

## Výsledek

Technická dokumentácia média dokončená. Identifikované limitácie a riziká. Poznámky pripravené pre ďalšie kroky obnovy.

## Reference

ISO/IEC 27037:2012 - Section 5.3 (Documentation)
NIST SP 800-86 - Section 3.1.1.3 (Media characteristics)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
1. Zhrnutie technických parametrov
2. Identifikované riziká
3. Odporúčania pre proces obnovy
4. Prognóza úspešnosti obnovy

## Dôležité
- Táto dokumentácia pomáha predvídať problémy
- Niektoré technológie (TRIM) môžu znemožniť úplnú obnovu
- Klient musí byť informovaný o limitáciách
