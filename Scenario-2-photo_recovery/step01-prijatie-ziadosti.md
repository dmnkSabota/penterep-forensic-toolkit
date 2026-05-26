# Detaily testu

## Úkol
Přijmout žádost o obnovu fotografií a vytvořit identifikátor případu.

## Obtížnost
Jednoduchá

## Časová náročnost
15 minut

## Automatický test
Ne

## Popis
První krok procesu obnovy fotografií začíná formálním přijetím žádosti od klienta. Analytik manuálně shromáždí všechny potřebné informace, vytvoří jedinečný identifikátor případu a inicializuje záznam řetězce důkazů. Postup vychází z ISO/IEC 27037:2012, který zůstává platným mezinárodním standardem pro zacházení s digitálními důkazy. Identifikátor případu slouží jako primární klíč, pod kterým jsou ukládány výsledky všech následných technických kroků včetně forenzního obrazu média a výsledků obnovy souborů.

## Jak na to

**1. Vytvoření identifikátoru případu:**
Vytvořte identifikátor případu podle formátu `PHOTORECOVERY-RRRR-MM-DD-XXX` a vyplňte ho do formuláře scénáře:
- `PHOTORECOVERY` – pevná předpona identifikující typ scénáře
- `RRRR-MM-DD` – aktuální datum (rok-měsíc-den), například `2025-01-26`
- `XXX` – trojciferné pořadové číslo případu v daný den, začíná od `001`

Příklad prvního případu dne 26. ledna 2025: `PHOTORECOVERY-2025-01-26-001`

Zkontrolujte archiv existujících případů a ověřte, že toto ID ještě nebylo použito.

**2. Údaje klienta:**
Zaznamenejte kontaktní údaje klienta do formuláře scénáře:
- Jméno nebo název firmy
- E-mail
- Telefonní číslo
- Fakturační adresa (je-li k dispozici)

**3. Naléhavost a SLA:**
Dohodněte s klientem naléhavost případu a zaznamenejte zvolenou možnost:
- Standardní (5–7 pracovních dnů)
- Vysoká (2–3 pracovní dny)
- Kritická (do 24 hodin)

**4. Soulad s GDPR:**
Zvolte právní základ zpracování osobních údajů podle čl. 6 nařízení EU 2016/679 a zaznamenejte ho:
- Pro komerční obnovu: čl. 6 odst. 1 písm. b) – plnění smlouvy
- Pro soudní případy: čl. 6 odst. 1 písm. c) – právní povinnost

**5. Příjmový protokol:**
Manuálně vyplňte příjmový protokol. Protokol musí obsahovat minimálně tato pole:
- Identifikátor případu a datum přijetí
- Jméno a kontaktní údaje klienta
- Popis a fyzický stav předaného média
- Podpis klienta a analytika

Vytiskněte ho, nechte klienta podepsat a naskenovanou verzi archivujte do fyzické i digitální dokumentace případu. Fyzickou kopii uložte na příslušné místo.

**6. Inicializace záznamu případu:**
Vytvořte JSON záznam případu a uložte ho pod příslušným identifikátorem případu. Záznam musí obsahovat stav `INITIATED`, kontaktní údaje klienta, zvolenou naléhavost, zaznamenaný právní základ a první zápis do pole `chainOfCustody`.

Příklad záznamu:
```json
{
  "caseId": "PHOTORECOVERY-2025-01-26-001",
  "status": "INITIATED",
  "client": {
    "name": "Jméno Klienta",
    "email": "klient@example.com",
    "phone": "+420 900 000 000",
    "address": "Ulice 1, 000 00 Město"
  },
  "urgency": "standard",
  "gdprBasis": "Art. 6(1)(b) - performance of contract",
  "chainOfCustody": [
    {
      "timestamp": "2025-01-26T09:00:00Z",
      "analyst": "Jméno Analytika",
      "action": "Přijata žádost o obnovu fotografií"
    }
  ]
}
```

**7. Finalizace:**
Zkontrolujte, že záznam případu obsahuje všechna povinná pole: `caseId`, `status`, `client`, první záznam v poli `chainOfCustody`. Potvrzovací e-mail s číslem případu a dalšími kroky odešlete klientovi manuálně.

## Výsledek
Po dokončení kroku existují tyto výstupy:
- Vyplněný záznam případu se stavem `INITIATED` a prvním záznamem `chainOfCustody`
- Vyplněný a podepsaný příjmový protokol (fyzická kopie + naskenovaná digitální kopie)
- Odeslaný potvrzovací e-mail klientovi

## Reference

ISO/IEC 27037:2012 – Section 5.4.2 (Identification) & Section 6.1 (Chain of custody)

GDPR (Nařízení EU 2016/679) – Článek 6 (Zákonnost zpracování)

NIST SP 800-86 – Section 3.1 (Data Collection)

## Stav
K otestování

## Nález
(prázdné – vyplní se po testu)