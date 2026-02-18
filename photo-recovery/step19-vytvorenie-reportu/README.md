[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTFINALREPORT – Forensic Photo Recovery Final Report Generator

`ptfinalreport` is a ptlibs-compliant forensic tool that consolidates data
from all preceding workflow steps (10–18) into a courtroom-ready 11-section
JSON report, an optional PDF, a client README, and a delivery checklist.
It is **Step 19** – the documentation and handover step.

## Prerequisites

| Source | Step | Status |
|--------|------|--------|
| `{case_id}_validation_report.json` | Step 15 | **Required** |
| `{case_id}_catalog/catalog_summary.json` | Step 18 | **Required** |
| `{case_id}_exif_analysis/exif_database.json` | Step 14 | Optional |
| `{case_id}_repair_report.json` | Step 17 | Optional |

## Installation

```
pip install ptfinalreport
# Optional PDF support:
pip install reportlab --break-system-packages
```

## Usage examples

```
ptfinalreport PHOTO-2025-001
ptfinalreport CASE-042 --json
ptfinalreport TEST-001 --dry-run
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate with synthetic data, no file writes
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show help and exit
    --version         Show version and exit
```

## Six-phase process

| Phase | What happens |
|-------|-------------|
| 1 | Collect JSON reports from steps 14, 15, 17, 18 |
| 2 | Build all 11 report sections |
| 3 | Save `FINAL_REPORT.json` (11 sections) |
| 4 | Generate `FINAL_REPORT.pdf` (optional, requires reportlab) |
| 5 | Create `README.txt` (client instructions, FAQ, 3-2-1 backup guide) |
| 5 | Create `delivery_checklist.json` (7-item pre-delivery verification) |
| 6 | Save `workflow_summary.json` (metrics, completed steps, deliverables) |

## 11-section report structure

| # | Section | Audience |
|---|---------|---------|
| 1 | Executive Summary | Client |
| 2 | Case Information | All |
| 3 | Evidence Information | Legal/Court |
| 4 | Methodology (standards, tools, principles) | Expert |
| 5 | Timeline | All |
| 6 | Results (recovery, repair, metadata) | All |
| 7 | Technical Details | Expert |
| 8 | Quality Assurance | Expert/Court |
| 9 | Delivery Package | Client |
| 10 | Chain of Custody | Legal/Court |
| 11 | Signatures *(PENDING – required before delivery)* | Legal |

## PDF features (reportlab)

- Cover page with case summary table
- HR section dividers
- Results overview table with striped rows
- Chain of custody events list
- Signature block with lines
- Confidentiality header/footer
- A4 format, 2 cm margins, 13+ pages

## Output structure

```
{case_id}_final_report/
├── FINAL_REPORT.json          11-section comprehensive JSON report
├── FINAL_REPORT.pdf           professional PDF (if reportlab installed)
├── README.txt                 client instructions, FAQ, backup guide
├── delivery_checklist.json    pre-delivery verification (7 items)
└── workflow_summary.json      workflow metrics and completeness
```

## Quality ratings

| Score | Rating |
|-------|--------|
| ≥ 95 % | Excellent |
| 85–94 % | Very Good |
| 75–84 % | Good |
| 60–74 % | Fair |
| < 60 % | Poor |

## Delivery checklist items

1. Photo catalog prepared ✓
2. HTML catalog accessible ✓
3. Thumbnails generated ✓
4. Integrity validation completed ✓
5. Metadata extraction performed ✓ / SKIPPED
6. **Peer review by senior analyst — PENDING (REQUIRED)**
7. **Analyst and reviewer signatures — PENDING (REQUIRED)**

## Standards compliance

- ISO/IEC 27037:2012 – Digital evidence handling
- NIST SP 800-86 – Guide to Forensic Techniques
- ACPO Good Practice Guide for Digital Evidence v5
- SWGDE Best Practices for Digital and Multimedia Evidence

## Dependencies

```
ptlibs      >= 1.0.25, < 2   (required)
reportlab   >= 4.0             (optional, for PDF generation)
```

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno – GPLv3.
