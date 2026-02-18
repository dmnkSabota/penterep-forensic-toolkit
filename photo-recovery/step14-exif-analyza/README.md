[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTEXIFANALYSIS – Forensic EXIF Metadata Analysis

`ptexifanalysis` is a ptlibs-compliant forensic tool that extracts and analyses
EXIF metadata from all consolidated recovered photos.
It is **Step 14** in the photo-recovery forensic workflow and reads directly
from the master catalog produced by Step 13.

## Prerequisites

Step 13 (`ptrecoveryconsolidation`) must be completed first – this tool reads
`{case_id}_consolidated/master_catalog.json`.

## Installation

```
pip install ptexifanalysis
```

External tool:
```
sudo apt-get install libimage-exiftool-perl
```

## Usage examples

```
ptexifanalysis PHOTO-2025-001
ptexifanalysis CASE-042 --json
ptexifanalysis TEST-001 --dry-run
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate without running exiftool
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show this help message and exit
    --version         Show version and exit
```

## Analysis phases

| Phase | What happens |
|-------|-------------|
| 1 | Load master_catalog.json from Step 13 |
| 2 | Verify ExifTool installation + version |
| 3 | Batch-extract EXIF with `exiftool -j -G -a -s -n` |
| 4 | Analyse time / cameras / settings / GPS |
| 5 | Detect edited photos (Software tag) and anomalies; compute quality score |
| 6 | Save exif_database.json, exif_data.csv, EXIF_REPORT.txt |

## Output

```
{case_id}_exif_analysis/
├── exif_database.json   per-file EXIF + timeline + GPS + anomalies
├── exif_data.csv        spreadsheet-ready export
└── EXIF_REPORT.txt      human-readable summary
```

## Quality score

| Score | Threshold | Interpretation |
|-------|-----------|----------------|
| EXCELLENT | ≥ 90 % DateTimeOriginal | Full timeline possible |
| GOOD | 70–90 % | Partial timeline |
| FAIR | 50–70 % | Limited analysis |
| POOR | < 50 % | Heavy metadata loss |

## Edit / anomaly detection

- **Editing software** – Photoshop, Lightroom, GIMP, Affinity, Instagram, Snapseed, VSCO …
- **Future dates** – DateTimeOriginal after current date
- **Unusual ISO** – values > 25 600
- **ModifyDate > DateTimeOriginal** – post-capture modification indicator

## Standards compliance

- EXIF 2.32 / CIPA DC-008-2019
- ISO 12234-2:2001 (Electronic still-picture imaging)

## Dependencies

```
ptlibs >= 1.0.25, < 2
```
External: `libimage-exiftool-perl`

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno – GPLv3.
See https://www.gnu.org/licenses/ for details.
