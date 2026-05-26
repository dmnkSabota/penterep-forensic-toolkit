# Detaily testu

## Úkol

Rozhodnout pro každý REPAIRABLE soubor, zda a jak přistoupit k opravě.

## Obtížnost

Jednoduchá

## Časová náročnost

5 minut

## Automatický test

Ano

## Popis

Tento krok načte výsledky kroku Validace integrity a pro každý REPAIRABLE soubor určí rozhodnutí na základě empiricky odhadované míry úspěšnosti opravy podle typu poškození. Výsledek je čistě analytický – žádné soubory se v tomto kroku nemění.

Rozhodnutí: `ATTEMPT_REPAIR` (postoupí do kroku Oprava fotografií), `MANUAL_REVIEW` (příznak pro analytika, automatická oprava se neprovede), `SKIP` (soubor je považován za neopravitelný).

Míry úspěšnosti vycházejí z odhadů podpořených odkazy v literatuře: Kessler (2007) a Garfinkel et al. (2009).

## Jak na to

**1. Spuštění rozhodovacího kroku:**

```bash
CASE_ID="PHOTORECOVERY-2025-01-26-001"
VALIDATION="/var/forensics/images/${CASE_ID}_integrity_validation.json"

# Pouze terminálový výstup
ptrepairdecision ${CASE_ID} ${VALIDATION} --analyst "Jméno Analytika"

# S JSON výstupem pro case.json
ptrepairdecision ${CASE_ID} ${VALIDATION} \
  --analyst "Jméno Analytika" \
  --json-out ${CASE_ID}_repair_decisions.json

# Simulace bez čtení souborů
ptrepairdecision ${CASE_ID} ${VALIDATION} --dry-run
```

Skript automaticky provede kroky 2–3 pro každý REPAIRABLE soubor ze zprávy validace.

**2. Přiřazení míry úspěšnosti podle typu poškození:**

Pro každý REPAIRABLE soubor vyhledejte `corruptionType` v tabulce:

| Typ poškození | Odhadovaná úspěšnost | Zdroj odhadu |
|---|---|---|
| `missing_footer` | 90 % | Autor; doplnění EOI je spolehlivé pokud jsou data kompletní |
| `invalid_header` | 85 % | Autor; rekonstrukce SOI + APP0 – závisí na integritě segmentu SOS |
| `corrupt_segments` | 60 % | Autor; variabilita podle toho, který segment je poškozený |
| `truncated` | 85 % | Autor; PIL LOAD_TRUNCATED_IMAGES – efektivní při ztrátě konce souboru |
| `corrupt_data` | 40 % | Kessler (2007); poškození v datovém regionu produkuje artefakty |
| `fragmented` | 15 % | Garfinkel et al. (2009); více-fragmentové skládání zřídka uspěje |
| `unknown` | 30 % | Konzervativní odhad pro neklasifikované případy |

**3. Aplikace pravidel R1–R5:**

Na základě míry úspěšnosti aplikujte pravidla v pořadí – první platné pravidlo rozhoduje:

| Pravidlo | Podmínka | Rozhodnutí |
|---|---|---|
| R1 | Úspěšnost ≥ 85 % | `ATTEMPT_REPAIR` |
| R2 | 50 % ≤ úspěšnost < 85 % | `ATTEMPT_REPAIR` |
| R3 | 30 % ≤ úspěšnost < 50 % | `MANUAL_REVIEW` |
| R4 | 15 % ≤ úspěšnost < 30 % | `SKIP` |
| R5 | Úspěšnost < 15 % | `SKIP` |

Pokud automatický nástroj není dostupný, otevřete `{CASE_ID}_integrity_validation.json`, pro každý soubor se stavem `REPAIRABLE` vyhledejte `corruptionType` v tabulce v kroku 2, aplikujte pravidla R1–R5 a výsledné rozhodnutí zapište ručně do `{CASE_ID}_repair_decisions.json`.

**4. Zápis výsledků a aktualizace řetězce důkazů:**

Při použití `--json-out` se vytvoří JSON s výsledky. Analytik manuálně zkopíruje oba záznamy do `case.json`.

Přidávaný objekt `repairDecision`:
```json
"repairDecision": {
  "timestamp": "2025-01-26T16:05:00Z",
  "analyst": "Jméno Analytika",
  "totalRepairable": 198,
  "attemptRepair": 156,
  "manualReview": 29,
  "skip": 13,
  "decisionBreakdown": {
    "missing_footer": {"count": 87, "decision": "ATTEMPT_REPAIR", "rule": "R1"},
    "truncated": {"count": 64, "decision": "ATTEMPT_REPAIR", "rule": "R1"},
    "corrupt_segments": {"count": 31, "decision": "ATTEMPT_REPAIR", "rule": "R2"},
    "corrupt_data": {"count": 16, "decision": "MANUAL_REVIEW", "rule": "R3"}
  },
  "decisionFile": "PHOTORECOVERY-2025-01-26-001_repair_decisions.json"
}
```

Nový záznam do pole `chainOfCustody`:
```json
{
  "timestamp": "2025-01-26T16:05:00Z",
  "analyst": "Jméno Analytika",
  "action": "Rozhodnutí o opravě dokončeno – 156 ATTEMPT_REPAIR, 29 MANUAL_REVIEW, 13 SKIP",
  "mediaSerial": "SN-XXXXXXXX"
}
```

**5. Archivace výstupů:**

Archivujte do dokumentace případu:
- `${CASE_ID}_repair_decisions.json` – seznam rozhodnutí s typem poškození, mírou úspěšnosti, použitým pravidlem a odůvodněním pro každý soubor

## Výsledek

Čistě analytická operace – žádné soubory se nekopírují ani nemění. Výsledky zaznamenány v `{CASE_ID}_repair_decisions.json`. Pracovní postup pokračuje do kroku Oprava fotografií (pokud existují záznamy `ATTEMPT_REPAIR`) nebo přímo do kroku EXIF analýza (pokud všechny záznamy jsou `MANUAL_REVIEW` / `SKIP`).

## Reference

Kessler, G.C. (2007). Anti-forensics and the Digital Investigator. Proceedings of the 5th Australian Digital Forensics Conference. doi:10.4225/75/57B2667BE45CF

Garfinkel, S.L., Farrell, P., Roussev, V., & Dinolt, G. (2009). Bringing Science to Digital Forensics with Standardized Forensic Corpora. Digital Investigation, 6, S2–S11. doi:10.1016/j.diin.2009.06.016

ISO/IEC 27042:2015 – Section 5 (Investigative processes)

NIST SP 800-86 – Section 3.3 (Analysis)

## Stav

K otestování

## Nález

(prázdné – vyplní se po testu)