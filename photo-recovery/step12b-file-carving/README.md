[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTFILECARVING – Forensic File Carving Photo Recovery

`ptfilecarving` is a ptlibs-compliant forensic tool that recovers image files
from a forensic disk image using **PhotoRec** byte-signature search.
It is **Step 12B** in the photo-recovery forensic workflow and works
**without a functional filesystem** – ideal for damaged, formatted or
unrecognised media.

## Prerequisites

**Step 10 (ptfilesystemanalysis) must be completed first** – this tool loads
the image path from `{case_id}_filesystem_analysis.json`.

## Installation

```
pip install ptfilecarving
```

External tools (Linux):
```
sudo apt-get install testdisk imagemagick libimage-exiftool-perl
```

## Usage examples

```
ptfilecarving PHOTO-2025-001
ptfilecarving PHOTO-2025-001 --json
ptfilecarving PHOTO-2025-001 --dry-run
ptfilecarving PHOTO-2025-001 --force   # override filesystem_scan recommendation
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate without executing external commands
    --force           Run even if Step 10 recommended filesystem_scan
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show this help message and exit
    --version         Show version and exit
```

## Recovery phases

| Phase | What happens |
|-------|-------------|
| 1 | Load Step 10 filesystem analysis JSON |
| 2 | Check tools: photorec, file, identify, exiftool |
| 3 | Create output directory structure |
| 4 | Run PhotoRec + collect files from recup_dir.* |
| 5 | Validate (file + ImageMagick) + SHA-256 deduplication |
| 6 | Extract EXIF, organise by type, rename, save reports |

## Output structure

```
{case_id}_carved/
├── organized/
│   ├── jpg/          PHOTO-2025-001_jpg_000001.jpg …
│   ├── png/
│   ├── tiff/
│   ├── raw/          CR2, NEF, ARW, DNG …
│   └── other/        HEIC, WebP, GIF, BMP
├── corrupted/        Partially damaged files
├── quarantine/       Invalid / false positives
├── duplicates/       SHA-256 duplicates
├── metadata/         Per-file EXIF JSON catalogs
└── CARVING_REPORT.txt
{case_id}_carving_report.json
```

## Key limitations vs Step 12A

| Property | 12A (filesystem) | 12B (carving) |
|----------|-----------------|---------------|
| Original filenames | ✅ Preserved | ❌ Lost |
| Directory structure | ✅ Preserved | ❌ Lost |
| FS timestamps | ✅ Preserved | ❌ Lost |
| EXIF data | ✅ Preserved | ✅ Preserved |
| Works without FS | ❌ No | ✅ Yes |
| Speed | Fast (30 min–2 hr) | Slow (2–8 hr) |
| Typical success rate | >95% | 50–65% |

## Standards compliance

- NIST SP 800-86 – Section 3.1.2.3 (Data Carving)
- ISO/IEC 27037:2012 – Section 7.3 (Data Extraction)
- Chain of Custody: SHA-256 hash database in JSON report

## Dependencies

```
ptlibs >= 1.0.25, < 2
```
External: `testdisk` (photorec), `imagemagick`, `libimage-exiftool-perl`

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

ptfilecarving is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option)
any later version.

See https://www.gnu.org/licenses/ for details.
