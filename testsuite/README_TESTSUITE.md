# Testovacia sada: penterep-forensic-toolkit

Testovacia sada k diplomovej práci *Rozšírenie penetračnej testovacej
platformy o forenznú analýzu dát*, VUT FEKT Brno, 2026.

**Autor:** Bc. Dominik Sabota
**Licencia:** GPL-3.0

## Štruktúra adresára

```
testsuite/
├── testlib/
│   ├── reference_values.sh        # Vektory NIST FIPS 180-4 a konštanty
│   └── test_framework.sh          # Pomocné funkcie pass/fail/assert_*
├── run_all_tests.sh               # Hlavný runner
├── run_all_tests_<tool>.sh        # 18 testovacích sád pre jednotlivé nástroje
└── README_TESTSUITE.md
```

## Spoločná knižnica `testlib/`

Osemnásť testovacích skriptov zdieľa referenčné vektory NIST, návratové
kódy a pomocné assertion funkcie. Centralizácia týchto prvkov do
adresára `testlib/` znižuje duplicitu (princíp DRY) a umožňuje, aby sa
každý skript sústredil na špecifiká testovaného nástroja.

## Pôvod referenčných hodnôt

Očakávané SHA-256 odtlačky pochádzajú výhradne z dvoch zdrojov:

1. **Štandardné vektory NIST FIPS 180-4** (`reference_values.sh`):
   - Prázdny reťazec: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
   - `"abc"`: `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`
   - 56-znakový reťazec `"abcdbcde..."`: `248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1`
   - 1 000 000 × `'a'`: `cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0`

2. **Nezávisle vypočítané hodnoty** pomocou utility `sha256sum`
   spustenej na fixtúrach, ktoré si test sám vytvorí
   (napr. `dd if=/dev/zero count=1024 | sha256sum`). Výstup testovaného
   nástroja sa následne porovnáva s externe vypočítanou hodnotou; ide
   o štandardný vzor krížovej validácie podľa NIST SP 800-86.

Žiadny test neobsahuje pevne zapísanú hodnotu typu
`TEST_HASH = "abc123"`. Každá očakávaná hodnota je buď dohľadateľná
v publikovanej norme, alebo je vypočítaná nezávisle v rámci testu.

## Spustenie

```bash
# Spustenie jednej testovacej sady
./run_all_tests_cocmanager.sh

# Spustenie všetkých 18 sád s agregovaným súhrnom
./run_all_tests.sh

# So zberom pokrytia (vyžaduje pip install coverage)
./run_all_tests.sh --coverage

# Bez farieb (vhodné pre CI logy)
NO_COLOR=1 ./run_all_tests.sh

# Filtrovanie podľa názvu nástroja
./run_all_tests.sh --filter media
```

## Návratové kódy

| Kód | Význam                                              |
|-----|-----------------------------------------------------|
| 0   | Všetky sady prešli                                  |
| 1   | Aspoň jedna sada nahlásila zlyhanie                 |
| 2   | Neobjavené žiadne testovacie sady (konfiguračná chyba) |
| 99  | Chýbajú predpoklady prostredia (Python, externé nástroje) |

## Kategórie testov

Každá per-tool sada dodržuje päťkategóriový model definovaný
v kapitole 5.4.2 diplomovej práce:

| Kategória | Účel                                                  |
|-----------|-------------------------------------------------------|
| A         | Hlavný pracovný postup (typické vstupy)               |
| B         | Chybové podmienky (chýbajúce vstupy, neplatný stav)   |
| C         | Hraničné prípady (prázdny vstup, prahy, maximá)       |
| D         | Štruktúra výstupu JSON a Chain-of-Custody             |
| E         | Návratové kódy (0 úspech, 1 zlyhanie, 2 nález, 99 prostredie) |

## Externé závislosti

Testovaný toolkit volá externé binárne nástroje (`dc3dd`, `mmls`,
`photorec`, `exiftool` a ďalšie). Testovacie skripty ich nahrádzajú
mock implementáciami so zhodným výstupným formátom, čím sa parsovacia
logika toolkitu izoluje od dostupnosti reálnych binárok. Správanie
nástrojov na fyzickom médiu pokrývajú integračné testy popísané
v kapitole 5 diplomovej práce.

## Umiestnenie v repozitári

Celý adresár `testsuite/` sa očakáva v koreni repozitára
`penterep-forensic-toolkit`, aby testovacie skripty našli testované
nástroje cez `${SCRIPT_DIR}/pt<tool>.py`.