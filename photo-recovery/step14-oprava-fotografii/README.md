[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTPHOTOREPAIR – Forensic Photo Repair

`ptphotorepair` is a ptlibs-compliant forensic tool that attempts to repair
corrupted JPEG photographs using four automated techniques.
It is **Step 17** in the photo-recovery workflow (optional – only executed
when Step 16 decides `perform_repair`).

## Prerequisites

Step 15 (`ptintegrityvalidation`) must be completed first.  
PIL/Pillow must be installed (see below).

## Installation

```
pip install ptphotorepair
```

System packages:
```
pip install Pillow --break-system-packages           # required
sudo apt-get install imagemagick jpeginfo            # optional
```

## Usage examples

```
ptphotorepair PHOTO-2025-001
ptphotorepair CASE-042 --json
ptphotorepair TEST-001 --dry-run
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate all repairs with synthetic data
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show this help message and exit
    --version         Show version and exit
```

## Repair pipeline

| Phase | What happens |
|-------|-------------|
| 1 | Load files_needing_repair list from Step 15 validation report |
| 2 | Check tools (PIL required; ImageMagick, jpeginfo optional) |
| 3 | Prepare repaired / failed / logs directories |
| 4 | Route each file to correct repair technique; attempt repair |
| 5 | Multi-tool validation: PIL verify+load, ImageMagick, jpeginfo |
| 6 | Save repair_report.json + REPAIR_REPORT.txt |

## Four repair techniques

| Corruption type | Technique | Expected success |
|----------------|-----------|-----------------|
| missing_footer | Append FF D9 EOI marker | 85–95 % |
| invalid_header | Remove leading garbage / reconstruct SOI+JFIF | 90–95 % |
| corrupt_segments | Strip APP segments; preserve SOF/DQT/DHT + SOS..EOI | 80–85 % |
| truncated / corrupt_data | PIL LOAD_TRUNCATED_IMAGES → save partial JPEG | 50–70 % |

## Forensic integrity note

Repair only **reconstructs existing data** (fills missing markers, removes
corrupt segments) – it never fabricates or interpolates pixel data.  
Source files in `{case_id}_validation/corrupted/` are **READ-ONLY**; all
repair work is done on `shutil.copy2` working copies.

## Output structure

```
{case_id}_repair/
├── repaired/      successfully repaired → ready for Step 18
├── failed/        repair failed → document and exclude
└── logs/
{case_id}_repair_report.json
```

## Standards compliance

- ISO/IEC 10918-1 (JPEG / ITU-T T.81)
- JFIF Specification v1.02
- NIST SP 800-86 Section 3.1.4 (Data Recovery and Repair)

## Dependencies

```
ptlibs  >= 1.0.25, < 2
Pillow  >= 9.0
```
Optional system: `imagemagick`, `jpeginfo`

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno – GPLv3.
