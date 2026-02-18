# Detaily testu

## Úkol

Prijať žiadosť o obnovu fotografií a vytvoriť Case ID.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

15 minút

## Automatický test

Nie

## Popis

Prvý krok procesu obnovy fotografií začína formálnym prijatím žiadosti od klienta. Vytvorí sa unikátny identifikátor prípadu (Case ID), zaznamenajú sa základné informácie o klientovi a médiu, a inicializuje sa dokumentačný proces v súlade s ISO/IEC 27037:2012.

## Jak na to

**1. Vytvorenie Case ID a základnej dokumentácie:**

Otvorte formulár pre nový Case a vytvorte Case ID podľa formátu PHOTO-YYYY-MM-DD-XXX, kde YYYY-MM-DD je aktuálny dátum a XXX je poradové číslo prípadu v daný deň (napríklad PHOTO-2025-01-26-001). Overte, že Case ID je jedinečné a neexistuje v databáze.

**2. Údaje klienta:**

Vyplňte kompletné údaje klienta:
- Meno alebo názov firmy
- Kontaktný email
- Telefónne číslo
- Fakturačná adresa (ak je dostupná)

**3. Informácie o poškodenom médiu:**

Zaznamenajte základné informácie podľa údajov od klienta:
- Typ zariadenia (SD karta, microSD karta, USB flash disk, HDD, SSD alebo iné)
- Odhadovaná kapacita
- Viditeľné fyzické poškodenie (ak áno, zapíšte popis)

POZNÁMKA: Tieto údaje budú overené pri fyzickej identifikácii média v ďalšom kroku.

**4. Urgentnosť a SLA:**

Vyberte urgentnosť prípadu podľa dohody s klientom:
- Štandardná (5-7 pracovných dní)
- Vysoká (2-3 pracovné dni)
- Kritická (do 24 hodín)

**5. GDPR súlad:**

Zvoľte právny základ spracovania osobných údajov:
- Pre komerčnú obnovu: "plnenie zmluvy"
- Pre súdne vyšetrovania: "právna povinnosť"

**6. Príjmový protokol:**

Vygenerujte príjmový protokol s vyššie uvedenými údajmi, vytlačte ho a nechajte klienta podpísať. Naskenujte podpísanú verziu a archivujte ju do dokumentácie Case.

**7. Finalizácia:**

Uložte Case do systému a overte:
- Vytvorenie Case ID dokumentu (JSON formát)
- Odoslanie potvrdzovacieho emailu klientovi s číslom prípadu a ďalšími krokmi

## Výsledek

Po úspešnom dokončení sú vytvorené:
- Case ID dokument (JSON)
- Príjmový protokol (PDF) s podpisom klienta
- Potvrdzovací email odoslaný klientovi

Case je označený stavom "INITIATED" a workflow automaticky postupuje do kroku "Identifikácia média".

## Reference

ISO/IEC 27037:2012 - Section 5 (Guidelines for identification)
GDPR (Nariadenie EÚ 2016/679) - Článok 6 (Právny základ spracovania)
NIST SP 800-86 - Section 3.1.1 (Collection Phase)

## Stav

K otestovaniu

## Nález

(prázdne - vyplní sa po teste)

---------------------------------------------------------------------
## Poznámky k implementácii

**Praktické rozšírenia oproti teoretickému návrhu v diplomovej práci:**

Teoretická časť (Kapitola 3.3.2, Kroky 1-2) uvádza len:
- Vytvorenie Case ID
- Záznam typu média, výrobcu, kapacity a viditeľného poškodenia

**Implementácia rozširuje tento krok o:**

1. **Kompletné údaje klienta** (meno/firma, email, telefón, adresa) - potrebné pre komerčné využitie a komunikáciu s klientom
2. **Urgentnosť a SLA** (štandardná/vysoká/kritická) - nastavenie realistických očakávaní a časových rámcov
3. **GDPR právny základ** - súlad s legislatívou pri spracovaní osobných údajov (relevantné pre fotografie obsahujúce osobné údaje)
4. **Príjmový protokol s podpisom** - formálne potvrdenie prijatia média a podmienok
5. **Potvrdzovací email** - automatická komunikácia s klientom o stave prípadu
6. **Štruktúrované podkroky 1-7** - detailný návod na vykonanie kroku v praxi

Tieto rozšírenia budú doplnené do implementačnej kapitoly diplomovej práce s odôvodnením ich potreby pre praktické nasadenie systému v komerčnom prostredí forenzných laboratórií a orgánov činných v trestnom konaní.3