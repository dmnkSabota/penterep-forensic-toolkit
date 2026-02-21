[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)

## PTPHOTOCATALOG – Forensic Photo Cataloging

`ptphotocatalog` is a ptlibs-compliant forensic tool that collects all
validated and repaired photographs, generates thumbnails, consolidates EXIF
metadata, builds search indexes, and produces an interactive HTML catalog
ready for client delivery. It is **Step 18** – the final organization step
in the photo-recovery workflow.

## Prerequisites

Step 15 (`ptintegrityvalidation`) must be completed.  
Step 14 (`ptexifanalysis`) is strongly recommended (for EXIF enrichment).  
Step 17 (`ptphotorepair`) output is automatically included if present.

## Installation

```
pip install ptphotocatalog
```

System packages:
```
pip install Pillow --break-system-packages
```

## Usage examples

```
ptphotocatalog PHOTO-2025-001
ptphotocatalog CASE-042 --json
ptphotocatalog TEST-001 --dry-run
```

## Options

```
case-id               Forensic case identifier  (REQUIRED)
-o  --output-dir <d>  Output directory (default: /var/forensics/images)
    --dry-run         Simulate without PIL processing or file copies
-j  --json            Output in JSON format (platform integration)
-q  --quiet           Suppress progress output
-h  --help            Show this help message and exit
    --version         Show version and exit
```

## Six-phase process

| Phase | What happens |
|-------|-------------|
| 1 | Collect from `{case_id}_validation/valid/` and `_repair/repaired/`; rename to `{case_id}_{seq:04d}.ext` |
| 2 | Generate thumbnails: small (150), medium (300), large (600 px) – LANCZOS, q=85, optimize |
| 3 | Consolidate EXIF from `{case_id}_exif_analysis/exif_database.json` – datetime, camera, GPS |
| 4 | Build indexes: chronological, by_camera, GPS (JSON files) |
| 5 | Generate self-contained `photo_catalog.html` – search, filter, sort, lightbox, offline |
| 6 | Save `complete_catalog.json`, `catalog.csv`, `catalog_summary.json`, `README.txt` |

## HTML catalog features

- **Search** by filename, camera, date
- **Filter** by source (validation / repair)
- **Sort** by ID, date, camera, megapixels
- **Lightbox** full-view with caption
- **Badges**: REPAIRED (orange), GPS (green), No EXIF (grey)
- Fully **offline** – no CDN, no external requests
- Responsive grid layout

## Output structure

```
{case_id}_catalog/
├── photos/                    {case_id}_{seq:04d}.jpg  (renamed)
├── thumbnails/
│   ├── small/                 150×150 JPEG
│   ├── medium/                300×300 JPEG
│   └── large/                 600×600 JPEG
├── metadata/
│   ├── complete_catalog.json
│   └── catalog.csv
├── indexes/
│   ├── chronological_index.json
│   ├── by_camera_index.json
│   └── gps_index.json
├── photo_catalog.html         ← open in any browser
├── catalog_summary.json
└── README.txt
```

## Coverage targets

| Metric | Target |
|--------|--------|
| Catalog completeness | 100 % |
| EXIF datetime coverage | > 90 % |
| Thumbnail success rate | > 95 % |
| GPS coverage | 30–50 % (smartphones) |

## Standards compliance

- ISO/IEC 27037:2012 Section 7.7 (Documentation)
- NIST SP 800-86 Section 3.3 (Reporting)
- Dublin Core Metadata Standard

## Dependencies

```
ptlibs  >= 1.0.25, < 2
Pillow  >= 9.0
```

## License

Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno – GPLv3.
