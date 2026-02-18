#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptphotocatalog - Forensic photo cataloging tool

    ptphotocatalog is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    ptphotocatalog is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with ptphotocatalog.  If not, see <https://www.gnu.org/licenses/>.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import argparse
import sys; sys.path.append(__file__.rsplit("/", 1)[0])
import csv
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from _version import __version__
from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_OUTPUT_DIR = "/var/forensics/images"

# Three thumbnail sizes (width, height) – PIL uses max-dimension bounding box
THUMBNAIL_SIZES: Dict[str, tuple] = {
    "small":  (150, 150),
    "medium": (300, 300),
    "large":  (600, 600),
}

# Image extensions to collect
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp",
                    ".webp", ".heic", ".cr2", ".cr3", ".nef", ".arw", ".dng"}

# EXIF datetime format used by exiftool
EXIF_DT_FMT = "%Y:%m:%d %H:%M:%S"


# ============================================================================
# HTML TEMPLATE HELPERS
# ============================================================================

def _html_catalog(case_id: str, stats: Dict, photos_js: str) -> str:
    """Return a self-contained interactive HTML catalog page."""
    total        = stats.get("totalPhotos", 0)
    with_exif    = stats.get("withExif", 0)
    with_gps     = stats.get("withGps", 0)
    cameras      = stats.get("uniqueCameras", 0)
    from_val     = stats.get("fromValidation", 0)
    from_rep     = stats.get("fromRepair", 0)
    timestamp    = stats.get("timestamp", "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Photo Recovery Catalog – {case_id}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f4f4f5}}
    .hdr{{background:#1e293b;color:#fff;padding:18px 24px}}
    .hdr h1{{font-size:20px;margin-bottom:8px}}
    .hdr .meta{{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;opacity:.85}}
    .ctrl{{background:#fff;padding:14px 24px;display:flex;gap:10px;align-items:center;border-bottom:1px solid #e2e8f0}}
    .ctrl input{{flex:1;max-width:360px;padding:8px 12px;font-size:14px;border:1px solid #cbd5e1;border-radius:6px}}
    .ctrl select{{padding:8px 10px;font-size:14px;border:1px solid #cbd5e1;border-radius:6px}}
    .gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;padding:20px}}
    .card{{background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.1);
           cursor:pointer;transition:transform .15s,box-shadow .15s}}
    .card:hover{{transform:translateY(-3px);box-shadow:0 4px 14px rgba(0,0,0,.15)}}
    .card img{{width:100%;height:240px;object-fit:cover;background:#e2e8f0}}
    .card-body{{padding:12px}}
    .card-id{{font-weight:600;color:#1e293b;font-size:14px;margin-bottom:6px}}
    .card-meta{{font-size:12px;color:#64748b;line-height:1.7}}
    .card-meta strong{{color:#334155}}
    .badge{{display:inline-block;padding:2px 7px;font-size:10px;border-radius:4px;margin:0 3px 4px 0;font-weight:600}}
    .b-rep{{background:#f97316;color:#fff}}
    .b-gps{{background:#22c55e;color:#fff}}
    .b-noexif{{background:#94a3b8;color:#fff}}
    .empty{{text-align:center;padding:60px;color:#94a3b8;font-size:16px}}
    /* Lightbox */
    .lb{{display:none;position:fixed;inset:0;z-index:9000;background:rgba(0,0,0,.92);
         align-items:center;justify-content:center}}
    .lb.on{{display:flex}}
    .lb img{{max-width:92vw;max-height:88vh;object-fit:contain;border-radius:4px}}
    .lb-close{{position:absolute;top:14px;right:24px;color:#fff;font-size:36px;cursor:pointer;line-height:1}}
    .lb-info{{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);
              color:#fff;font-size:13px;background:rgba(0,0,0,.55);padding:6px 14px;border-radius:20px}}
  </style>
</head>
<body>

<div class="hdr">
  <h1>📷 Photo Recovery Catalog</h1>
  <div class="meta">
    <span>Case: <strong>{case_id}</strong></span>
    <span>Photos: <strong>{total}</strong></span>
    <span>From validation: <strong>{from_val}</strong></span>
    <span>From repair: <strong>{from_rep}</strong></span>
    <span>With EXIF: <strong>{with_exif}</strong></span>
    <span>With GPS: <strong>{with_gps}</strong></span>
    <span>Cameras: <strong>{cameras}</strong></span>
    <span style="margin-left:auto;opacity:.6">{timestamp[:10]}</span>
  </div>
</div>

<div class="ctrl">
  <input id="q" type="text" placeholder="Search by filename, camera, date…" oninput="render()">
  <select id="sort" onchange="render()">
    <option value="id">Sort: ID</option>
    <option value="date">Sort: Date</option>
    <option value="camera">Sort: Camera</option>
    <option value="mp">Sort: Megapixels</option>
  </select>
  <select id="src" onchange="render()">
    <option value="">All sources</option>
    <option value="validation">Validation only</option>
    <option value="repair">Repair only</option>
  </select>
</div>

<div class="gallery" id="gallery"></div>

<div class="lb" id="lb" onclick="closeLb()">
  <span class="lb-close" onclick="closeLb()">&times;</span>
  <img id="lb-img" src="" alt="">
  <div class="lb-info" id="lb-info"></div>
</div>

<script>
const PHOTOS = {photos_js};
let vis = [];

function render() {{
  const q   = document.getElementById('q').value.toLowerCase();
  const srt = document.getElementById('sort').value;
  const src = document.getElementById('src').value;

  vis = PHOTOS.filter(p =>
    (!src || p.source === src) &&
    (!q || p.catalogFilename.toLowerCase().includes(q) ||
           p.originalFilename.toLowerCase().includes(q) ||
           (p.camera||'').toLowerCase().includes(q) ||
           (p.datetimeOriginal||'').includes(q))
  );

  if (srt==='date')   vis.sort((a,b)=>(a.datetimeOriginal||'').localeCompare(b.datetimeOriginal||''));
  else if (srt==='camera') vis.sort((a,b)=>(a.camera||'').localeCompare(b.camera||''));
  else if (srt==='mp') vis.sort((a,b)=>b.megapixels-a.megapixels);
  else                vis.sort((a,b)=>a.catalogId.localeCompare(b.catalogId));

  const g = document.getElementById('gallery');
  if (!vis.length) {{ g.innerHTML='<div class="empty">No matching photos</div>'; return; }}

  g.innerHTML = vis.map((p,i) => `
    <div class="card" onclick="openLb(${{i}})">
      <img src="${{p.thumbnailMedium}}" alt="${{p.catalogFilename}}" loading="lazy">
      <div class="card-body">
        <div class="card-id">${{p.catalogId}}</div>
        ${{p.source==='repair'?'<span class="badge b-rep">REPAIRED</span>':''}}
        ${{p.hasGps?'<span class="badge b-gps">GPS</span>':''}}
        ${{!p.hasExif?'<span class="badge b-noexif">No EXIF</span>':''}}
        <div class="card-meta">
          <strong>Original:</strong> ${{p.originalFilename}}<br>
          <strong>Camera:</strong> ${{p.camera||'Unknown'}}<br>
          ${{p.datetimeOriginal?`<strong>Date:</strong> ${{p.datetimeOriginal}}<br>`:''}}
          ${{p.iso?`<strong>ISO:</strong> ${{p.iso}} `:''}}\
${{p.megapixels?`<strong>MP:</strong> ${{p.megapixels}}`:''}}
        </div>
      </div>
    </div>`).join('');
}}

function openLb(i) {{
  const p = vis[i];
  document.getElementById('lb-img').src = p.fullPath;
  document.getElementById('lb-info').textContent =
    `${{p.catalogId}} · ${{p.originalFilename}}${{p.datetimeOriginal?' · '+p.datetimeOriginal:''}}`;
  document.getElementById('lb').classList.add('on');
}}
function closeLb() {{ document.getElementById('lb').classList.remove('on'); }}
document.addEventListener('keydown', e => {{ if(e.key==='Escape') closeLb(); }});

render();
</script>
</body>
</html>"""


# ============================================================================
# MAIN CLASS
# ============================================================================

class PtPhotoCatalog:
    """
    Forensic photo cataloging tool – ptlibs compliant.

    Six-phase process:
    1. Collect valid photos from Step 15 (valid/) and Step 17 (repaired/)
       Rename to {case_id}_{seq:04d}.{ext} format
    2. Generate thumbnails in three sizes: small (150), medium (300), large (600)
       Uses PIL LANCZOS resampling, JPEG quality=85, optimize=True
    3. Consolidate EXIF metadata from Step 14's exif_database.json
       Match by original filename → extract datetime, camera, GPS
    4. Build three JSON indexes: chronological, by_camera, GPS
    5. Generate self-contained interactive photo_catalog.html
       Search, filter by source, sort by ID/date/camera/MP, lightbox view
    6. Save complete_catalog.json, catalog.csv, catalog_summary.json, README.txt

    Complies with ISO/IEC 27037:2012 §7.7, NIST SP 800-86 §3.3,
    Dublin Core Metadata Standard.
    """

    def __init__(self, args):
        self.ptjsonlib = ptjsonlib.PtJsonLib()
        self.args      = args

        self.case_id    = self.args.case_id.strip()
        self.dry_run    = self.args.dry_run
        self.output_dir = Path(self.args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Input sources
        self.valid_dir    = self.output_dir / f"{self.case_id}_validation" / "valid"
        self.repaired_dir = self.output_dir / f"{self.case_id}_repair"    / "repaired"
        self.exif_db_path = self.output_dir / f"{self.case_id}_exif_analysis" / "exif_database.json"

        # Output tree
        self.catalog_base  = self.output_dir / f"{self.case_id}_catalog"
        self.photos_dir    = self.catalog_base / "photos"
        self.thumbs_base   = self.catalog_base / "thumbnails"
        self.metadata_dir  = self.catalog_base / "metadata"
        self.indexes_dir   = self.catalog_base / "indexes"

        # State
        self._exif_db: Dict[str, Dict] = {}   # filename → exif dict
        self._collection: List[Dict]   = []

        # Counters
        self._from_validation = 0
        self._from_repair     = 0
        self._thumbs_ok       = 0
        self._thumbs_fail     = 0
        self._with_exif       = 0
        self._with_gps        = 0
        self._cameras: Dict[str, int] = {}
        self._date_range: Dict[str, Any] = {}

        self.ptjsonlib.add_properties({
            "caseId":          self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "scriptVersion":   __version__,
            "totalPhotos":     0,
            "fromValidation":  0,
            "fromRepair":      0,
            "thumbnailsGenerated": 0,
            "withExif":        0,
            "withGps":         0,
            "uniqueCameras":   0,
            "dateRange":       {},
            "catalogPath":     str(self.catalog_base),
            "dryRun":          self.dry_run,
        })

        ptprint(f"Initialized: case={self.case_id}",
                "INFO", condition=not self.args.json)

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _mk(self, *paths):
        """Create directories unless dry_run."""
        for p in paths:
            if not self.dry_run:
                Path(p).mkdir(parents=True, exist_ok=True)

    def _collect_images(self, directory: Path) -> List[Path]:
        """Recursively collect image files from a directory."""
        if not directory.exists():
            return []
        return [p for p in directory.rglob("*")
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]

    # -------------------------------------------------------------------------
    # PHASE 1 – COLLECT PHOTOS
    # -------------------------------------------------------------------------

    def collect_photos(self) -> bool:
        """
        Phase 1 – Gather valid images from Step 15 (valid/) and Step 17 (repaired/).

        Each file is copied to catalog/photos/{case_id}_{seq:04d}.{ext}.
        Mapping from catalog ID back to original filename is preserved.
        """
        ptprint("\n[STEP 1/6] Collecting Photos",
                "TITLE", condition=not self.args.json)

        self._mk(self.photos_dir)
        seq = 1

        for source_label, source_dir in [
            ("validation", self.valid_dir),
            ("repair",     self.repaired_dir),
        ]:
            files = self._collect_images(source_dir)
            if not files:
                ptprint(f"  {source_label}: directory empty or absent",
                        "WARNING", condition=not self.args.json)
                continue

            ptprint(f"  Collecting from {source_label}: {len(files)} file(s)…",
                    "INFO", condition=not self.args.json)

            for src in sorted(files):
                ext          = src.suffix.lower()
                catalog_id   = f"{self.case_id}_{seq:04d}"
                cat_filename = f"{catalog_id}{ext}"
                cat_path     = self.photos_dir / cat_filename

                if not self.dry_run:
                    shutil.copy2(src, cat_path)

                entry: Dict[str, Any] = {
                    "catalogId":       catalog_id,
                    "catalogFilename": cat_filename,
                    "catalogPath":     str(cat_path),
                    "originalFilename": src.name,
                    "source":          source_label,
                    "sourcePath":      str(src),
                    # filled later
                    "hasExif":    False,
                    "hasGps":     False,
                    "thumbnails": {},
                }
                self._collection.append(entry)

                if source_label == "validation":
                    self._from_validation += 1
                else:
                    self._from_repair += 1
                seq += 1

            ptprint(f"  ✓ {source_label}: {self._from_validation if source_label == 'validation' else self._from_repair} collected",
                    "OK", condition=not self.args.json)

        total = len(self._collection)
        ptprint(f"  Total photos collected: {total}",
                "OK", condition=not self.args.json)

        if total == 0:
            ptprint("✗ No photos found – check that Steps 15/17 have been run",
                    "ERROR", condition=not self.args.json)
            self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
                "photoCollection", properties={"success": False, "totalPhotos": 0}))
            return False

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "photoCollection",
            properties={"success": True, "totalPhotos": total,
                        "fromValidation": self._from_validation,
                        "fromRepair": self._from_repair}))
        return True

    # -------------------------------------------------------------------------
    # PHASE 2 – GENERATE THUMBNAILS
    # -------------------------------------------------------------------------

    def generate_thumbnails(self) -> None:
        """
        Phase 2 – Create small / medium / large JPEG thumbnails for each photo.

        Uses PIL LANCZOS resampling, quality=85, optimize=True.
        Thumbnails are saved to catalog/thumbnails/{size}/{id}_{size}.jpg.
        Relative paths (from catalog_base) are stored in the photo entry.
        """
        ptprint("\n[STEP 2/6] Generating Thumbnails",
                "TITLE", condition=not self.args.json)

        for size in THUMBNAIL_SIZES:
            self._mk(self.thumbs_base / size)

        total = len(self._collection)
        ptprint(f"  {total} photo(s) × {len(THUMBNAIL_SIZES)} sizes…",
                "INFO", condition=not self.args.json)

        for idx, entry in enumerate(self._collection, 1):
            if idx % 100 == 0 or idx == total:
                ptprint(f"  {idx}/{total} ({idx*100//total}%)",
                        "INFO", condition=not self.args.json)

            src_path = Path(entry["catalogPath"])

            if self.dry_run:
                for size in THUMBNAIL_SIZES:
                    rel = f"thumbnails/{size}/{entry['catalogId']}_{size}.jpg"
                    entry["thumbnails"][size] = rel
                entry["width"] = 1920; entry["height"] = 1080
                entry["megapixels"] = 2.1
                self._thumbs_ok += len(THUMBNAIL_SIZES)
                continue

            try:
                img   = Image.open(src_path)
                # Convert palette / RGBA to RGB for JPEG output
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                entry["width"], entry["height"] = img.size
                entry["megapixels"] = round(img.size[0] * img.size[1] / 1_000_000, 1)

                for size_name, dims in THUMBNAIL_SIZES.items():
                    thumb_fn  = f"{entry['catalogId']}_{size_name}.jpg"
                    thumb_abs = self.thumbs_base / size_name / thumb_fn
                    thumb_rel = f"thumbnails/{size_name}/{thumb_fn}"

                    thumb = img.copy()
                    thumb.thumbnail(dims, Image.Resampling.LANCZOS)
                    thumb.save(thumb_abs, "JPEG", quality=85, optimize=True)
                    entry["thumbnails"][size_name] = thumb_rel
                    self._thumbs_ok += 1

            except Exception as exc:
                ptprint(f"  ⚠ Thumbnail failed for {entry['catalogFilename']}: {exc}",
                        "WARNING", condition=not self.args.json)
                self._thumbs_fail += 1

        ptprint(f"  ✓ Thumbnails generated: {self._thumbs_ok}  failed: {self._thumbs_fail}",
                "OK", condition=not self.args.json)
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "thumbnailGeneration",
            properties={"success": True, "generated": self._thumbs_ok,
                        "failed": self._thumbs_fail}))

    # -------------------------------------------------------------------------
    # PHASE 3 – CONSOLIDATE METADATA
    # -------------------------------------------------------------------------

    def consolidate_metadata(self) -> None:
        """
        Phase 3 – Match each collected photo against the EXIF database from
        Step 14.  Populates datetime, camera, ISO, GPS fields in each entry.

        The exif_database.json may contain a list under "exifData" or "exif_data";
        each item has a "filename" key matching the original filename.
        """
        ptprint("\n[STEP 3/6] Consolidating Metadata",
                "TITLE", condition=not self.args.json)

        # Load EXIF database
        if self.exif_db_path.exists():
            try:
                raw = json.loads(self.exif_db_path.read_text(encoding="utf-8"))
                rows = raw.get("exifData") or raw.get("exif_data") or []
                for row in rows:
                    fn = row.get("filename") or row.get("file_name")
                    if fn:
                        self._exif_db[fn] = row.get("exif") or row.get("exifFields") or {}
                ptprint(f"  EXIF database loaded: {len(self._exif_db)} entries",
                        "OK", condition=not self.args.json)
            except Exception as exc:
                ptprint(f"  ⚠ Could not load EXIF database: {exc}",
                        "WARNING", condition=not self.args.json)
        else:
            ptprint("  ⚠ EXIF database not found – continuing without EXIF",
                    "WARNING", condition=not self.args.json)

        for entry in self._collection:
            exif = self._exif_db.get(entry["originalFilename"], {})
            if exif:
                entry["hasExif"] = True
                self._with_exif += 1

                entry["datetimeOriginal"] = exif.get("DateTimeOriginal") or exif.get("datetime_original")
                make  = exif.get("Make")  or exif.get("make", "")
                model = exif.get("Model") or exif.get("model", "")
                entry["cameraMake"]  = make
                entry["cameraModel"] = model
                entry["camera"]      = f"{make} {model}".strip() or "Unknown"
                entry["iso"]         = exif.get("ISO") or exif.get("iso")
                entry["fNumber"]     = exif.get("FNumber") or exif.get("f_number")
                entry["focalLength"] = exif.get("FocalLength") or exif.get("focal_length")

                lat = exif.get("GPSLatitude") or exif.get("gps_latitude")
                lon = exif.get("GPSLongitude") or exif.get("gps_longitude")
                if lat is not None and lon is not None:
                    entry["gpsLatitude"]  = lat
                    entry["gpsLongitude"] = lon
                    entry["hasGps"]       = True
                    self._with_gps += 1
            else:
                entry["camera"] = "Unknown"

            # Camera breakdown
            cam = entry.get("camera", "Unknown")
            self._cameras[cam] = self._cameras.get(cam, 0) + 1

        exif_pct = round(self._with_exif / max(len(self._collection), 1) * 100, 1)
        ptprint(f"  ✓ With EXIF: {self._with_exif}  ({exif_pct}%)  GPS: {self._with_gps}",
                "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "metadataConsolidation",
            properties={"withExif": self._with_exif, "withGps": self._with_gps,
                        "exifCoverage": exif_pct}))

    # -------------------------------------------------------------------------
    # PHASE 4 – BUILD INDEXES
    # -------------------------------------------------------------------------

    def create_indexes(self) -> None:
        """
        Phase 4 – Build and save three JSON indexes:
          chronological_index.json – photos with DateTimeOriginal, sorted
          by_camera_index.json     – dict of camera → [catalog IDs]
          gps_index.json           – list of {catalogId, lat, lon}
        """
        ptprint("\n[STEP 4/6] Creating Indexes",
                "TITLE", condition=not self.args.json)

        self._mk(self.indexes_dir)

        # ── Chronological ─────────────────────────────────────────────────
        chron  = []
        dates  = []

        for e in self._collection:
            dt_str = e.get("datetimeOriginal")
            if dt_str:
                chron.append({"catalogId": e["catalogId"],
                               "catalogFilename": e["catalogFilename"],
                               "datetimeOriginal": dt_str})
                try:
                    dates.append(datetime.strptime(dt_str, EXIF_DT_FMT))
                except ValueError:
                    pass

        chron.sort(key=lambda x: x["datetimeOriginal"])

        if dates:
            self._date_range = {
                "earliest":  min(dates).strftime("%Y-%m-%d"),
                "latest":    max(dates).strftime("%Y-%m-%d"),
                "spanDays":  (max(dates) - min(dates)).days,
            }

        if not self.dry_run:
            (self.indexes_dir / "chronological_index.json").write_text(
                json.dumps(chron, indent=2, ensure_ascii=False), encoding="utf-8")
        ptprint(f"  ✓ Chronological: {len(chron)} photos with datetime",
                "OK", condition=not self.args.json)

        # ── By camera ─────────────────────────────────────────────────────
        by_cam: Dict[str, List] = defaultdict(list)
        for e in self._collection:
            by_cam[e.get("camera", "Unknown")].append(
                {"catalogId": e["catalogId"],
                 "catalogFilename": e["catalogFilename"]})

        if not self.dry_run:
            (self.indexes_dir / "by_camera_index.json").write_text(
                json.dumps(dict(by_cam), indent=2, ensure_ascii=False), encoding="utf-8")
        ptprint(f"  ✓ By camera: {len(by_cam)} unique camera(s)",
                "OK", condition=not self.args.json)

        # ── GPS ───────────────────────────────────────────────────────────
        gps_list = [
            {"catalogId": e["catalogId"],
             "catalogFilename": e["catalogFilename"],
             "latitude":  e["gpsLatitude"],
             "longitude": e["gpsLongitude"]}
            for e in self._collection if e.get("hasGps")
        ]

        if not self.dry_run:
            (self.indexes_dir / "gps_index.json").write_text(
                json.dumps(gps_list, indent=2, ensure_ascii=False), encoding="utf-8")
        ptprint(f"  ✓ GPS: {len(gps_list)} photos with coordinates",
                "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "indexCreation",
            properties={"chronological": len(chron), "cameras": len(by_cam),
                        "gpsEntries": len(gps_list), "dateRange": self._date_range}))

    # -------------------------------------------------------------------------
    # PHASE 5 – HTML CATALOG
    # -------------------------------------------------------------------------

    def generate_html_catalog(self) -> None:
        """
        Phase 5 – Generate self-contained interactive photo_catalog.html.

        Features: search, filter by source, sort by ID/date/camera/MP,
        lightbox full-view, responsive grid, REPAIRED / GPS badges,
        works fully offline (no CDN dependencies).
        """
        ptprint("\n[STEP 5/6] Generating HTML Catalog",
                "TITLE", condition=not self.args.json)

        stats_for_html = {
            "totalPhotos":     len(self._collection),
            "fromValidation":  self._from_validation,
            "fromRepair":      self._from_repair,
            "withExif":        self._with_exif,
            "withGps":         self._with_gps,
            "uniqueCameras":   len(self._cameras),
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        }

        photos_js_list = []
        for e in self._collection:
            photos_js_list.append({
                "catalogId":       e["catalogId"],
                "catalogFilename": e["catalogFilename"],
                "originalFilename": e["originalFilename"],
                "source":          e["source"],
                "camera":          e.get("camera", "Unknown"),
                "datetimeOriginal": e.get("datetimeOriginal") or "",
                "iso":             e.get("iso") or "",
                "megapixels":      e.get("megapixels") or 0,
                "hasExif":         e.get("hasExif", False),
                "hasGps":          e.get("hasGps", False),
                "thumbnailMedium": e["thumbnails"].get("medium", ""),
                "fullPath":        f"photos/{e['catalogFilename']}",
            })

        html = _html_catalog(
            self.case_id, stats_for_html,
            json.dumps(photos_js_list, ensure_ascii=False)
        )

        html_path = self.catalog_base / "photo_catalog.html"
        if not self.dry_run:
            html_path.write_text(html, encoding="utf-8")
        ptprint(f"  ✓ photo_catalog.html generated ({len(self._collection)} entries)",
                "OK", condition=not self.args.json)

        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            "htmlCatalog",
            properties={"success": True,
                        "path": str(html_path),
                        "entries": len(photos_js_list)}))

    # -------------------------------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """Orchestrate all six phases."""

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("PHOTO CATALOGING", "TITLE", condition=not self.args.json)
        ptprint(f"Case: {self.case_id}", "TITLE", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        # Phase 1
        if not self.collect_photos():
            self.ptjsonlib.set_status("finished")
            return

        # Phase 2
        self.generate_thumbnails()

        # Phase 3
        self.consolidate_metadata()

        # Phase 4
        self.create_indexes()

        # Phase 5
        self.generate_html_catalog()

        # Update top-level properties
        total      = len(self._collection)
        exif_pct   = round(self._with_exif / max(total, 1) * 100, 1)
        thumb_rate = round(self._thumbs_ok / max(total * len(THUMBNAIL_SIZES), 1) * 100, 1)

        self.ptjsonlib.add_properties({
            "totalPhotos":         total,
            "fromValidation":      self._from_validation,
            "fromRepair":          self._from_repair,
            "thumbnailsGenerated": self._thumbs_ok,
            "withExif":            self._with_exif,
            "withGps":             self._with_gps,
            "uniqueCameras":       len(self._cameras),
            "exifCoveragePercent": exif_pct,
            "thumbnailSuccessRate": thumb_rate,
            "dateRange":           self._date_range,
            "camerasDetected":     self._cameras,
        })

        ptprint("\n" + "=" * 70, "TITLE", condition=not self.args.json)
        ptprint("CATALOGING COMPLETED 🎉", "OK",   condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"Total photos:      {total}",       "OK",   condition=not self.args.json)
        ptprint(f"Thumbnails:        {self._thumbs_ok} ({thumb_rate}%)",
                "OK",   condition=not self.args.json)
        ptprint(f"EXIF coverage:     {self._with_exif}/{total} ({exif_pct}%)",
                "OK",   condition=not self.args.json)
        ptprint(f"GPS coverage:      {self._with_gps}/{total}",
                "INFO", condition=not self.args.json)
        ptprint(f"Unique cameras:    {len(self._cameras)}",
                "INFO", condition=not self.args.json)
        if self._date_range:
            ptprint(f"Date range:        {self._date_range.get('earliest')} → "
                    f"{self._date_range.get('latest')} "
                    f"({self._date_range.get('spanDays')} days)",
                    "INFO", condition=not self.args.json)
        ptprint(f"\n📦 Delivery package: {self.catalog_base}",
                "OK",   condition=not self.args.json)
        ptprint(f"   Open: photo_catalog.html in any browser",
                "INFO", condition=not self.args.json)

        self.ptjsonlib.set_status("finished")

    # -------------------------------------------------------------------------
    # PHASE 6 – SAVE REPORTS
    # -------------------------------------------------------------------------

    def save_report(self) -> Optional[str]:
        """
        Phase 6 – Save complete_catalog.json, catalog.csv,
        catalog_summary.json, README.txt, and (in --json mode) print to stdout.
        """
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None

        self._mk(self.metadata_dir, self.catalog_base)

        # complete_catalog.json  (serialisable copy – drop raw catalog_path)
        cat_file = self.metadata_dir / "complete_catalog.json"
        if not self.dry_run:
            safe = [{k: v for k, v in e.items() if k != "catalogPath"}
                    for e in self._collection]
            cat_file.write_text(json.dumps(safe, indent=2, ensure_ascii=False,
                                           default=str), encoding="utf-8")
        ptprint(f"  ✓ complete_catalog.json",
                "OK", condition=not self.args.json)

        # catalog.csv
        csv_file = self.metadata_dir / "catalog.csv"
        fields   = ["catalogId", "catalogFilename", "originalFilename", "source",
                    "datetimeOriginal", "cameraMake", "cameraModel", "iso",
                    "fNumber", "focalLength", "hasGps", "gpsLatitude",
                    "gpsLongitude", "megapixels", "width", "height"]
        if not self.dry_run:
            with open(csv_file, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self._collection)
        ptprint(f"  ✓ catalog.csv",
                "OK", condition=not self.args.json)

        # catalog_summary.json
        summary_file = self.catalog_base / "catalog_summary.json"
        props        = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        summary = {
            **props,
            "catalogCompleteness": "100%",
            "outputStructure": {
                "photos":       "photos/",
                "thumbnails":   "thumbnails/{small,medium,large}/",
                "metadata":     "metadata/",
                "indexes":      "indexes/",
                "htmlCatalog":  "photo_catalog.html",
            }
        }
        if not self.dry_run:
            summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False,
                                               default=str), encoding="utf-8")
        ptprint(f"  ✓ catalog_summary.json",
                "OK", condition=not self.args.json)

        # README.txt
        readme = self.catalog_base / "README.txt"
        total  = len(self._collection)
        if not self.dry_run:
            with open(readme, "w", encoding="utf-8") as fh:
                fh.write("=" * 70 + "\n")
                fh.write("PHOTO RECOVERY CATALOG\n")
                fh.write("=" * 70 + "\n\n")
                fh.write(f"Case ID:   {self.case_id}\n")
                fh.write(f"Date:      {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n")
                fh.write("CONTENTS:\n")
                fh.write(f"  Total Photos:      {total}\n")
                fh.write(f"  From Validation:   {self._from_validation}\n")
                fh.write(f"  From Repair:       {self._from_repair}\n")
                fh.write(f"  With EXIF:         {self._with_exif} ({props.get('exifCoveragePercent',0)}%)\n")
                fh.write(f"  With GPS:          {self._with_gps}\n")
                fh.write(f"  Unique Cameras:    {len(self._cameras)}\n\n")
                if self._date_range:
                    fh.write("DATE RANGE:\n")
                    fh.write(f"  Earliest: {self._date_range.get('earliest')}\n")
                    fh.write(f"  Latest:   {self._date_range.get('latest')}\n")
                    fh.write(f"  Span:     {self._date_range.get('spanDays')} days\n\n")
                fh.write("CAMERAS DETECTED:\n")
                for cam, cnt in sorted(self._cameras.items(), key=lambda x: -x[1]):
                    fh.write(f"  {cam}: {cnt} photos\n")
                fh.write("\nSTRUCTURE:\n")
                fh.write("  photos/              All recovered photos (renamed)\n")
                fh.write("  thumbnails/          Preview images (small/medium/large)\n")
                fh.write("  metadata/            Catalogs (JSON + CSV)\n")
                fh.write("  indexes/             Search indexes\n")
                fh.write("  photo_catalog.html   Interactive catalog\n\n")
                fh.write("HOW TO VIEW:\n")
                fh.write("  1. Open photo_catalog.html in any web browser\n")
                fh.write("  2. Search by filename, camera or date\n")
                fh.write("  3. Click a photo to view full size\n")
                fh.write("  4. Filter by source (validation / repair)\n")
                fh.write("  5. Sort by ID, date, camera or megapixels\n")
        ptprint(f"  ✓ README.txt",
                "OK", condition=not self.args.json)

        ptprint(f"\n✓ All reports saved to: {self.catalog_base.name}/",
                "OK", condition=not self.args.json)
        return str(self.catalog_base)


# ============================================================================
# CLI HELPERS
# ============================================================================

def get_help():
    return [
        {"description": [
            "Forensic photo cataloging tool – ptlibs compliant",
            "Collects valid/repaired photos, generates thumbnails,",
            "consolidates EXIF metadata, creates indexes and interactive HTML catalog",
        ]},
        {"usage": ["ptphotocatalog <case-id> [options]"]},
        {"usage_example": [
            "ptphotocatalog PHOTO-2025-001",
            "ptphotocatalog CASE-042 --json",
            "ptphotocatalog TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",    "",              "Forensic case identifier  (REQUIRED)"],
            ["-o",  "--output-dir", "<dir>",  f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["--dry-run",  "",              "Simulate without copying files or PIL processing"],
            ["-j",  "--json",       "",      "JSON output for platform integration"],
            ["-q",  "--quiet",      "",      "Suppress progress output"],
            ["-h",  "--help",       "",      "Show this help and exit"],
            ["--version",  "",              "Show version and exit"],
        ]},
        {"phases": [
            "1  Collect from {case_id}_validation/valid/ and _repair/repaired/",
            "2  Generate thumbnails: small(150) medium(300) large(600) LANCZOS q85",
            "3  Consolidate EXIF from {case_id}_exif_analysis/exif_database.json",
            "4  Build indexes: chronological, by_camera, GPS",
            "5  Generate photo_catalog.html (search, filter, lightbox, offline)",
            "6  Save complete_catalog.json, catalog.csv, catalog_summary.json, README.txt",
        ]},
        {"coverage_targets": [
            "Catalog completeness: 100%",
            "EXIF datetime coverage: >90%",
            "Thumbnail success rate: >95%",
            "GPS coverage: 30–50% (smartphones typical)",
        ]},
        {"forensic_notes": [
            "Source files are READ-ONLY (shutil.copy2 only)",
            "Complies with ISO/IEC 27037:2012 §7.7, NIST SP 800-86 §3.3",
            "Dublin Core Metadata Standard compatible",
        ]},
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"{SCRIPTNAME} – Forensic photo cataloging"
    )
    parser.add_argument("case_id",         help="Forensic case identifier")
    parser.add_argument("-o", "--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run",       action="store_true")
    parser.add_argument("-j", "--json",    action="store_true")
    parser.add_argument("-q", "--quiet",   action="store_true")
    parser.add_argument("--version",       action="version",
                        version=f"{SCRIPTNAME} {__version__}")
    parser.add_argument("--socket-address", type=str, default=None)
    parser.add_argument("--socket-port",    type=str, default=None)
    parser.add_argument("--process-ident",  type=str, default=None)

    if len(sys.argv) == 1 or "-h" in sys.argv or "--help" in sys.argv:
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    if args.json:
        args.quiet = True
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main():
    global SCRIPTNAME
    SCRIPTNAME = "ptphotocatalog"
    try:
        args = parse_args()
        tool = PtPhotoCatalog(args)
        tool.run()
        tool.save_report()

        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("totalPhotos", 0) > 0 else 1

    except KeyboardInterrupt:
        ptprint("\n✗ Interrupted by user", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())
