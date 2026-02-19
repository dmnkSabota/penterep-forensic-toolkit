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

Prvý krok procesu obnovy fotografií začína formálnym prijatím žiadosti od klienta. Vytvorí sa unikátny identifikátor prípadu (Case ID), zaznamenajú sa základné informácie o klientovi a médiu, inicializuje sa Chain of Custody log a spustí sa dokumentačný proces v súlade s ISO/IEC 27037:2012.

## Jak na to

**1. Vytvorenie Case ID:**

Vytvorte Case ID podľa formátu PHOTO-YYYY-MM-DD-XXX, kde YYYY-MM-DD je aktuálny dátum a XXX je poradové číslo prípadu v daný deň (napríklad PHOTO-2025-01-26-001). Overte, že Case ID ešte neexistuje v databáze.

**2. Údaje klienta:**

Vyplňte kontaktné údaje klienta: meno alebo názov firmy, email, telefónne číslo a fakturačnú adresu ak je dostupná.

**3. Informácie o médiu:**

Zaznamenajte základné informácie podľa toho, čo klient uvádza: typ zariadenia (SD karta, microSD, USB flash disk, HDD, SSD alebo iné), odhadovanú kapacitu a popis prípadného viditeľného poškodenia. Tieto údaje budú overené fyzicky v nasledujúcom kroku.

**4. Urgentnosť a SLA:**

Dohodnite s klientom urgentnosť prípadu:
- Štandardná (5–7 pracovných dní)
- Vysoká (2–3 pracovné dni)
- Kritická (do 24 hodín)

**5. GDPR súlad:**

Zvoľte právny základ spracovania osobných údajov: pre komerčnú obnovu "plnenie zmluvy", pre súdne prípady "právna povinnosť".

**6. Príjmový protokol:**

Platforma vygeneruje príjmový protokol vo formáte PDF. Vytlačte ho, nechajte klienta podpísať a naskenovanú verziu archivujte do dokumentácie Case. Podpis a skenovanie sú manuálne aktivity mimo systému.

**7. Finalizácia:**

Uložte Case a skontrolujte, že bol vytvorený Case ID dokument (JSON) a inicializovaný Chain of Custody log s prvým záznamom. Potvrdzovací email s číslom prípadu a ďalšími krokmi odošlite klientovi manuálne.

## Výsledek

Po dokončení kroku existujú tieto výstupy:
- Case ID dokument (JSON) so stavom "INITIATED"
- Príjmový protokol (PDF) s podpisom klienta
- Inicializovaný Chain of Custody log – prvý záznam obsahuje Case ID, dátum a čas prijatia, meno analytika
- Odoslaný potvrdzovací email klientovi

Workflow automaticky postupuje do kroku "Identifikácia média".

## Reference

ISO/IEC 27037:2012 – Section 5 (Guidelines for identification)
GDPR (Nariadenie EÚ 2016/679) – Článok 6 (Právny základ spracovania)
NIST SP 800-86 – Section 3.1.1 (Collection Phase)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Teoretická časť (Kapitola 3.3.2, Kroky 1–2) pokrýva len vytvorenie Case ID a záznam základných údajov o médiu. Implementácia tento základ rozširuje o prvky potrebné pre praktické nasadenie v komerčnom laboratóriu:

Kompletné údaje klienta umožňujú komunikáciu a fakturáciu. Urgentnosť a SLA nastavuje realistické očakávania hneď od začiatku. GDPR právny základ je relevantný najmä pri fotografiách obsahujúcich osobné údaje. Príjmový protokol s podpisom klienta formálne potvrdzuje podmienky spolupráce a odovzdanie média. Inicializácia Chain of Custody logu priamo v kroku 1 zabezpečuje nepretržitý audit trail od momentu prijatia žiadosti – nie až od fyzického prevzatia média.

Tieto rozšírenia budú zdôvodnené v implementačnej kapitole diplomovej práce.