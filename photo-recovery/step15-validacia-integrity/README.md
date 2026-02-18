[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTINTEGRITYVALIDATION – Forensic Photo Integrity Validation

`ptintegrityvalidation` is a ptlibs-compliant forensic tool that validates
the physical integrity of all consolidated recovered photos using a
**multi-tool pipeline** and classifies them as valid, corrupted (repairable),
or unrecoverable. It is **Step 15** in the photo-recovery forensic workflow.

## Prerequisites

Step 13 (`ptrecoveryconsolidation`) must be completed first.  
PIL/Pillow must be installed (see below).

## Installation

```
pip install ptintegrityvalidation
```

System packages:
```
pip install Pillow --break-system-packages           # required
sudo apt-get install imagemagick jpeginfo pngcheck   # optional but recommended
```

## Usage examples

```
ptintegrityvalidation PHOTO-2025-001
ptintegrityvalidation CASE-042 --json
ptintegrityvalidation TEST-001 --dry-run
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate without reading files or copying
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show this help message and exit
    --version         Show version and exit
```

## Validation pipeline

| Phase | What happens |
|-------|-------------|
| 1 | Load master_catalog.json from Step 13 |
| 2 | Check tools (PIL required; identify, file, jpeginfo, pngcheck optional) |
| 3 | Prepare valid / corrupted / unrecoverable directories |
| 4 | Per-file: size → magic bytes → `file` → ImageMagick → PIL → format-specific |
| 5 | Copy files into categorised output directories (copy2, never move) |
| 6 | Save JSON report + VALIDATION_REPORT.txt |

## Decision logic

| Tools result | Magic bytes | Classification |
|-------------|-------------|----------------|
| ALL pass | ✓ | **valid** |
| ≥1 pass | any | **corrupted** (repairability assessed) |
| ALL fail | any | **unrecoverable** |

## Corruption taxonomy

| Level | Type | Repairable | Technique |
|-------|------|-----------|-----------|
| 1 | truncated | ✅ Yes | Add missing footer bytes |
| 2 | invalid_header | ✅ Yes | Fix/rebuild header |
| 2 | corrupt_segments | ✅ Yes | Remove/skip bad segments |
| 3 | corrupt_data | ⚠ Partial | Partial pixel recovery |
| 4 | fragmented | ❌ No | Manual defragmentation |
| 5 | false_positive | ❌ No | Discard |

## Output structure

```
{case_id}_validation/
├── valid/              fully functional photos → ready for delivery
├── corrupted/          repairable → pass to Step 17 (Photo Repair)
├── unrecoverable/      false positives → document and discard
└── VALIDATION_REPORT.txt
{case_id}_validation_report.json
```

## Expected integrity scores

| Source | Expected valid |
|--------|---------------|
| FS-based (12A) | > 95 % |
| File carving (12B) | 70–85 % |
| Active files | ~ 99 % |
| Deleted files | ~ 78 % |

## Standards compliance

- ISO/IEC 10918-1 (JPEG)
- PNG ISO/IEC 15948:2004
- NIST SP 800-86 Section 3.1.3 (Data Validation)

## Dependencies

```
ptlibs  >= 1.0.25, < 2
Pillow  >= 9.0
```
Optional system: `imagemagick`, `jpeginfo`, `pngcheck`

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno – GPLv3.
See https://www.gnu.org/licenses/ for details.
