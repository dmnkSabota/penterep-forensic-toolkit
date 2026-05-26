# Detaily testu

## Úkol

Konsolidovat zprávy do hlavního dokumentu řetězce důkazů, exportovat kompletní dokumentaci případu, předat vyšetřovateli a formálně uzavřít případ.

## Obtížnost

Jednoduchá

## Časová náročnost

30 minut

## Automatický test

Ano

## Popis

Závěrečný krok kombinuje **automatizovanou konsolidaci** (`ptcocmanager --mode consolidate`) s **manuálním fyzickým předáním**. Skript konsoliduje všechny JSON zprávy z pracovního postupu do jednoho hlavního dokumentu řetězce důkazů s chronologickou časovou osou a manifestem SHA-256. Tento dokument je primárním vstupem pro PDF a JSON export, který platforma Penterep předá vyšetřovateli. Fyzické předání s ověřením totožnosti, podpisy a aktualizací formuláře řetězce důkazů je právní úkon vyžadující lidskou odpovědnost – tuto část kroku není možné automatizovat.

## Jak na to

**1. Spuštění konsolidace:**

Skript automaticky detekuje scénář z předpony `COC-*` a načte všechny dostupné zprávy:

```bash
CASE_ID="COC-2025-01-26-001"

# Pouze terminálový výstup
ptcocmanager ${CASE_ID} --mode consolidate \
  --storage-location "Místnost B03, Regál 4, Polička 2" \
  --analyst "Jméno Analytika"

# S JSON výstupem (hlavní dokument řetězce důkazů)
ptcocmanager ${CASE_ID} --mode consolidate \
  --storage-location "Místnost B03, Regál 4, Polička 2" \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_coc_master.json
```

**2. Jaké zprávy skript hledá:**

Automatické vyhledávání projde tyto vzory názvů v `--output-dir`:

| Typ | Zdrojový skript | Vzor názvu |
|-----|-----------------|------------|
| readability | `ptmediareadability` (Kontrola čitelnosti) | `${CASE_ID}_readability.json` |
| imaging | `ptforensicimaging` (Forenzní imaging) | `${CASE_ID}_imaging.json` |
| verification | `ptimageverification` (Verifikace integrity) | `${CASE_ID}_verification.json` |

Pro scénář Chain of Custody jsou očekávané pouze tyto tři zprávy (žádná analytická fáze). Povinné jsou `imaging` a `verification`, `readability` je volitelná. Soubor `${CASE_ID}_coc_gate.json` z předchozího kroku konsolidace nevyhledává — záznam o křížovém ověření vznikne nanovo během konsolidace. Původní `coc_gate.json` zůstává archivován samostatně jako auditní záznam fyzických úkonů.

**3. Struktura hlavního JSON dokumentu řetězce důkazů:**

Skript vytvoří `${CASE_ID}_coc_master.json` se třemi hlavními uzly:

**Uzel `cocTimeline`** – chronologická časová osa záznamů řetězce důkazů načtených ze zpráv. Skript převezme všechny uzly `chainOfCustodyEntry` ze souborů readability, imaging a verification a uspořádá je podle časové značky. Hodnoty pole `action` jsou ve zprávách zapsané v angličtině (formát je dán skriptem):

```json
"cocTimeline": {
  "entryCount": 3,
  "sourceReports": ["imaging", "verification", "readability"],
  "entries": [
    {"timestamp": "2025-01-26T10:00:00Z", "action": "Media readability test - result: READABLE", "analyst": "Jméno Analytika", "result": "SUCCESS", "tool": "", "sourceReport": "readability"},
    {"timestamp": "2025-01-26T11:00:00Z", "action": "Forensic imaging complete", "analyst": "Jméno Analytika", "result": "SUCCESS", "tool": "dc3dd", "sourceReport": "imaging"},
    {"timestamp": "2025-01-26T12:00:00Z", "action": "Image hash verification - result: VERIFIED", "analyst": "Jméno Analytika", "result": "SUCCESS", "tool": "", "sourceReport": "verification"}
  ]
}
```

**Uzel `cocDocumentation`** – hlavní dokument řetězce důkazů:
```json
"cocDocumentation": {
  "scenario": "chain-of-custody",
  "mode": "consolidate",
  "storageLocation": "Místnost B03, Regál 4, Polička 2",
  "documentationTimestamp": "2025-01-26T14:00:00Z",
  "sourceHash": "a3f5e8c9...",
  "imageHash": "a3f5e8c9...",
  "imagePath": "/var/forensics/images/COC-2025-01-26-001.dd",
  "imageSizeBytes": 500107862016,
  "toolVersion": "7.2.646",
  "writeBlockerConfirmed": true,
  "mediaStatus": "READABLE",
  "crossValidated": true,
  "scenarioSpecific": {
    "storage": {"location": "Místnost B03, Regál 4, Polička 2"}
  },
  "artefacts": [
    {"type": "forensic_image", "path": "/var/forensics/images/COC-2025-01-26-001.dd", "sha256": "a3f5...", "sizeBytes": 500107862016, "sourceReport": "imaging"}
  ]
}
```

**Uzel `manifest`** – SHA-256 každé načtené zprávy (pro vyšetřovatele k ověření):
```json
"manifest": {
  "generatedAt": "2025-01-26T14:00:00Z",
  "fileCount": 3,
  "files": [
    {"filename": "COC-2025-01-26-001_imaging.json", "path": "...", "label": "imaging", "sha256": "...", "sizeBytes": 12345},
    {"filename": "COC-2025-01-26-001_readability.json", "path": "...", "label": "readability", "sha256": "...", "sizeBytes": 8901},
    {"filename": "COC-2025-01-26-001_verification.json", "path": "...", "label": "verification", "sha256": "...", "sizeBytes": 6789}
  ]
}
```

**4. Export dokumentace:**

Platforma Penterep vezme `${CASE_ID}_coc_master.json` jako primární vstup a vygeneruje:
- `${CASE_ID}_documentation.pdf` – pro právní použití (titulní strana, přehled případu, technická dokumentace, kryptografické ověření, časová osa řetězce důkazů z hlavního JSON, příloha formuláře řetězce důkazů)
- `${CASE_ID}_documentation.json` – pro automatizované zpracování

Po vygenerování systém vypočítá SHA-256 hash obou dokumentů.

**5. Příprava předávací sady:**

Zkompletujte předávací sadu:
- Vytištěný PDF dokument
- USB nosič s digitálními verzemi (PDF + JSON + `${CASE_ID}_coc_master.json`)
- Podepsaný papírový formulář řetězce důkazů (z kroku CoC brána a uložení)
- Předávací protokol

Manifest pro předání už existuje v `${CASE_ID}_coc_master.json` v uzlu `manifest` – vyšetřovatel může ověřit integritu přijatých dat:

```bash
sha256sum COC-2025-01-26-001_imaging.json
# Porovnej s hodnotou v coc_master.json → manifest.files[].sha256
```

**6. Fyzické předání:**

Ověřte totožnost vyšetřovatele. Vyšetřovatel může před podpisem ověřit integritu dokumentů porovnáním SHA-256 hashů s manifestem v hlavním dokumentu řetězce důkazů:

```bash
sha256sum COC-2025-01-26-001_documentation.pdf
sha256sum COC-2025-01-26-001_coc_master.json
```

Obě strany podepíší předávací protokol s datem a časem – každá strana dostane jednu kopii.

**7. Uzavření případu:**

Doplňte do papírového formuláře řetězce důkazů sekci „Záznamy o předání" (jméno přebírající osoby, datum, účel předání) a formulář znovu podepište. Nastavte stav případu na `CLOSED` v `case.json`:

```json
{
  "timestamp": "2025-01-26T14:30:00Z",
  "analyst": "Jméno Analytika",
  "action": "Dokumentace předána vyšetřovateli, případ uzavřen – stav: CLOSED",
  "recipient": "Jméno Vyšetřovatele"
}
```

Forenzní obraz zůstává archivován pro případné další analýzy. Originální médium zůstává v zabezpečené úschovně.

## Výsledek

Po dokončení kroku existují tyto výstupy:
- `${CASE_ID}_coc_master.json` – hlavní dokument řetězce důkazů (vstup pro PDF/JSON export a budoucí auditní nebo soudní použití)
- PDF a JSON dokumentace vygenerovaná platformou Penterep
- Podepsaný předávací protokol (dvě kopie)
- USB nosič s dokumentací předaný vyšetřovateli
- Papírový formulář řetězce důkazů aktualizovaný sekcí předání
- Případ uzavřen se stavem `CLOSED`, kompletní záznam řetězce důkazů archivován

## Reference

ISO/IEC 27037:2012 – Section 6.1 (Chain of custody) & Section 6.6 (Documentation)

ISO/IEC 27042:2015 – Section 6 (Analytical processes and reporting)

NIST SP 800-86 – Section 3.4 (Reporting)

NIST FIPS 180-4 – Secure Hash Standard (SHA-256 pro manifest)

ACPO Good Practice Guide for Digital Evidence v5 – Principle 3 (Audit trail) & Principle 4 (Overall responsibility)

Zákon č. 141/1961 Sb. (Trestní řád) – §65 (Nahlížení do spisů), §89 (Důkaz)

## Stav

Hybridní – automatická konsolidace a manuální předání

## Nález

(prázdné – vyplní se po předání)