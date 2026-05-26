# penterep-forensic-toolkit

**Bc. Dominik Sabota** · VUT FEKT Brno · 2026  
Diplomová práca: *Rozšírenie penetračnej testovacej platformy o forenznú analýzu dát*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-green)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-lightgrey)](https://kernel.org/)
[![Verzia](https://img.shields.io/badge/Verzia-1.0.0-orange)](ptforensicanalysis/_version.py)

---

## O projekte

Toolkit rozširuje open-source platformu **Penterep** o štruktúrovanú digitálnu forenznú analýzu. Skladá sa z 18 Python nástrojov pokrývajúcich tri kompletné forenzné pracovné postupy — od akvizície média cez obnovu fotografií až po vyšetrovanie malvéru. Každý nástroj produkuje JSON výstup so zabudovaným Chain-of-Custody auditným záznamom a SHA-256 overením integrity podľa NIST SP 800-86.

Projekt vznikol ako praktický artefakt diplomovej práce a jeho celý kód je pokrytý automatizovanou testovacou sadou (18 sád, 200+ testov) s referenčnými hodnotami z NIST FIPS 180-4.

---

## Štruktúra repozitára

```
ptforensictoolkit/
│
├── ptforensicanalysis/           # Python balík — všetky forenzné nástroje
│   ├── _version.py               # Verzia balíka (1.0.0)
│   ├── _constants.py             # Zdieľané konštanty, timeouty, prahy
│   ├── ptforensictoolbase.py     # Abstraktná základná trieda (ForensicToolBase)
│   │
│   ├── ptcocmanager.py           # Správa Chain-of-Custody brán
│   ├── ptmediareadability.py     # Kontrola čitateľnosti média
│   ├── ptforensicimaging.py      # Forenzný imaging (dc3dd / ddrescue / ewfacquire)
│   ├── ptimageverification.py    # Verifikácia integrity obrazu (SHA-256 / ewfverify)
│   ├── ptintegrityvalidation.py  # Kryptografická validácia integrity súborov
│   ├── ptfilesystemanalysis.py   # Analýza oddielov a súborového systému (mmls/fsstat/fls)
│   ├── ptfilesystemrecovery.py   # Obnova fotografií zo súborového systému (icat)
│   ├── ptfilecarving.py          # Obnova pomocou file carvingu (photorec)
│   ├── ptrecoveryconsolidation.py# Konsolidácia a deduplikácia výsledkov obnovy
│   ├── ptrepairdecision.py       # Rozhodovací engine pre opravu fotografií (pravidlá)
│   ├── ptphotorepair.py          # Štrukturálna oprava JPEG/PNG (jpegtran / Pillow)
│   ├── ptexifanalysis.py         # Extrakcia a analýza EXIF metadát
│   ├── ptvolatilecollector.py    # Zber RAM a volatilných dát (LiME / dd)
│   ├── ptstaticanalysis.py       # Statická analýza malvéru (strings, PE/ELF hlavičky)
│   ├── ptartefactextractor.py    # Extrakcia artefaktov z forenzných obrazov
│   ├── ptthreatintel.py          # Threat intelligence (VirusTotal API)
│   └── ptiocreport.py            # Generovanie IoC reportu a YARA pravidiel
│
├── testsuite/                    # Automatizovaná testovacia sada
│   ├── testlib/
│   │   ├── reference_values.sh   # SHA-256 vektory NIST FIPS 180-4
│   │   └── test_framework.sh     # Pomocné funkcie pre assert, pass/fail
│   ├── run_all_tests.sh          # Hlavný runner (všetkých 18 sád)
│   └── run_all_tests_<tool>.sh   # Per-modul testovacia sada (18 súborov)
│
├── Scenario-1-chain_of_custody/
├── Scenario-2-photo_recovery/
├── Scenario-3-malware_investigation/
├── diagrams/                     # SVG diagramy pracovných postupov
└── README.md
```

---

## Forenzné scenáre

Toolkit je organizovaný okolo troch realistických vyšetrovacích postupov. Každý je zdokumentovaný diagramom nižšie a detailným step-by-step sprievodcom v príslušnom adresári.

---

### Scenár 1 — Chain of Custody

Všeobecný postup pre akvizíciu digitálneho dôkazu a vedenie reťazca opatrovania. Výsledkom je forenzný obraz média s overenými SHA-256 odtlačkami a podpísanou CoC dokumentáciou.

![Scenár 1 — Chain of Custody](diagrams/scenario1_chain_of_custody.svg)

| Krok | Modul | Popis |
|------|-------|-------|
| 1 | — | Inicializácia prípadu a príjem |
| 2 | `ptmediareadability` | Overenie dostupnosti média |
| 3 | — | Identifikácia zariadenia |
| 4 | `ptmediareadability` | Kontrola čitateľnosti → eskalácia pri UNREADABLE |
| 5 | `ptforensicimaging` | Forenzný imaging + výpočet SHA-256 |
| 6 | `ptimageverification` | Verifikácia integrity hashu obrazu |
| 7 | `ptcocmanager` | CoC gate — pečate, štítky, úschovňa |
| 8 | — | Export a odovzdanie vyšetrovateľovi |

---

### Scenár 2 — Obnova fotografií

Kompletný pipeline pre obnovu fotografií z poškodeného, vymazaného alebo skompromitovaného úložného média. Zahŕňa fyzickú opravu média, forenzný imaging, analýzu súborového systému, file carving, validáciu integrity a opravu poškodených súborov.

![Scenár 2 — Obnova fotografií](diagrams/scenario2_photo_recovery.svg)

| Krok | Modul | Popis |
|------|-------|-------|
| 1–7 | (rovnaké ako Scenár 1) | Akvizícia a CoC |
| 8 | `ptfilesystemanalysis` | Analýza súborového systému (mmls/fsstat/fls) |
| 9a | `ptfilesystemrecovery` | Obnova zo súborového systému — ak je FS intaktný |
| 9b | `ptfilecarving` | File carving (photorec) — ak je FS poškodený |
| 10 | `ptrecoveryconsolidation` | Konsolidácia a SHA-256 deduplikácia |
| 11 | `ptintegrityvalidation` | Validácia integrity každého súboru |
| 12–13 | `ptrepairdecision` + `ptphotorepair` | Rozhodnutie o oprave + štrukturálna oprava |
| 14 | `ptexifanalysis` | Extrakcia a anomálna analýza EXIF |
| 15 | `ptcocmanager` | CoC konsolidácia (master CoC) |
| 16–17 | — | Finálny report a odovzdanie |

---

### Scenár 3 — Vyšetrovanie malvéru

Live-response a post-mortem postup pre vyšetrovanie podozrenia na malvér na Linux systéme. Pri živom systéme sa najskôr zbierajú volatilné dáta (RAM, procesy, sieťové spojenia), pri mŕtvom systéme sa priamo pokračuje forenzným imagingom.

![Scenár 3 — Vyšetrovanie malvéru](diagrams/scenario3_malware_investigation.svg)

| Krok | Modul | Popis |
|------|-------|-------|
| 1 | — | Hlásenie incidentu a izolácia systému |
| 2 | — | Určenie stavu systému (LIVE / DEAD) |
| 3 | `ptvolatilecollector` | Zber RAM a volatilných dát (LiME / dd) — iba LIVE |
| 4 | `ptforensicimaging` | Post-mortem forenzný imaging + SHA-256 |
| 5 | `ptimageverification` | Verifikácia integrity obrazu |
| 6 | `ptcocmanager` | CoC gate — zabezpečenie evidencie |
| 7 | `ptstaticanalysis` | Statická analýza (strings, PE/ELF hlavičky, entropia) |
| 8 | — | Dynamická analýza (sandbox) |
| 9 | `ptartefactextractor` | Extrakcia artefaktov z obrazu |
| 10 | `ptiocreport` | IoC report + generovanie YARA pravidiel |
| 11 | `ptthreatintel` | Threat intelligence (VirusTotal, OTX) |
| 12 | — | Forenzný report a návrh nápravy |
| 13 | `ptcocmanager` | CoC konsolidácia (master CoC) |
| 14 | — | Archivácia a uzavretie prípadu |

---

## Prehľad modulov

| Modul | Externé nástroje |
|-------|-----------------|
| `ptcocmanager` | — (čistý Python) |
| `ptmediareadability` | `lsblk`, `blkid`, `smartctl`, `hdparm` |
| `ptforensicimaging` | `dc3dd`, `ddrescue`, `ewfacquire` |
| `ptimageverification` | `sha256sum`, `ewfverify` |
| `ptfilesystemanalysis` | `mmls`, `fsstat`, `fls` (The Sleuth Kit) |
| `ptfilesystemrecovery` | `fls`, `icat`, `exiftool`, `identify` |
| `ptfilecarving` | `photorec`, `identify`, `ewfexport` |
| `ptrecoveryconsolidation` | — (čistý Python) |
| `ptintegrityvalidation` | `jpeginfo`, `pngcheck`, `tiffinfo` |
| `ptrepairdecision` | — (pravidlový engine, čistý Python) |
| `ptphotorepair` | `jpegtran`, Pillow |
| `ptexifanalysis` | `exiftool` |
| `ptvolatilecollector` | `LiME`, `dd`, `ps`, `ss` / `netstat` |
| `ptstaticanalysis` | `strings`, `file` |
| `ptartefactextractor` | `fls`, `icat` |
| `ptthreatintel` | VirusTotal API v3 |
| `ptiocreport` | — (čistý Python) |

Všetky moduly podporujú `--json-out <súbor>` pre strojovo čitateľný výstup a `--quiet` pre potlačenie konzolového výstupu. Pre bezpečné testovanie bez skutočnej akvizície je k dispozícii `--dry-run`.

---

## Inštalácia

### Systémové závislosti

```bash
sudo apt-get install \
    util-linux e2fsprogs smartmontools hdparm \
    dc3dd gddrescue libewf-tools \
    sleuthkit testdisk \
    imagemagick libimage-exiftool-perl \
    jpeginfo pngcheck libtiff-tools libjpeg-turbo-progs \
    iproute2 net-tools
```

Pre akvizíciu RAM (Scenár 3):
```bash
sudo apt-get install lime-forensics-dkms
```

### Python závislosti

```bash
pip install -r ptforensicanalysis/requirements.txt
# ptlibs>=1.0.25, Pillow>=9.0, pexpect>=4.8
```

> Akvizičné nástroje vyžadujú spustenie ako `root` alebo s `CAP_SYS_RAWIO`. Toolkit nikdy neinštalujte ani nespúšťajte na vyšetrovanom systéme.

---

## Rýchly štart

```bash
# Scenár 2 — obnova fotografií (skrátená ukážka)

# Krok 2 — kontrola čitateľnosti média
python -m ptforensicanalysis.ptmediareadability PRIPAD-001 /dev/sdb \
    --analyst "J. Novák" --json-out krok02.json

# Krok 5 — forenzný imaging
python -m ptforensicanalysis.ptforensicimaging PRIPAD-001 /dev/sdb \
    --output-dir /var/forensics/images \
    --analyst "J. Novák" --json-out krok05.json

# Krok 8 — analýza súborového systému
python -m ptforensicanalysis.ptfilesystemanalysis PRIPAD-001 \
    /var/forensics/images/PRIPAD-001.dd \
    --analyst "J. Novák" --json-out krok08.json

# Krok 9b — file carving
python -m ptforensicanalysis.ptfilecarving PRIPAD-001 \
    /var/forensics/images/PRIPAD-001.dd \
    --output-dir /var/forensics/recovered \
    --analyst "J. Novák" --json-out krok09b.json

# Testovanie bez skutočnej akvizície
python -m ptforensicanalysis.ptforensicimaging PRIPAD-001 /dev/sdb \
    --analyst "J. Novák" --dry-run --json-out krok05_dry.json
```

---

## Návratové kódy

| Kód | Význam |
|-----|--------|
| `0` | Nominálne dokončenie (`VERIFIED`, `READABLE`, brána `PASS`) |
| `1` | Chyba spracovania alebo forenzný nález (`MISMATCH`, 0 súborov) |
| `2` | Špecifický nález (`UNREADABLE` médium) |
| `99` | Chyba prostredia (chýbajúci externý nástroj, blocker odmietnutý) |
| `130` | Prerušené signálom SIGINT |

---

## Testovacia sada

Každý z 18 modulov má vlastný testovací skript v adresári `testsuite/`. Všetky skripty zdieľajú pomocnú knižnicu `testsuite/testlib/` s NIST referenčnými vektormi a assertion funkciami.

```bash
# Spustenie všetkých 18 sád s agregovaným súhrnom
./testsuite/run_all_tests.sh

# Jedna sada
./testsuite/run_all_tests_photorepair.sh

# S pokrytím (vyžaduje pip install coverage)
./testsuite/run_all_tests.sh --coverage

# Pre CI (bez farby)
NO_COLOR=1 ./testsuite/run_all_tests.sh

# Filter podľa názvu nástroja
./testsuite/run_all_tests.sh --filter media
```

Každá sada testuje päť kategórií (podľa kap. 5.4.2 diplomovej práce):

| Kategória | Zameranie |
|-----------|-----------|
| A | Hlavný pracovný postup (typické vstupy) |
| B | Chybové podmienky (chýbajúce vstupy, neplatný stav) |
| C | Hraničné prípady (prázdny vstup, prahy, maximá) |
| D | Štruktúra JSON výstupu a úplnosť CoC polí |
| E | Návratové kódy (0 / 1 / 2 / 99) |

Všetky referenčné SHA-256 hodnoty pochádzajú z **NIST FIPS 180-4** štandardu alebo sú nezávisle vypočítané v rámci testu pomocou `sha256sum` (krížová validácia podľa NIST SP 800-86). Žiadny test neobsahuje pevne zapísanú hashovaciu hodnotu.

---

## Súlad so štandardmi

| Štandard | Použitie |
|----------|----------|
| NIST SP 800-86 | Forenzná akvizícia a spracovanie dôkazov |
| NIST FIPS 180-4 | SHA-256 pri akvizícii a verifikácii integrity |
| ISO/IEC 10918-1 | Formát JPEG (validácia a oprava) |
| ISO/IEC 15948 | Formát PNG (validácia) |
| TIFF 6.0 (Adobe) | Formát TIFF (validácia) |
| The Sleuth Kit konvencie | Výstupný formát analýzy súborového systému |

---

## Akademický kontext

Projekt bol vyvinutý ako praktický artefakt k diplomovej práci:

> **Rozšírenie penetračnej testovacej platformy o forenznú analýzu dát**  
> Bc. Dominik Sabota — Vysoké učení technické v Brně, Fakulta elektrotechniky a komunikačních technologií, 2026

Práca rozširuje platformu [Penterep](https://github.com/Penterep) (FIT VUT Brno) o tri kompletné forenzné pracovné postupy, zdieľanú základnú knižnicu a automatizovanú testovaciu sadu. Implementácia sa riadi princípmi forenznej korektnosti z NIST SP 800-86 a vývojovými konvenciami projektu Penterep.

---

## Licencia

Copyright © 2026 Bc. Dominik Sabota, VUT FEKT Brno  
Vydané pod licenciou **GNU General Public License v3.0** — pozri [LICENSE](LICENSE).

Toolkit využíva externé nástroje (`dc3dd`, `ddrescue`, `photorec`, The Sleuth Kit, ExifTool), ktoré sú distribuované pod vlastnými licenciami.