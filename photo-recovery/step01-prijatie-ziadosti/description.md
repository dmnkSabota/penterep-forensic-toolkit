# Detaily testu

## Úkol

Formálne prijať žiadosť o obnovu fotografií z poškodeného média a vytvoriť Case ID pre sledovanie celého procesu obnovy.

## Obtiažnosť

Snadné

## Časová náročnosť

10

## Automatický test

(prázdne - manuálny krok)

## Popis

Prvý krok každého forenzného procesu obnovy dát začína formálnym prijatím žiadosti od klienta. V tomto kroku sa vytvorí unikátny identifikátor prípadu (Case ID), zaznamenajú sa základné informácie o klientovi a povahe žiadosti, a inicializuje sa dokumentačný proces v súlade s ISO/IEC 27037:2012.

Prečo je tento krok kritický:
- Vytvorenie jedinečného Case ID zabezpečuje sledovateľnosť počas celého procesu
- Presná časová značka prijatia je dôležitá pre Chain of Custody
- Základné informácie o klientovi sú potrebné pre reporting a komunikáciu
- Právny základ žiadosti musí byť dokumentovaný pre GDPR súlad

## Jak na to

1. Vytvor Case ID v formáte PHOTO-YYYY-MM-DD-XXX (napr. PHOTO-2025-01-13-001)
2. Zaznamej informácie o klientovi (meno, email, telefón)
3. Zadaj popis žiadosti a urgentnosť (štandardná / vysoká / kritická)
4. Identifikuj typ média a viditeľné poškodenie
5. Vyber právny základ spracovania podľa GDPR (plnenie zmluvy / právna povinnosť / súhlas / oprávnený záujem)
6. Vygeneruj a archivuj príjmový protokol s podpisom klienta

---

## 📝 FORMULÁR - Vstupné polia

```json
{
  "case_id": {
    "type": "string",
    "pattern": "PHOTO-\\d{4}-\\d{2}-\\d{2}-\\d{3}",
    "auto_generate": true,
    "editable": false,
    "required": true
  },
  "intake_timestamp": {
    "type": "datetime",
    "auto_generate": true,
    "format": "ISO8601",
    "required": true
  },
  "client_info": {
    "name": {
      "type": "string",
      "label": "Meno klienta / Firma",
      "max_length": 200,
      "required": true
    },
    "email": {
      "type": "email",
      "label": "Kontaktný email",
      "required": true
    },
    "phone": {
      "type": "string",
      "label": "Telefónne číslo",
      "pattern": "^\\+?[0-9\\s\\-\\(\\)]{9,20}$",
      "required": true
    },
    "billing_address": {
      "type": "text",
      "label": "Fakturačná adresa",
      "max_length": 500,
      "required": false
    }
  },
  "request_info": {
    "intake_method": {
      "type": "select",
      "label": "Spôsob prijatia",
      "options": ["Osobne", "Poštou", "Kuriérom", "Iné"],
      "required": true
    },
    "description": {
      "type": "textarea",
      "label": "Popis problému",
      "max_length": 500,
      "placeholder": "Napríklad: SD karta z fotoaparátu, náhle prestala fungovať po dovolenke. Klient potrebuje zachrániť fotografie z rodinnej oslavy.",
      "required": true
    },
    "urgency": {
      "type": "select",
      "label": "Urgencia",
      "options": [
        {"value": "standard", "label": "Štandardná (5-7 dní)"},
        {"value": "high", "label": "Vysoká (2-3 dni)"},
        {"value": "critical", "label": "Kritická (24 hodín)"}
      ],
      "default": "standard",
      "required": true
    }
  },
  "media_info": {
    "media_type": {
      "type": "select",
      "label": "Typ média",
      "options": [
        "SD karta",
        "microSD karta",
        "USB flash disk",
        "Pevný disk (HDD)",
        "SSD disk",
        "CF karta (CompactFlash)",
        "Memory Stick",
        "Pamäťová karta fotoaparátu (iná)",
        "Iné"
      ],
      "required": true
    },
    "estimated_capacity": {
      "type": "string",
      "label": "Odhadovaná kapacita",
      "placeholder": "Napr: 64 GB, 1 TB, neznáma",
      "required": false
    },
    "visible_damage": {
      "type": "boolean",
      "label": "Viditeľné fyzické poškodenie?",
      "default": false,
      "required": true
    },
    "damage_description": {
      "type": "textarea",
      "label": "Popis poškodenia",
      "max_length": 300,
      "visible_if": "visible_damage == true",
      "required": false
    }
  },
  "legal_basis": {
    "gdpr_basis": {
      "type": "select",
      "label": "Právny základ spracovania (GDPR)",
      "options": [
        {"value": "contract", "label": "Plnenie zmluvy"},
        {"value": "legal_obligation", "label": "Právna povinnosť"},
        {"value": "consent", "label": "Súhlas subjektu údajov"},
        {"value": "legitimate_interest", "label": "Oprávnený záujem"}
      ],
      "required": true
    },
    "consent_obtained": {
      "type": "boolean",
      "label": "GDPR súhlas získaný?",
      "visible_if": "gdpr_basis == 'consent'",
      "required": true,
      "help_text": "Klient musí podpísať GDPR formulár súhlasu"
    }
  },
  "analyst": {
    "type": "string",
    "label": "Prijímajúci analytik",
    "auto_fill": "current_user",
    "required": true
  },
  "notes": {
    "type": "textarea",
    "label": "Interné poznámky",
    "max_length": 1000,
    "required": false
  }
}
```

## Validačné pravidlá

Pred uložením skontroluj:
1. Case ID je jedinečné (neexistuje v databáze)
2. Email má správny formát
3. Telefónne číslo obsahuje 9-20 znakov
4. Ak je viditeľné poškodenie = áno, popis poškodenia je vyplnený
5. Ak je právny základ = súhlas, checkbox "súhlas získaný" = áno
6. Všetky povinné polia sú vyplnené

## Výsledek

Po úspešnom uložení sa vygeneruje Case ID dokument (JSON), Príjmový protokol (PDF) a Email potvrdenie pre klienta.

**1. Case ID dokument (JSON)**

```json
{
  "case_id": "PHOTO-2025-01-13-001",
  "status": "INITIATED",
  "created_at": "2025-01-13T14:32:15Z",
  "created_by": "analyst@forensicslab.cz",
  "client": {
    "name": "Ján Novák",
    "email": "jan.novak@email.sk",
    "phone": "+421 912 345 678",
    "billing_address": "Hlavná 123, 811 02 Bratislava"
  },
  "request": {
    "intake_method": "Osobne",
    "description": "SD karta z fotoaparátu Canon prestala fungovať po dovolenke. Potrebujem záchrana 200+ fotiek z rodinnej oslavy.",
    "urgency": "high"
  },
  "media": {
    "type": "SD karta",
    "estimated_capacity": "64 GB",
    "visible_damage": false
  },
  "legal": {
    "gdpr_basis": "contract",
    "consent_obtained": null
  },
  "workflow": {
    "current_step": 1,
    "total_steps": 20,
    "next_step": "Identifikácia média"
  }
}
```

**2. Príjmový protokol (PDF)**

Generuje sa automaticky s nasledujúcou štruktúrou:

```
╔═══════════════════════════════════════════════════════════╗
║          PRÍJMOVÝ PROTOKOL - OBNOVA FOTOGRAFIÍ           ║
╚═══════════════════════════════════════════════════════════╝

Case ID: PHOTO-2025-01-13-001
Dátum prijatia: 13.01.2025, 14:32
Prijal: analyst@forensicslab.cz

─────────────────────────────────────────────────────────────
INFORMÁCIE O KLIENTOVI
─────────────────────────────────────────────────────────────
Meno: Ján Novák
Email: jan.novak@email.sk
Telefón: +421 912 345 678

─────────────────────────────────────────────────────────────
POPIS ŽIADOSTI
─────────────────────────────────────────────────────────────
Spôsob prijatia: Osobne
Urgencia: Vysoká (2-3 dni)

Popis problému:
SD karta z fotoaparátu Canon prestala fungovať po dovolenke.
Potrebujem záchrana 200+ fotiek z rodinnej oslavy.

─────────────────────────────────────────────────────────────
INFORMÁCIE O MÉDIU
─────────────────────────────────────────────────────────────
Typ: SD karta
Kapacita: 64 GB (odhadovaná)
Viditeľné poškodenie: Nie

─────────────────────────────────────────────────────────────
PRÁVNY ZÁKLAD
─────────────────────────────────────────────────────────────
GDPR základ: Plnenie zmluvy

─────────────────────────────────────────────────────────────
PODPISY
─────────────────────────────────────────────────────────────

Klient:                          Analytik:

___________________             ___________________
Ján Novák                       [Meno analytika]
Dátum: 13.01.2025               Dátum: 13.01.2025
```

**3. Email potvrdenie klientovi**

```
Predmet: Potvrdenie prijatia žiadosti - Case ID PHOTO-2025-01-13-001

Vážený pán Novák,

potvrdzujeme prijatie Vašej žiadosti o obnovu fotografií.

Case ID: PHOTO-2025-01-13-001
Dátum prijatia: 13.01.2025
Urgencia: Vysoká (2-3 dni)

Vaša žiadosť bola zaregistrovaná a bude spracovaná v nasledujúcich krokoch:
1. Identifikácia a diagnostika média
2. Vytvorenie forenzného obrazu
3. Obnova fotografií
4. Validácia a katalogizácia
5. Dodanie výsledkov

Budeme Vás informovať o priebehu obnovy.

S pozdravom,
Forenzné laboratórium
```

## Reference

ISO/IEC 27037:2012 - Guidelines for identification, collection, acquisition
GDPR (Nariadenie EÚ 2016/679) - Článok 6 (Právny základ spracovania)
NIST SP 800-86 - Section 3.1.1 (Collection Phase)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
