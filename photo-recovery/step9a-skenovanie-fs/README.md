[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTFILESYSTEMRECOVERY – Forensic Filesystem-Based Photo Recovery

`ptfilesystemrecovery` is a ptlibs-compliant forensic tool that recovers image
files from a forensic disk image using The Sleuth Kit (`fls` + `icat`).
It is **Step 12A** in the photo-recovery forensic workflow.

## Prerequisites

**Step 10 (ptfilesystemanalysis) must be completed first** – this tool loads
the partition layout and image path from `{case_id}_filesystem_analysis.json`.

## Installation

```
pip install ptfilesystemrecovery
```

External tools (Linux):
```
sudo apt-get install sleuthkit imagemagick libimage-exiftool-perl
```

## Usage examples

```
ptfilesystemrecovery PHOTO-2025-001
ptfilesystemrecovery PHOTO-2025-001 --json
ptfilesystemrecovery PHOTO-2025-001 --dry-run
ptfilesystemrecovery PHOTO-2025-001 --force   # override carving recommendation
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate without executing external commands
    --force           Run even if Step 10 recommended file_carving
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show this help message and exit
    --version         Show version and exit
```

## Recovery phases

| Phase | What happens |
|-------|-------------|
| 1 | Load Step 10 filesystem analysis JSON |
| 2 | Check tools: fls, icat, file, identify, exiftool |
| 3 | Create output directory structure |
| 4 | Scan filesystem with `fls -r -d -p` |
| 5 | Extract with `icat`, validate, extract EXIF metadata |
| 6 | Save JSON report + text summary |

## Output structure

```
{case_id}_recovered/
├── active/       original dir tree preserved (DCIM/100CANON/IMG_0001.JPG …)
├── deleted/      deleted-but-recoverable files
├── corrupted/    partially damaged files (may be repairable)
├── metadata/     per-file JSON metadata catalogs
└── RECOVERY_REPORT.txt
{case_id}_recovery_report.json
```

## Supported image formats

JPEG/JPG, PNG, TIFF, BMP, GIF, HEIC/HEIF, WebP,
RAW (CR2, CR3, NEF, NRW, ARW, DNG, ORF, RAF, RW2, PEF, RAW)

## Standards compliance

- ISO/IEC 27037:2012 – Section 7.3 (Data Extraction)
- NIST SP 800-86 – Section 3.1.2.2 (File System Recovery)
- Chain of Custody: JSON audit trail for every extracted file

## Dependencies

```
ptlibs >= 1.0.25, < 2
```
External: `sleuthkit`, `imagemagick`, `libimage-exiftool-perl`

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

ptfilesystemrecovery is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your option)
any later version.

See https://www.gnu.org/licenses/ for details.
