# Detaily testu

## Úkol

Vypočítať SHA-256 hash vytvoreného forenzného obrazu pre overenie integrity procesu imaging.

## Obtiažnosť

Snadné

## Časová náročnosť

45

## Automatický test

Áno - Python skript vypočíta SHA-256 hash forenzného obrazu

## Popis

Výpočet hashu forenzného obrazu je druhý krok trojfázového procesu zabezpečenia integrity. Tento hash sa porovná s hashom originálneho média (z Kroku 6), aby sme matematicky overili, že obraz je presná kópia originálu.

Prečo je tento krok kritický:
- Umožňuje verifikáciu, že imaging proces prebehol bez chýb
- Detekuje akékoľvek rozdiely medzi originálom a obrazom
- Poskytuje matematický dôkaz integrity
- Je súčasťou forenzných štandardov

POZNÁMKA: Tento krok je integrovaný do Kroku 5 (POST-IMAGING fáza), ale je vyčlenený ako samostatný krok pre prehľadnosť workflow.

## Jak na to

1. Najdi vytvorený forenzný obraz (súbor .dd, .raw alebo .E01)
2. Pre RAW obrazy (.dd, .raw) použij príkaz: sha256sum evidence.dd
3. Pre E01 obrazy použij: ewfverify evidence.E01 (E01 má integrovaný hash)
4. Proces môže trvať 30-60 minút podľa veľkosti obrazu
5. Zaznamenať výslednú hash hodnotu (64 hexadecimálnych znakov)
6. Uložiť hash do databázy spolu s časovou značkou
7. Hash sa automaticky použije v Kroku 9 na porovnanie s originálom

---

## Výsledek

SHA-256 hash forenzného obrazu vypočítaný a uložený. Táto hodnota sa v Kroku 9 porovná s hashom originálneho média na verifikáciu integrity.

## Reference

NIST SP 800-86 - Section 3.1.2 (Data Integrity)
ISO/IEC 27037:2012 - Section 7.2 (Verification of integrity)
RFC 6234 - US Secure Hash Algorithms (SHA-256)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
  "hash_algorithm": "SHA-256",
  "hash_value": "a1b2c3d4e5f6...",
  "timestamp": "2026-01-21T15:45:30Z",
  "duration_seconds": 1847,
  "operator": "forensic_analyst_01"
}
```

## Výkonnostné poznámky
- Výpočet hashu veľkého obrazu môže trvať hodiny
- Progress bar je dôležitý pre monitoring
- Možnosť paralelného počítania (ak je dostatok RAM)

## Porovnanie s originálom
Automatická príprava na krok 9:
```python
original_hash = load_hash_from_step6(case_id)
image_hash = calculate_image_hash(image_path)

comparison_ready = {
    "original": original_hash,
    "image": image_hash,
    "match": original_hash == image_hash
}
```

## Dôležité
- Hash hodnota obrazu **MUSÍ** byť identická s hashom originálneho média
- Akýkoľvek rozdiel znamená problém v procese imaging
- Pre právne účely je tento krok povinný
