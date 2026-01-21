# Detaily testu

## Úkol

Vypočítať SHA-256 hash originálneho média ako referenčnú hodnotu pre verifikáciu integrity forenzného obrazu.

## Obtiažnosť

Snadné

## Časová náročnosť

45

## Automatický test

Áno - Python skript vypočíta SHA-256 hash celého média

## Popis

Výpočet kryptografického hashu originálneho média je prvý krok trojfázového procesu zabezpečenia integrity. Tento hash slúži ako referenčná hodnota - digitálny odtlačok originálneho média, s ktorým neskôr porovnáme hash vytvoreného forenzného obrazu.

Prečo je tento krok kritický:
- Vytvára matematický dôkaz pôvodného stavu média
- Umožňuje verifikáciu, že obraz je identický s originálom
- Spĺňa forenzné štandardy (NIST, ISO 27037)
- Bez tohto hashu nemáme s čím porovnať obraz

POZNÁMKA: Tento krok je integrovaný do Kroku 5 (PRE-IMAGING fáza), ale je vyčlenený ako samostatný krok pre prehľadnosť workflow.

## Jak na to

1. Overiť, že médium je pripojené CEZ WRITE-BLOCKER (read-only režim)
2. Spustiť automatický výpočet SHA-256 hashu - príkaz: sudo dd if=/dev/sdX bs=1M | sha256sum
3. Proces môže trvať 30-60 minút podľa veľkosti média
4. Zaznamenať výslednú hash hodnotu (64 hexadecimálnych znakov)
5. Uložiť hash do databázy spolu s časovou značkou a metadátami (veľkosť média, názov zariadenia)
6. Hash sa automaticky použije v Kroku 9 na verifikáciu

---

## Výsledek

SHA-256 hash originálneho média vypočítaný a uložený. Táto hodnota slúži ako referencia pre overenie integrity forenzného obrazu v Kroku 9.

## Reference

NIST SP 800-86 - Section 3.1.2 (Data Integrity)
ISO/IEC 27037:2012 - Section 7.2 (Principles for handling digital evidence)
RFC 6234 - US Secure Hash Algorithms (SHA-256)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
  "hash_value": "a1b2c3d4e5f6...",
  "timestamp": "2026-01-21T14:30:45Z",
  "operator": "forensic_analyst_01"
}
```

## Dôležité poznámky
- Hash sa počíta z **originálneho média**, nie z obrazu
- Proces môže trvať dlho pri veľkých médiách
- Hash hodnota musí byť identická s hashom obrazu (overí sa v kroku 9)
- Pre právne účely je možné použiť aj MD5 + SHA-256 súčasne

## Chain of Custody
- Tento krok je kritický pre dokumentáciu integrity dôkazu
- Hash hodnota sa používa ako dôkaz, že obraz je identický s originálom
