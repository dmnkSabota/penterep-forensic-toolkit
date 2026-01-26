# Detaily testu

## Úkol

Prijať žiadosť a vytvoriť Case ID pre obnovu fotografií.

## Obtiažnosť

Snadné

## Časová náročnosť

10

## Automatický test

Nie

## Popis

Prvý krok každého forenzného procesu obnovy dát začína formálnym prijatím žiadosti od klienta. V tomto kroku sa vytvorí unikátny identifikátor prípadu (Case ID), zaznamenajú sa základné informácie o klientovi a povahe žiadosti, a inicializuje sa dokumentačný proces v súlade s ISO/IEC 27037:2012.



## Jak na to

Otvorte formulár pre nový Case a vyplňte kompletné údaje klienta - meno alebo názov firmy, kontaktný email, telefónne číslo a fakturačnú adresu ak je dostupná.

Vytvorte Case ID podľa formátu PHOTO-YYYY-MM-DD-XXX, kde YYYY-MM-DD je aktuálny dátum a XXX je poradové číslo prípadu v daný deň (napríklad PHOTO-2025-01-26-001 pre prvý prípad). Overte, že Case ID je jedinečné a neexistuje v databáze.

Zaznamenajte základné informácie o poškodenom médiu: typ zariadenia (SD karta, microSD karta, USB flash disk, HDD, SSD alebo iné), odhadovanú kapacitu podľa údajov od klienta, a či je prítomné viditeľné fyzické poškodenie. Ak klient uvádza poškodenie, zapíšte jeho popis.

Vyberte urgentnosť prípadu podľa dohody s klientom:
- Štandardná (5-7 pracovných dní)
- Vysoká (2-3 pracovné dni)
- Kritická (do 24 hodín)

Zvoľte právny základ spracovania osobných údajov podľa GDPR. Pre komerčnú obnovu dát je to typicky "plnenie zmluvy", pre súdne vyšetrovania "právna povinnosť".

Vygenerujte príjmový protokol s týmito údajmi, vytlačte ho a nechajte klienta podpísať. Naskenujte podpísanú verziu a archivujte ju do dokumentácie Case.

Uložte Case do systému - overte vytvorenie Case ID dokumentu (JSON formát) a odoslanie potvrdzovacieho emailu klientovi s číslom prípadu a ďalšími krokmi.

## Výsledek

Po úspešnom dokončení je vytvorený Case ID dokument (JSON), príjmový protokol (PDF) s podpisom klienta, a odoslaný potvrdzovací email. Case je označený ako "INITIATED" a workflow automaticky postúpi do kroku "Identifikácia média".

## Reference

ISO/IEC 27037:2012 - Section 5 (Guidelines for identification)
GDPR (Nariadenie EÚ 2016/679) - Článok 6 (Právny základ spracovania)
NIST SP 800-86 - Section 3.1.1 (Collection Phase)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)