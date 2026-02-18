[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTREPAIRDECISION – Automated Repair Decision

`ptrepairdecision` is a ptlibs-compliant forensic tool that analyses the
integrity validation results from **Step 15** and automatically decides
whether to perform photo repair (**Step 17**) or proceed directly to
cataloging (**Step 18**). It is **Step 16** in the photo-recovery workflow.

## Prerequisites

Step 15 (`ptintegrityvalidation`) must be completed first.

## Installation

```
pip install ptrepairdecision
```

No system packages required – pure Python + ptlibs.

## Usage examples

```
ptrepairdecision PHOTO-2025-001
ptrepairdecision CASE-042 --json
ptrepairdecision TEST-001 --dry-run
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate with synthetic validation data
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show this help message and exit
    --version         Show version and exit
```

## Decision rules (evaluated top-to-bottom)

| Rule | Condition | Strategy | Confidence |
|------|-----------|----------|-----------|
| R1 | corrupted == 0 | skip_repair → Step 18 | HIGH |
| R2 | repairable == 0 | skip_repair → Step 18 | HIGH |
| R3 | valid < 50 | perform_repair → Step 17 | HIGH |
| R4 | estimate ≥ 50 % | perform_repair → Step 17 | HIGH/MEDIUM |
| R5 | estimate < 50 % | skip_repair → Step 18 | MEDIUM |

## Repair success rate table

| Corruption type | Estimate |
|----------------|---------|
| truncated | 85 % – missing footer bytes |
| invalid_header | 70 % – header reconstruction |
| corrupt_segments | 60 % – segment removal |
| corrupt_data | 40 % – partial pixel recovery |
| fragmented | 15 % – defragmentation |
| false_positive | 0 % – not an image |

## Output

```
{case_id}_repair_decision.json
```

Fields: `strategy`, `nextStep`, `confidence`, `reasoning[]`,
`repairSuccessEstimate`, `expectedOutcome`.

## Standards compliance

- ISO/IEC 27037:2012 Section 7.6 (Decision making)
- NIST SP 800-86 Section 3.2 (Analysis decisions)

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno – GPLv3.
