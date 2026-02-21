[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTRECOVERYCONSOLIDATION – Forensic Recovery Consolidation

`ptrecoveryconsolidation` is a ptlibs-compliant forensic tool that merges the
outputs from **Step 12A** (filesystem-based recovery) and/or **Step 12B**
(file carving) into a single deduplicated dataset with a master catalog.
It is **Step 13** in the photo-recovery forensic workflow.

## Prerequisites

At least one of the following must be present:
- `{case_id}_recovered/` (Step 12A output)
- `{case_id}_carved/`    (Step 12B output)

## Installation

```
pip install ptrecoveryconsolidation
```

No additional system packages required (pure Python + ptlibs).

## Usage examples

```
ptrecoveryconsolidation PHOTO-2025-001
ptrecoveryconsolidation CASE-042 --json
ptrecoveryconsolidation TEST-001 --dry-run
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate without copying files
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show this help message and exit
    --version         Show version and exit
```

## Consolidation phases

| Phase | What happens |
|-------|-------------|
| 1 | Detect available sources (12A / 12B / both) |
| 2 | Inventory all image files from all sources |
| 3 | SHA-256 hash + cross-source deduplication (FS-based wins) |
| 4 | Prepare consolidated directory structure |
| 5 | Copy unique files, move duplicates to audit folder |
| 6 | Build master_catalog.json and save reports |

## Output structure

```
{case_id}_consolidated/
├── fs_based/
│   ├── jpg/    original filenames (IMG_0001.JPG …)
│   ├── png/
│   ├── tiff/
│   ├── raw/
│   └── other/
├── carved/
│   ├── jpg/    systematic names (CASE_jpg_000001.jpg …)
│   ├── png/ …
├── duplicates/             SHA-256 audit copies
├── master_catalog.json     complete file inventory
└── CONSOLIDATION_REPORT.txt
{case_id}_consolidation_report.json
```

## Deduplication logic

When both Step 12A and 12B are present, the same photo may appear in both
outputs. Priority rule: **FS-based copy is always kept** (preserves original
filename, directory structure, timestamps). Carved copies of the same file
are moved to `duplicates/`. Typical overlap: 15–25 % in hybrid scenarios.

## Master catalog

Every unique file gets a catalog entry:

```json
{
  "id": 1,
  "filename": "IMG_0001.JPG",
  "hashSha256": "a1b2c3…",
  "sizeBytes": 2458624,
  "format": "jpg",
  "formatGroup": "jpg",
  "recoveryMethod": "fs_based",
  "path": "fs_based/jpg/IMG_0001.JPG"
}
```

## Standards compliance

- ISO/IEC 27037:2012 – Section 7.3 (Data consolidation)
- NIST SP 800-86 – Section 3.1.3 (Analysis)
- Chain of Custody: SHA-256 of every file in master catalog

## Dependencies

```
ptlibs >= 1.0.25, < 2
```

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno – GPLv3.
See https://www.gnu.org/licenses/ for details.
