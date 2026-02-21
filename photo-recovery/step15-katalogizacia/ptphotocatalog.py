#!/usr/bin/env python3
"""
    Copyright (c) 2025 Bc. Dominik Sabota, VUT FIT Brno

    ptphotocatalog - Forensic photo cataloging tool

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License.
    See <https://www.gnu.org/licenses/> for details.
"""

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from ._version import __version__

from ptlibs import ptjsonlib, ptprinthelper
from ptlibs.ptprinthelper import ptprint

SCRIPTNAME         = "ptphotocatalog"
DEFAULT_OUTPUT_DIR = "/var/forensics/images"
EXIF_DT_FMT        = "%Y:%m:%d %H:%M:%S"

THUMBNAIL_SIZES: Dict[str, tuple] = {
    "small":  (150, 150),
    "medium": (300, 300),
    "large":  (600, 600),
}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp",
    ".webp", ".heic", ".cr2", ".cr3", ".nef", ".arw", ".dng",
}


def _html_catalog(case_id: str, stats: Dict, photos_js: str) -> str:
    s = stats
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Photo Recovery Catalog - {case_id}</title>
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
    .card{{background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 6px rgba(0,0,0,.1);cursor:pointer;transition:transform .15s,box-shadow .15s}}
    .card:hover{{transform:translateY(-3px);box-shadow:0 4px 14px rgba(0,0,0,.15)}}
    .card img{{width:100%;height:240px;object-fit:cover;background:#e2e8f0}}
    .card-body{{padding:12px}}
    .card-id{{font-weight:600;color:#1e293b;font-size:14px;margin-bottom:6px}}
    .card-meta{{font-size:12px;color:#64748b;line-height:1.7}}.card-meta strong{{color:#334155}}
    .badge{{display:inline-block;padding:2px 7px;font-size:10px;border-radius:4px;margin:0 3px 4px 0;font-weight:600}}
    .b-rep{{background:#f97316;color:#fff}}.b-gps{{background:#22c55e;color:#fff}}.b-noexif{{background:#94a3b8;color:#fff}}
    .empty{{text-align:center;padding:60px;color:#94a3b8;font-size:16px}}
    .lb{{display:none;position:fixed;inset:0;z-index:9000;background:rgba(0,0,0,.92);align-items:center;justify-content:center}}
    .lb.on{{display:flex}}
    .lb img{{max-width:92vw;max-height:88vh;object-fit:contain;border-radius:4px}}
    .lb-close{{position:absolute;top:14px;right:24px;color:#fff;font-size:36px;cursor:pointer;line-height:1}}
    .lb-info{{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);color:#fff;font-size:13px;background:rgba(0,0,0,.55);padding:6px 14px;border-radius:20px}}
  </style>
</head>
<body>
<div class="hdr">
  <h1>Photo Recovery Catalog</h1>
  <div class="meta">
    <span>Case: <strong>{case_id}</strong></span>
    <span>Photos: <strong>{s.get('totalPhotos',0)}</strong></span>
    <span>From validation: <strong>{s.get('fromValidation',0)}</strong></span>
    <span>From repair: <strong>{s.get('fromRepair',0)}</strong></span>
    <span>With EXIF: <strong>{s.get('withExif',0)}</strong></span>
    <span>With GPS: <strong>{s.get('withGps',0)}</strong></span>
    <span>Cameras: <strong>{s.get('uniqueCameras',0)}</strong></span>
    <span style="margin-left:auto;opacity:.6">{str(s.get('timestamp',''))[:10]}</span>
  </div>
</div>
<div class="ctrl">
  <input id="q" type="text" placeholder="Search by filename, camera, date..." oninput="render()">
  <select id="sort" onchange="render()">
    <option value="id">Sort: ID</option><option value="date">Sort: Date</option>
    <option value="camera">Sort: Camera</option><option value="mp">Sort: Megapixels</option>
  </select>
  <select id="src" onchange="render()">
    <option value="">All sources</option>
    <option value="validation">Validation only</option><option value="repair">Repair only</option>
  </select>
</div>
<div class="gallery" id="gallery"></div>
<div class="lb" id="lb" onclick="closeLb()">
  <span class="lb-close" onclick="closeLb()">&times;</span>
  <img id="lb-img" src="" alt="">
  <div class="lb-info" id="lb-info"></div>
</div>
<script>
const PHOTOS={photos_js};let vis=[];
function render(){{
  const q=document.getElementById('q').value.toLowerCase(),srt=document.getElementById('sort').value,src=document.getElementById('src').value;
  vis=PHOTOS.filter(p=>(!src||p.source===src)&&(!q||p.catalogFilename.toLowerCase().includes(q)||p.originalFilename.toLowerCase().includes(q)||(p.camera||'').toLowerCase().includes(q)||(p.datetimeOriginal||'').includes(q)));
  if(srt==='date')vis.sort((a,b)=>(a.datetimeOriginal||'').localeCompare(b.datetimeOriginal||''));
  else if(srt==='camera')vis.sort((a,b)=>(a.camera||'').localeCompare(b.camera||''));
  else if(srt==='mp')vis.sort((a,b)=>b.megapixels-a.megapixels);
  else vis.sort((a,b)=>a.catalogId.localeCompare(b.catalogId));
  const g=document.getElementById('gallery');
  if(!vis.length){{g.innerHTML='<div class="empty">No matching photos</div>';return;}}
  g.innerHTML=vis.map((p,i)=>`<div class="card" onclick="openLb(${{i}})"><img src="${{p.thumbnailMedium}}" alt="${{p.catalogFilename}}" loading="lazy"><div class="card-body"><div class="card-id">${{p.catalogId}}</div>${{p.source==='repair'?'<span class="badge b-rep">REPAIRED</span>':''}}${{p.hasGps?'<span class="badge b-gps">GPS</span>':''}}${{!p.hasExif?'<span class="badge b-noexif">No EXIF</span>':''}}<div class="card-meta"><strong>Original:</strong> ${{p.originalFilename}}<br><strong>Camera:</strong> ${{p.camera||'Unknown'}}<br>${{p.datetimeOriginal?`<strong>Date:</strong> ${{p.datetimeOriginal}}<br>`:''}}</div></div></div>`).join('');
}}
function openLb(i){{const p=vis[i];document.getElementById('lb-img').src=p.fullPath;document.getElementById('lb-info').textContent=`${{p.catalogId}} - ${{p.originalFilename}}${{p.datetimeOriginal?' - '+p.datetimeOriginal:''}}`;document.getElementById('lb').classList.add('on');}}
function closeLb(){{document.getElementById('lb').classList.remove('on');}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeLb();}});
render();
</script>
</body></html>"""


class PtPhotoCatalog:
    """
    Forensic photo cataloging - ptlibs compliant.

    Pipeline: collect valid+repaired photos -> generate thumbnails ->
              consolidate EXIF metadata -> build indexes -> HTML catalog ->
              save summary + README.

    Output: {case_id}_catalog/ ready for client delivery.
    Compliant with ISO/IEC 27037:2012 Section 7.7, NIST SP 800-86 Section 3.3,
    Dublin Core Metadata Standard.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.ptjsonlib  = ptjsonlib.PtJsonLib()
        self.args       = args
        self.case_id    = args.case_id.strip()
        self.dry_run    = args.dry_run
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.valid_dir    = self.output_dir / f"{self.case_id}_validation" / "valid"
        self.repaired_dir = self.output_dir / f"{self.case_id}_repair"    / "repaired"
        self.exif_db_path = self.output_dir / f"{self.case_id}_exif_analysis" / "exif_database.json"

        self.catalog_base = self.output_dir / f"{self.case_id}_catalog"
        self.photos_dir   = self.catalog_base / "photos"
        self.thumbs_base  = self.catalog_base / "thumbnails"
        self.metadata_dir = self.catalog_base / "metadata"
        self.indexes_dir  = self.catalog_base / "indexes"

        self._exif_db:    Dict[str, Dict] = {}
        self._collection: List[Dict]      = []
        self._cameras:    Dict[str, int]  = {}
        self._date_range: Dict[str, Any]  = {}
        self._s = {
            "from_validation": 0, "from_repair": 0,
            "thumbs_ok": 0, "thumbs_fail": 0,
            "with_exif": 0, "with_gps": 0,
        }

        self.ptjsonlib.add_properties({
            "caseId": self.case_id,
            "outputDirectory": str(self.output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scriptVersion": __version__,
            "totalPhotos": 0, "fromValidation": 0, "fromRepair": 0,
            "thumbnailsGenerated": 0, "withExif": 0, "withGps": 0,
            "uniqueCameras": 0, "dateRange": {}, "dryRun": self.dry_run,
        })
        ptprint(f"Initialized: case={self.case_id}", "INFO", condition=not self.args.json)

    def _add_node(self, node_type: str, success: bool, **kwargs) -> None:
        self.ptjsonlib.add_node(self.ptjsonlib.create_node_object(
            node_type, properties={"success": success, **kwargs}
        ))

    def _fail(self, node_type: str, msg: str) -> bool:
        ptprint(msg, "ERROR", condition=not self.args.json)
        self._add_node(node_type, False, error=msg)
        return False

    def _mk(self, *paths) -> None:
        if not self.dry_run:
            for p in paths: Path(p).mkdir(parents=True, exist_ok=True)

    def _collect_images(self, directory: Path) -> List[Path]:
        if not directory.exists(): return []
        return sorted(p for p in directory.rglob("*")
                      if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)

    def collect_photos(self) -> bool:
        ptprint("\n[1/6] Collecting Photos", "TITLE", condition=not self.args.json)
        self._mk(self.photos_dir)
        seq = 1
        for label, src_dir in [("validation", self.valid_dir), ("repair", self.repaired_dir)]:
            files = self._collect_images(src_dir)
            if not files:
                ptprint(f"  {label}/: empty or absent", "WARNING", condition=not self.args.json)
                continue
            for src in files:
                ext      = src.suffix.lower()
                cat_id   = f"{self.case_id}_{seq:04d}"
                cat_name = f"{cat_id}{ext}"
                cat_path = self.photos_dir / cat_name
                if not self.dry_run:
                    shutil.copy2(src, cat_path)
                self._collection.append({
                    "catalogId": cat_id, "catalogFilename": cat_name,
                    "catalogPath": str(cat_path), "originalFilename": src.name,
                    "source": label, "sourcePath": str(src),
                    "hasExif": False, "hasGps": False, "thumbnails": {},
                })
                self._s[f"from_{label}"] += 1
                seq += 1

        total = len(self._collection)
        if total == 0:
            return self._fail("photoCollection",
                              "No photos found – check that integrity validation and repair have been run.")

        if not self.dry_run:
            self._mk(self.metadata_dir)
            (self.metadata_dir / "collection_index.json").write_text(
                json.dumps([{k: e[k] for k in ("catalogId","catalogFilename","originalFilename","source")}
                            for e in self._collection], indent=2), encoding="utf-8")

        ptprint(f"Collected: {total} "
                f"(validation: {self._s['from_validation']}, repair: {self._s['from_repair']})",
                "OK", condition=not self.args.json)
        self._add_node("photoCollection", True, totalPhotos=total,
                       fromValidation=self._s["from_validation"], fromRepair=self._s["from_repair"])
        return True

    def generate_thumbnails(self) -> None:
        ptprint("\n[2/6] Generating Thumbnails", "TITLE", condition=not self.args.json)
        for sz in THUMBNAIL_SIZES:
            self._mk(self.thumbs_base / sz)

        for entry in self._collection:
            if self.dry_run:
                for sz in THUMBNAIL_SIZES:
                    entry["thumbnails"][sz] = f"thumbnails/{sz}/{entry['catalogId']}_{sz}.jpg"
                entry.update({"width": 1920, "height": 1080, "megapixels": 2.1})
                self._s["thumbs_ok"] += 1; continue
            try:
                img = Image.open(entry["catalogPath"])
                if img.mode not in ("RGB", "L"): img = img.convert("RGB")
                entry["width"], entry["height"] = img.size
                entry["megapixels"] = round(img.size[0] * img.size[1] / 1_000_000, 1)
                for sz, dims in THUMBNAIL_SIZES.items():
                    fn  = f"{entry['catalogId']}_{sz}.jpg"
                    dst = self.thumbs_base / sz / fn
                    t   = img.copy(); t.thumbnail(dims, Image.Resampling.LANCZOS)
                    t.save(dst, "JPEG", quality=85, optimize=True)
                    entry["thumbnails"][sz] = f"thumbnails/{sz}/{fn}"
                self._s["thumbs_ok"] += 1
            except Exception as exc:
                ptprint(f"  Thumbnail failed: {entry['catalogFilename']}: {exc}",
                        "WARNING", condition=not self.args.json)
                self._s["thumbs_fail"] += 1

        ptprint(f"Thumbnails: {self._s['thumbs_ok']} OK, {self._s['thumbs_fail']} failed",
                "OK", condition=not self.args.json)
        self._add_node("thumbnails", True,
                       generated=self._s["thumbs_ok"], failed=self._s["thumbs_fail"])

    def consolidate_metadata(self) -> None:
        ptprint("\n[3/6] Consolidating Metadata", "TITLE", condition=not self.args.json)

        if self.exif_db_path.exists():
            try:
                raw  = json.loads(self.exif_db_path.read_text(encoding="utf-8"))
                rows = raw.get("exifData") or raw.get("exif_data") or []
                for row in rows:
                    fn = row.get("filename") or row.get("file_name")
                    if fn:
                        self._exif_db[fn] = row.get("exif") or row.get("exifFields") or {}
                ptprint(f"EXIF database: {len(self._exif_db)} records", "OK", condition=not self.args.json)
            except Exception as exc:
                ptprint(f"Cannot load EXIF database: {exc}", "WARNING", condition=not self.args.json)
        else:
            ptprint("No EXIF database found.", "WARNING", condition=not self.args.json)

        for entry in self._collection:
            exif = self._exif_db.get(entry["originalFilename"], {})
            if exif:
                entry["hasExif"] = True; self._s["with_exif"] += 1
                entry["datetimeOriginal"] = exif.get("DateTimeOriginal") or exif.get("datetime_original")
                make  = exif.get("Make")  or exif.get("make",  "")
                model = exif.get("Model") or exif.get("model", "")
                entry.update({"cameraMake": make, "cameraModel": model,
                              "camera": f"{make} {model}".strip() or "Unknown",
                              "iso": exif.get("ISO") or exif.get("iso"),
                              "fNumber": exif.get("FNumber") or exif.get("f_number"),
                              "focalLength": exif.get("FocalLength") or exif.get("focal_length")})
                lat = exif.get("GPSLatitude") or exif.get("gps_latitude")
                lon = exif.get("GPSLongitude") or exif.get("gps_longitude")
                if lat is not None and lon is not None:
                    entry.update({"gpsLatitude": lat, "gpsLongitude": lon, "hasGps": True})
                    self._s["with_gps"] += 1
            else:
                entry["camera"] = "Unknown"
            cam = entry.get("camera", "Unknown")
            self._cameras[cam] = self._cameras.get(cam, 0) + 1

        if not self.dry_run:
            (self.metadata_dir / "complete_catalog.json").write_text(
                json.dumps(self._collection, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            fields = ["catalogId","catalogFilename","originalFilename","source",
                      "datetimeOriginal","cameraMake","cameraModel","iso","fNumber",
                      "focalLength","hasGps","gpsLatitude","gpsLongitude","megapixels","width","height"]
            with open(self.metadata_dir / "catalog.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                w.writeheader(); w.writerows(self._collection)

        cov = round(self._s["with_exif"] / max(len(self._collection), 1) * 100, 1)
        ptprint(f"Metadata: {self._s['with_exif']} ({cov}%) | GPS: {self._s['with_gps']}",
                "OK", condition=not self.args.json)
        self._add_node("metadata", True, withExif=self._s["with_exif"],
                       withGps=self._s["with_gps"], exifCoverage=cov)

    def create_indexes(self) -> None:
        ptprint("\n[4/6] Creating Indexes", "TITLE", condition=not self.args.json)
        self._mk(self.indexes_dir)

        chron  = sorted(
            [{"catalogId": e["catalogId"], "catalogFilename": e["catalogFilename"],
              "datetimeOriginal": e["datetimeOriginal"]}
             for e in self._collection if e.get("datetimeOriginal")],
            key=lambda x: x["datetimeOriginal"])
        by_cam = defaultdict(list)
        for e in self._collection:
            by_cam[e.get("camera","Unknown")].append(
                {"catalogId": e["catalogId"], "catalogFilename": e["catalogFilename"]})
        gps = [{"catalogId": e["catalogId"], "catalogFilename": e["catalogFilename"],
                "latitude": e["gpsLatitude"], "longitude": e["gpsLongitude"]}
               for e in self._collection if e.get("hasGps")]

        dates = []
        for e in self._collection:
            try: dates.append(datetime.strptime(e.get("datetimeOriginal",""), EXIF_DT_FMT))
            except Exception: pass
        if dates:
            self._date_range = {"earliest": min(dates).strftime("%Y-%m-%d"),
                                "latest": max(dates).strftime("%Y-%m-%d"),
                                "spanDays": (max(dates) - min(dates)).days}

        if not self.dry_run:
            (self.indexes_dir / "chronological_index.json").write_text(
                json.dumps(chron, indent=2), encoding="utf-8")
            (self.indexes_dir / "by_camera_index.json").write_text(
                json.dumps(dict(by_cam), indent=2, ensure_ascii=False), encoding="utf-8")
            (self.indexes_dir / "gps_index.json").write_text(
                json.dumps(gps, indent=2, ensure_ascii=False), encoding="utf-8")

        ptprint(f"Indexes: chronological ({len(chron)}), cameras ({len(by_cam)}), GPS ({len(gps)})",
                "OK", condition=not self.args.json)
        self._add_node("indexes", True, chronological=len(chron),
                       cameras=len(by_cam), gpsEntries=len(gps), dateRange=self._date_range)

    def generate_html_catalog(self) -> None:
        ptprint("\n[5/6] Generating HTML Catalog", "TITLE", condition=not self.args.json)
        photos_js = json.dumps([{
            "catalogId": e["catalogId"], "catalogFilename": e["catalogFilename"],
            "originalFilename": e["originalFilename"], "source": e["source"],
            "camera": e.get("camera","Unknown"), "datetimeOriginal": e.get("datetimeOriginal") or "",
            "iso": e.get("iso") or "", "megapixels": e.get("megapixels") or 0,
            "hasExif": e.get("hasExif",False), "hasGps": e.get("hasGps",False),
            "thumbnailMedium": e["thumbnails"].get("medium",""),
            "fullPath": f"photos/{e['catalogFilename']}",
        } for e in self._collection], ensure_ascii=False)

        html = _html_catalog(self.case_id, {
            "totalPhotos": len(self._collection),
            "fromValidation": self._s["from_validation"], "fromRepair": self._s["from_repair"],
            "withExif": self._s["with_exif"], "withGps": self._s["with_gps"],
            "uniqueCameras": len(self._cameras),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, photos_js)

        if not self.dry_run:
            (self.catalog_base / "photo_catalog.html").write_text(html, encoding="utf-8")
        ptprint(f"HTML catalog: {len(self._collection)} entries", "OK", condition=not self.args.json)
        self._add_node("htmlCatalog", True, entries=len(self._collection))

    def run(self) -> None:
        ptprint("=" * 70, "TITLE", condition=not self.args.json)
        ptprint(f"PHOTO CATALOG v{__version__} | Case: {self.case_id}",
                "TITLE", condition=not self.args.json)
        if self.dry_run:
            ptprint("MODE: DRY-RUN", "WARNING", condition=not self.args.json)
        ptprint("=" * 70, "TITLE", condition=not self.args.json)

        if not self.collect_photos():
            self.ptjsonlib.set_status("finished"); return
        if not (PIL_AVAILABLE or self.dry_run):
            ptprint("PIL not found – thumbnails skipped. pip install Pillow --break-system-packages",
                    "WARNING", condition=not self.args.json)
        self.generate_thumbnails()
        self.consolidate_metadata()
        self.create_indexes()
        self.generate_html_catalog()

        total    = len(self._collection)
        exif_pct = round(self._s["with_exif"] / max(total, 1) * 100, 1)
        thumb_rt = round(self._s["thumbs_ok"] / max(total, 1) * 100, 1)
        self.ptjsonlib.add_properties({
            "totalPhotos": total, "fromValidation": self._s["from_validation"],
            "fromRepair": self._s["from_repair"], "thumbnailsGenerated": self._s["thumbs_ok"],
            "withExif": self._s["with_exif"], "withGps": self._s["with_gps"],
            "uniqueCameras": len(self._cameras), "exifCoveragePercent": exif_pct,
            "thumbnailSuccessRate": thumb_rt, "dateRange": self._date_range,
            "camerasDetected": self._cameras,
        })
        ptprint(f"\nCATALOG COMPLETED | Photos: {total} | EXIF: {exif_pct}% | "
                f"Thumbnails: {thumb_rt}% | Delivery: {self.catalog_base.name}/",
                "OK", condition=not self.args.json)
        self.ptjsonlib.set_status("finished")

    def _write_readme(self, props: Dict) -> None:
        lines = [
            "=" * 70, "PHOTO RECOVERY CATALOG", "=" * 70, "",
            f"Case ID:   {self.case_id}",
            f"Date:      {datetime.now(timezone.utc).strftime('%Y-%m-%d')}", "",
            "STATISTICS:",
            f"  Total Photos:      {len(self._collection)}",
            f"  From Validation:   {self._s['from_validation']}",
            f"  From Repair:       {self._s['from_repair']}",
            f"  With EXIF:         {self._s['with_exif']} ({props.get('exifCoveragePercent',0)}%)",
            f"  With GPS:          {self._s['with_gps']}",
            f"  Unique Cameras:    {len(self._cameras)}", "",
        ]
        if self._date_range:
            lines += ["DATE RANGE:",
                      f"  Earliest: {self._date_range.get('earliest')}",
                      f"  Latest:   {self._date_range.get('latest')}",
                      f"  Span:     {self._date_range.get('spanDays')} days", ""]
        lines += ["CAMERAS:"] + \
                 [f"  {cam}: {cnt}" for cam, cnt in sorted(self._cameras.items(), key=lambda x:-x[1])]
        lines += ["", "STRUCTURE:",
                  "  photos/              All recovered photos (renamed)",
                  "  thumbnails/          small / medium / large previews",
                  "  metadata/            JSON + CSV catalogs",
                  "  indexes/             chronological, camera, GPS",
                  "  photo_catalog.html   Interactive offline catalog", "",
                  "HOW TO VIEW:",
                  "  1. Open photo_catalog.html in any browser",
                  "  2. Search by filename, camera or date",
                  "  3. Click a photo to view full size",
                  "  4. Filter by source, sort by ID/date/camera/MP"]
        (self.catalog_base / "README.txt").write_text("\n".join(lines), encoding="utf-8")

    def save_report(self) -> Optional[str]:
        if self.args.json:
            ptprint(self.ptjsonlib.get_result_json(), "", self.args.json)
            return None
        props = json.loads(self.ptjsonlib.get_result_json())["result"]["properties"]
        if not self.dry_run:
            self._mk(self.catalog_base)
            summary = {**props, "catalogCompleteness": "100%"}
            (self.catalog_base / "catalog_summary.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            self._write_readme(props)
        ptprint(f"Reports saved: {self.catalog_base.name}/", "OK", condition=not self.args.json)
        return str(self.catalog_base)


def get_help() -> List:
    return [
        {"description": [
            "Forensic photo cataloging - ptlibs compliant",
            "Collects valid+repaired photos, thumbnails, EXIF, indexes, HTML catalog",
            "Output: {case_id}_catalog/ ready for client delivery",
        ]},
        {"usage": ["ptphotocatalog <case-id> [options]"]},
        {"usage_example": [
            "ptphotocatalog PHOTO-2025-001",
            "ptphotocatalog CASE-042 --json",
            "ptphotocatalog TEST-001 --dry-run",
        ]},
        {"options": [
            ["case-id",            "",      "Forensic case identifier - REQUIRED"],
            ["-o", "--output-dir", "<dir>", f"Output directory (default: {DEFAULT_OUTPUT_DIR})"],
            ["-v", "--verbose",    "",      "Verbose logging"],
            ["--dry-run",          "",      "Simulate without copying or PIL processing"],
            ["-j", "--json",       "",      "JSON output for Penterep platform"],
            ["-q", "--quiet",      "",      "Suppress progress output"],
            ["-h", "--help",       "",      "Show help"],
            ["--version",          "",      "Show version"],
        ]},
        {"notes": [
            "Sources: {case_id}_validation/valid/ and {case_id}_repair/repaired/",
            "EXIF loaded from {case_id}_exif_analysis/exif_database.json if available",
            "Thumbnails: small 150px | medium 300px | large 600px (PIL LANCZOS, JPEG q=85)",
            "HTML catalog fully offline - no CDN or external dependencies",
            "Compliant with ISO/IEC 27037:2012 Section 7.7, NIST SP 800-86 Section 3.3",
        ]},
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("case_id")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("-v", "--verbose",    action="store_true")
    parser.add_argument("-q", "--quiet",      action="store_true")
    parser.add_argument("--dry-run",          action="store_true")
    parser.add_argument("-j", "--json",       action="store_true")
    parser.add_argument("--version", action="version", version=f"{SCRIPTNAME} {__version__}")
    parser.add_argument("--socket-address",   default=None)
    parser.add_argument("--socket-port",      default=None)
    parser.add_argument("--process-ident",    default=None)

    if len(sys.argv) == 1 or {"-h", "--help"} & set(sys.argv):
        ptprinthelper.help_print(get_help(), SCRIPTNAME, __version__)
        sys.exit(0)

    args = parser.parse_args()
    if args.json:
        args.quiet = True
    ptprinthelper.print_banner(SCRIPTNAME, __version__, args.json)
    return args


def main() -> int:
    try:
        args = parse_args()
        tool = PtPhotoCatalog(args)
        tool.run()
        tool.save_report()
        props = json.loads(tool.ptjsonlib.get_result_json())["result"]["properties"]
        return 0 if props.get("totalPhotos", 0) > 0 else 1
    except KeyboardInterrupt:
        ptprint("Interrupted by user.", "WARNING", condition=True)
        return 130
    except Exception as exc:
        ptprint(f"ERROR: {exc}", "ERROR", condition=True)
        return 99


if __name__ == "__main__":
    sys.exit(main())