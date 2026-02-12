#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOR-COL-CATALOG: Katalogizácia obnovených fotografií
Autor: Bc. Dominik Sabota
VUT FIT Brno, 2025

Tento skript vytvára finálny katalóg všetkých validných fotografií
s thumbnailami, metadátami a interaktívnym HTML rozhraním.
"""

import json
import sys
import os
import shutil
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: PIL/Pillow not found")

try:
    from ptlibs import ptprinthelper
    PTLIBS_AVAILABLE = True
except ImportError:
    PTLIBS_AVAILABLE = False


class PhotoCataloger:
    """
    Katalogizácia obnovených fotografií.
    
    Proces:
    1. Collect valid photos from Steps 15 and 17
    2. Generate thumbnails (3 sizes)
    3. Consolidate metadata
    4. Create indexes (chronological, by camera, GPS)
    5. Generate interactive HTML catalog
    6. Create final summary report
    """
    
    # Thumbnail sizes
    THUMBNAIL_SIZES = {
        'small': (150, 150),
        'medium': (300, 300),
        'large': (600, 600)
    }
    
    def __init__(self, case_id, output_dir="/mnt/user-data/outputs"):
        self.case_id = case_id
        self.output_dir = Path(output_dir)
        
        # Input directories
        self.validation_base = self.output_dir / f"{case_id}_validation"
        self.valid_dir = self.validation_base / "valid"
        
        self.repair_base = self.output_dir / f"{case_id}_repair"
        self.repaired_dir = self.repair_base / "repaired"
        
        # EXIF analysis
        self.exif_base = self.output_dir / f"{case_id}_exif_analysis"
        self.exif_db_path = self.exif_base / "exif_database.json"
        
        # Output catalog structure
        self.catalog_base = self.output_dir / f"{case_id}_catalog"
        self.photos_dir = self.catalog_base / "photos"
        self.thumbnails_base = self.catalog_base / "thumbnails"
        self.metadata_dir = self.catalog_base / "metadata"
        self.indexes_dir = self.catalog_base / "indexes"
        
        # Data
        self.exif_data = None
        self.photo_collection = []
        self.catalog_index = {}
        
        # Statistics
        self.stats = {
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_photos": 0,
            "from_validation": 0,
            "from_repair": 0,
            "thumbnails_generated": 0,
            "with_exif": 0,
            "with_gps": 0,
            "unique_cameras": 0,
            "date_range": {"earliest": None, "latest": None},
            "success": False
        }
    
    def _print(self, message, level="INFO"):
        """Helper pre výpis"""
        if PTLIBS_AVAILABLE:
            ptprinthelper.ptprint(message, level)
        else:
            prefix = {
                "TITLE": "[*]",
                "OK": "[✓]",
                "ERROR": "[✗]",
                "WARNING": "[!]",
                "INFO": "[i]"
            }.get(level, "")
            print(f"{prefix} {message}")
    
    def check_tools(self):
        """Kontrola dostupnosti nástrojov"""
        self._print("\nChecking cataloging tools...", "INFO")
        
        if not PIL_AVAILABLE:
            self._print("PIL/Pillow: NOT FOUND", "ERROR")
            self._print("Install: pip install Pillow --break-system-packages", "ERROR")
            return False
        
        self._print("PIL/Pillow: Found", "OK")
        return True
    
    def prepare_directories(self):
        """Vytvorenie výstupných adresárov"""
        directories = [
            self.photos_dir,
            self.metadata_dir,
            self.indexes_dir
        ]
        
        # Thumbnail directories
        for size in self.THUMBNAIL_SIZES:
            directories.append(self.thumbnails_base / size)
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        
        return True
    
    def load_exif_database(self):
        """Načítanie EXIF databázy z Kroku 14"""
        self._print("\nLoading EXIF database from Step 14...", "INFO")
        
        if not self.exif_db_path.exists():
            self._print("WARNING: EXIF database not found - continuing without EXIF", "WARNING")
            return True
        
        try:
            with open(self.exif_db_path, 'r', encoding='utf-8') as f:
                self.exif_data = json.load(f)
            
            self._print("EXIF database loaded", "OK")
            return True
        except Exception as e:
            self._print(f"ERROR loading EXIF: {str(e)}", "ERROR")
            return True  # Continue without EXIF
    
    def collect_photos(self):
        """
        FÁZA 1: Zber všetkých validných fotografií.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("PHOTO COLLECTION PHASE", "TITLE")
        self._print("="*70, "TITLE")
        
        photo_counter = 1
        
        # Source 1: Validated photos from Step 15
        if self.valid_dir.exists():
            self._print("\nCollecting from Step 15 (Validation)...", "INFO")
            
            for source_file in self.valid_dir.rglob('*'):
                if source_file.is_file() and source_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.tif']:
                    # Generate catalog ID
                    catalog_id = f"{self.case_id}_{photo_counter:04d}"
                    catalog_filename = f"{catalog_id}{source_file.suffix.lower()}"
                    
                    # Copy to catalog
                    target_path = self.photos_dir / catalog_filename
                    shutil.copy2(source_file, target_path)
                    
                    # Record in collection
                    self.photo_collection.append({
                        'catalog_id': catalog_id,
                        'catalog_filename': catalog_filename,
                        'catalog_path': target_path,
                        'original_filename': source_file.name,
                        'source': 'validation',
                        'source_path': str(source_file)
                    })
                    
                    photo_counter += 1
                    self.stats['from_validation'] += 1
            
            self._print(f"Collected {self.stats['from_validation']} photos from validation", "OK")
        
        # Source 2: Repaired photos from Step 17
        if self.repaired_dir.exists():
            self._print("\nCollecting from Step 17 (Repair)...", "INFO")
            
            for source_file in self.repaired_dir.rglob('*'):
                if source_file.is_file() and source_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.tif']:
                    catalog_id = f"{self.case_id}_{photo_counter:04d}"
                    catalog_filename = f"{catalog_id}{source_file.suffix.lower()}"
                    
                    target_path = self.photos_dir / catalog_filename
                    shutil.copy2(source_file, target_path)
                    
                    self.photo_collection.append({
                        'catalog_id': catalog_id,
                        'catalog_filename': catalog_filename,
                        'catalog_path': target_path,
                        'original_filename': source_file.name,
                        'source': 'repair',
                        'source_path': str(source_file)
                    })
                    
                    photo_counter += 1
                    self.stats['from_repair'] += 1
            
            self._print(f"Collected {self.stats['from_repair']} photos from repair", "OK")
        
        self.stats['total_photos'] = len(self.photo_collection)
        
        self._print(f"\nTotal photos collected: {self.stats['total_photos']}", "OK")
        
        if self.stats['total_photos'] == 0:
            self._print("ERROR: No photos collected!", "ERROR")
            return False
        
        return True
    
    def generate_thumbnails(self):
        """
        FÁZA 2: Generovanie thumbnailov.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("THUMBNAIL GENERATION", "TITLE")
        self._print("="*70, "TITLE")
        
        total = len(self.photo_collection)
        
        self._print(f"\nGenerating thumbnails for {total} photos...", "INFO")
        
        for idx, photo in enumerate(self.photo_collection, 1):
            if idx % 50 == 0 or idx == total:
                self._print(f"Progress: {idx}/{total} ({idx*100//total}%)", "INFO")
            
            try:
                img = Image.open(photo['catalog_path'])
                
                # Get original dimensions
                photo['width'], photo['height'] = img.size
                photo['megapixels'] = round((photo['width'] * photo['height']) / 1_000_000, 1)
                
                # Generate thumbnails in 3 sizes
                photo['thumbnails'] = {}
                
                for size_name, size_dims in self.THUMBNAIL_SIZES.items():
                    thumb_filename = f"{photo['catalog_id']}_{size_name}.jpg"
                    thumb_path = self.thumbnails_base / size_name / thumb_filename
                    
                    # Create thumbnail
                    img_copy = img.copy()
                    img_copy.thumbnail(size_dims, Image.Resampling.LANCZOS)
                    img_copy.save(thumb_path, 'JPEG', quality=85, optimize=True)
                    
                    photo['thumbnails'][size_name] = str(thumb_path.relative_to(self.catalog_base))
                    self.stats['thumbnails_generated'] += 1
                
            except Exception as e:
                self._print(f"Thumbnail error for {photo['catalog_filename']}: {str(e)}", "WARNING")
                photo['thumbnails'] = {}
        
        self._print(f"\nThumbnails generated: {self.stats['thumbnails_generated']}", "OK")
    
    def consolidate_metadata(self):
        """
        FÁZA 3: Konsolidácia metadát.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("METADATA CONSOLIDATION", "TITLE")
        self._print("="*70, "TITLE")
        
        # Find matching EXIF data for each photo
        for photo in self.photo_collection:
            # Try to match by original filename
            exif_entry = None
            
            if self.exif_data:
                for exif_item in self.exif_data.get('exif_data', []):
                    if exif_item['filename'] == photo['original_filename']:
                        exif_entry = exif_item.get('exif')
                        break
            
            if exif_entry:
                photo['exif'] = exif_entry
                photo['has_exif'] = True
                self.stats['with_exif'] += 1
                
                # Extract key fields
                photo['datetime_original'] = exif_entry.get('datetime_original')
                photo['camera_make'] = exif_entry.get('make')
                photo['camera_model'] = exif_entry.get('model')
                photo['iso'] = exif_entry.get('iso')
                photo['f_number'] = exif_entry.get('f_number')
                photo['focal_length'] = exif_entry.get('focal_length')
                
                # GPS
                if 'gps_latitude' in exif_entry and 'gps_longitude' in exif_entry:
                    photo['gps_latitude'] = exif_entry['gps_latitude']
                    photo['gps_longitude'] = exif_entry['gps_longitude']
                    photo['has_gps'] = True
                    self.stats['with_gps'] += 1
                else:
                    photo['has_gps'] = False
            else:
                photo['has_exif'] = False
                photo['has_gps'] = False
        
        self._print(f"Photos with EXIF: {self.stats['with_exif']}/{self.stats['total_photos']}", "OK")
        self._print(f"Photos with GPS: {self.stats['with_gps']}/{self.stats['total_photos']}", "INFO")
    
    def create_indexes(self):
        """
        FÁZA 4: Vytvorenie indexov.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("INDEX CREATION", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Chronological index
        chronological = []
        dates = []
        
        for photo in self.photo_collection:
            if photo.get('datetime_original'):
                chronological.append({
                    'catalog_id': photo['catalog_id'],
                    'catalog_filename': photo['catalog_filename'],
                    'datetime_original': photo['datetime_original']
                })
                
                try:
                    dt = datetime.strptime(photo['datetime_original'], "%Y:%m:%d %H:%M:%S")
                    dates.append(dt)
                except:
                    pass
        
        chronological.sort(key=lambda x: x['datetime_original'])
        
        # Date range
        if dates:
            earliest = min(dates)
            latest = max(dates)
            self.stats['date_range']['earliest'] = earliest.strftime("%Y-%m-%d")
            self.stats['date_range']['latest'] = latest.strftime("%Y-%m-%d")
            self.stats['date_range']['span_days'] = (latest - earliest).days
        
        # Save chronological index
        with open(self.indexes_dir / 'chronological_index.json', 'w', encoding='utf-8') as f:
            json.dump(chronological, f, indent=2, ensure_ascii=False)
        
        self._print(f"Chronological index: {len(chronological)} photos with datetime", "OK")
        
        # 2. By camera index
        by_camera = defaultdict(list)
        
        for photo in self.photo_collection:
            camera_key = f"{photo.get('camera_make', 'Unknown')} {photo.get('camera_model', 'Unknown')}".strip()
            
            by_camera[camera_key].append({
                'catalog_id': photo['catalog_id'],
                'catalog_filename': photo['catalog_filename']
            })
        
        self.stats['unique_cameras'] = len(by_camera)
        
        # Save by camera index
        with open(self.indexes_dir / 'by_camera_index.json', 'w', encoding='utf-8') as f:
            json.dump(dict(by_camera), f, indent=2, ensure_ascii=False)
        
        self._print(f"By camera index: {len(by_camera)} unique cameras", "OK")
        
        # 3. GPS index
        gps_index = []
        
        for photo in self.photo_collection:
            if photo.get('has_gps'):
                gps_index.append({
                    'catalog_id': photo['catalog_id'],
                    'catalog_filename': photo['catalog_filename'],
                    'latitude': photo['gps_latitude'],
                    'longitude': photo['gps_longitude']
                })
        
        # Save GPS index
        with open(self.indexes_dir / 'gps_index.json', 'w', encoding='utf-8') as f:
            json.dump(gps_index, f, indent=2, ensure_ascii=False)
        
        self._print(f"GPS index: {len(gps_index)} photos with GPS", "OK")
    
    def generate_html_catalog(self):
        """
        FÁZA 5: Generovanie HTML katalógu.
        """
        self._print("\n" + "="*70, "TITLE")
        self._print("HTML CATALOG GENERATION", "TITLE")
        self._print("="*70, "TITLE")
        
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Photo Recovery Catalog - {self.case_id}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; }}
        
        .header {{ background: #2c3e50; color: white; padding: 20px; }}
        .header h1 {{ margin-bottom: 10px; }}
        .header .stats {{ display: flex; gap: 30px; font-size: 14px; opacity: 0.9; }}
        
        .controls {{ background: white; padding: 20px; margin: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .controls input, .controls select {{ padding: 10px; font-size: 14px; border: 1px solid #ddd; border-radius: 4px; }}
        .controls input {{ width: 300px; margin-right: 10px; }}
        
        .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; padding: 20px; }}
        
        .photo-card {{ background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: transform 0.2s; cursor: pointer; }}
        .photo-card:hover {{ transform: translateY(-4px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
        
        .photo-card img {{ width: 100%; height: 300px; object-fit: cover; }}
        
        .photo-info {{ padding: 15px; }}
        .photo-info .id {{ font-weight: bold; color: #2c3e50; margin-bottom: 8px; }}
        .photo-info .meta {{ font-size: 13px; color: #666; line-height: 1.6; }}
        .photo-info .meta strong {{ color: #333; }}
        
        .badge {{ display: inline-block; padding: 3px 8px; font-size: 11px; border-radius: 3px; margin-right: 5px; }}
        .badge-repair {{ background: #ff9800; color: white; }}
        .badge-gps {{ background: #4caf50; color: white; }}
        
        .lightbox {{ display: none; position: fixed; z-index: 1000; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); }}
        .lightbox.active {{ display: flex; align-items: center; justify-content: center; }}
        .lightbox img {{ max-width: 90%; max-height: 90%; object-fit: contain; }}
        .lightbox .close {{ position: absolute; top: 20px; right: 40px; color: white; font-size: 40px; cursor: pointer; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📷 Photo Recovery Catalog</h1>
        <div class="stats">
            <span>Case: {self.case_id}</span>
            <span>Total Photos: {self.stats['total_photos']}</span>
            <span>With EXIF: {self.stats['with_exif']}</span>
            <span>With GPS: {self.stats['with_gps']}</span>
            <span>Cameras: {self.stats['unique_cameras']}</span>
        </div>
    </div>
    
    <div class="controls">
        <input type="text" id="searchBox" placeholder="Search by filename, camera, date..." onkeyup="filterPhotos()">
        <select id="sortSelect" onchange="sortPhotos()">
            <option value="id">Sort by ID</option>
            <option value="date">Sort by Date</option>
            <option value="camera">Sort by Camera</option>
        </select>
    </div>
    
    <div class="gallery" id="gallery"></div>
    
    <div class="lightbox" id="lightbox" onclick="closeLightbox()">
        <span class="close">&times;</span>
        <img id="lightboxImage" src="" alt="">
    </div>
    
    <script>
        const photos = {json.dumps([{
            'catalog_id': p['catalog_id'],
            'catalog_filename': p['catalog_filename'],
            'original_filename': p['original_filename'],
            'source': p['source'],
            'datetime_original': p.get('datetime_original', ''),
            'camera': f"{p.get('camera_make', 'Unknown')} {p.get('camera_model', '')}".strip(),
            'iso': p.get('iso', ''),
            'has_gps': p.get('has_gps', False),
            'megapixels': p.get('megapixels', 0),
            'thumbnail': p['thumbnails'].get('medium', ''),
            'full_path': f"photos/{p['catalog_filename']}"
        } for p in self.photo_collection], indent=2)};
        
        let filteredPhotos = [...photos];
        
        function renderGallery() {{
            const gallery = document.getElementById('gallery');
            gallery.innerHTML = '';
            
            filteredPhotos.forEach(photo => {{
                const card = document.createElement('div');
                card.className = 'photo-card';
                card.onclick = () => openLightbox(photo.full_path);
                
                card.innerHTML = `
                    <img src="${{photo.thumbnail}}" alt="${{photo.catalog_filename}}">
                    <div class="photo-info">
                        <div class="id">${{photo.catalog_id}}</div>
                        ${{photo.source === 'repair' ? '<span class="badge badge-repair">REPAIRED</span>' : ''}}
                        ${{photo.has_gps ? '<span class="badge badge-gps">GPS</span>' : ''}}
                        <div class="meta">
                            <strong>Original:</strong> ${{photo.original_filename}}<br>
                            <strong>Camera:</strong> ${{photo.camera}}<br>
                            ${{photo.datetime_original ? `<strong>Date:</strong> ${{photo.datetime_original}}<br>` : ''}}
                            ${{photo.iso ? `<strong>ISO:</strong> ${{photo.iso}} ` : ''}}
                            ${{photo.megapixels ? `<strong>MP:</strong> ${{photo.megapixels}}` : ''}}
                        </div>
                    </div>
                `;
                
                gallery.appendChild(card);
            }});
        }}
        
        function filterPhotos() {{
            const query = document.getElementById('searchBox').value.toLowerCase();
            filteredPhotos = photos.filter(p => 
                p.catalog_filename.toLowerCase().includes(query) ||
                p.original_filename.toLowerCase().includes(query) ||
                p.camera.toLowerCase().includes(query) ||
                p.datetime_original.toLowerCase().includes(query)
            );
            renderGallery();
        }}
        
        function sortPhotos() {{
            const sortBy = document.getElementById('sortSelect').value;
            
            if (sortBy === 'id') {{
                filteredPhotos.sort((a, b) => a.catalog_id.localeCompare(b.catalog_id));
            }} else if (sortBy === 'date') {{
                filteredPhotos.sort((a, b) => (a.datetime_original || '').localeCompare(b.datetime_original || ''));
            }} else if (sortBy === 'camera') {{
                filteredPhotos.sort((a, b) => a.camera.localeCompare(b.camera));
            }}
            
            renderGallery();
        }}
        
        function openLightbox(imagePath) {{
            document.getElementById('lightboxImage').src = imagePath;
            document.getElementById('lightbox').classList.add('active');
        }}
        
        function closeLightbox() {{
            document.getElementById('lightbox').classList.remove('active');
        }}
        
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeLightbox();
        }});
        
        // Initial render
        renderGallery();
    </script>
</body>
</html>'''
        
        html_path = self.catalog_base / "photo_catalog.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        self._print(f"HTML catalog generated: {html_path.name}", "OK")
    
    def save_metadata_files(self):
        """Uloženie metadata súborov"""
        
        # 1. Complete catalog JSON
        catalog_json = self.metadata_dir / "complete_catalog.json"
        
        with open(catalog_json, 'w', encoding='utf-8') as f:
            json.dump(self.photo_collection, f, indent=2, ensure_ascii=False)
        
        self._print(f"Complete catalog saved: {catalog_json.name}", "OK")
        
        # 2. CSV export
        csv_file = self.metadata_dir / "catalog.csv"
        
        if self.photo_collection:
            fieldnames = ['catalog_id', 'catalog_filename', 'original_filename', 'source',
                         'datetime_original', 'camera_make', 'camera_model', 'iso',
                         'has_gps', 'gps_latitude', 'gps_longitude', 'megapixels']
            
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(self.photo_collection)
            
            self._print(f"CSV export saved: {csv_file.name}", "OK")
    
    def create_summary(self):
        """Vytvorenie súhrnného reportu"""
        
        summary = {
            "case_id": self.case_id,
            "timestamp": self.stats['timestamp'],
            "catalog_completeness": "100%",
            "statistics": self.stats,
            "cameras_detected": {},
            "output_structure": {
                "photos": str(self.photos_dir.relative_to(self.output_dir)),
                "thumbnails": str(self.thumbnails_base.relative_to(self.output_dir)),
                "metadata": str(self.metadata_dir.relative_to(self.output_dir)),
                "indexes": str(self.indexes_dir.relative_to(self.output_dir)),
                "html_catalog": "photo_catalog.html"
            }
        }
        
        # Camera breakdown
        for photo in self.photo_collection:
            camera = f"{photo.get('camera_make', 'Unknown')} {photo.get('camera_model', 'Unknown')}".strip()
            summary["cameras_detected"][camera] = summary["cameras_detected"].get(camera, 0) + 1
        
        # Save summary
        summary_file = self.catalog_base / "catalog_summary.json"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self._print(f"Summary report saved: {summary_file.name}", "OK")
        
        # Create README
        readme = self.catalog_base / "README.txt"
        
        with open(readme, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("PHOTO RECOVERY CATALOG\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"Case ID: {self.case_id}\n")
            f.write(f"Date: {self.stats['timestamp']}\n\n")
            
            f.write("CONTENTS:\n")
            f.write(f"  Total Photos: {self.stats['total_photos']}\n")
            f.write(f"  From Validation: {self.stats['from_validation']}\n")
            f.write(f"  From Repair: {self.stats['from_repair']}\n\n")
            
            f.write("STRUCTURE:\n")
            f.write("  photos/              - All recovered photos (renamed)\n")
            f.write("  thumbnails/          - Preview images (small/medium/large)\n")
            f.write("  metadata/            - Metadata catalog (JSON + CSV)\n")
            f.write("  indexes/             - Search indexes\n")
            f.write("  photo_catalog.html   - Interactive web catalog\n\n")
            
            f.write("HOW TO VIEW:\n")
            f.write("  1. Open photo_catalog.html in any web browser\n")
            f.write("  2. Use search box to find photos\n")
            f.write("  3. Click photos to view full size\n")
            f.write("  4. Use sort dropdown to organize\n\n")
            
            f.write("METADATA:\n")
            f.write(f"  Photos with EXIF: {self.stats['with_exif']}\n")
            f.write(f"  Photos with GPS: {self.stats['with_gps']}\n")
            f.write(f"  Unique cameras: {self.stats['unique_cameras']}\n\n")
            
            if self.stats['date_range']['earliest']:
                f.write("DATE RANGE:\n")
                f.write(f"  Earliest: {self.stats['date_range']['earliest']}\n")
                f.write(f"  Latest: {self.stats['date_range']['latest']}\n")
                f.write(f"  Span: {self.stats['date_range']['span_days']} days\n")
        
        self._print(f"README created: {readme.name}", "OK")
    
    def run_cataloging(self):
        """Hlavná funkcia - spustí celú katalogizáciu"""
        
        self._print("="*70, "TITLE")
        self._print("PHOTO CATALOGING", "TITLE")
        self._print(f"Case ID: {self.case_id}", "TITLE")
        self._print("="*70, "TITLE")
        
        # 1. Check tools
        if not self.check_tools():
            self.stats["success"] = False
            return self.stats
        
        # 2. Prepare directories
        self.prepare_directories()
        
        # 3. Load EXIF database
        self.load_exif_database()
        
        # 4. Collect photos
        if not self.collect_photos():
            self.stats["success"] = False
            return self.stats
        
        # 5. Generate thumbnails
        self.generate_thumbnails()
        
        # 6. Consolidate metadata
        self.consolidate_metadata()
        
        # 7. Create indexes
        self.create_indexes()
        
        # 8. Generate HTML catalog
        self.generate_html_catalog()
        
        # 9. Save metadata files
        self.save_metadata_files()
        
        # 10. Create summary
        self.create_summary()
        
        # 11. Final summary
        self._print("\n" + "="*70, "TITLE")
        self._print("CATALOGING COMPLETED", "OK")
        self._print("="*70, "TITLE")
        
        self._print(f"Total photos cataloged: {self.stats['total_photos']}", "OK")
        self._print(f"Thumbnails generated: {self.stats['thumbnails_generated']}", "OK")
        self._print(f"Metadata coverage: {self.stats['with_exif']}/{self.stats['total_photos']} ({self.stats['with_exif']/self.stats['total_photos']*100:.1f}%)", "OK")
        self._print(f"Output: {self.catalog_base}", "OK")
        
        self._print("="*70 + "\n", "TITLE")
        
        self.stats["success"] = True
        
        return self.stats


def main():
    """
    Hlavná funkcia
    """
    
    print("\n" + "="*70)
    print("FOR-COL-CATALOG: Photo Cataloging")
    print("="*70 + "\n")
    
    # Vstupné parametre
    if len(sys.argv) >= 2:
        case_id = sys.argv[1]
    else:
        case_id = input("Case ID (e.g., PHOTO-2025-01-26-001): ").strip()
    
    # Validácia
    if not case_id:
        print("ERROR: Case ID cannot be empty")
        sys.exit(1)
    
    # Run cataloging
    cataloger = PhotoCataloger(case_id)
    results = cataloger.run_cataloging()
    
    if results["success"]:
        print(f"\nCataloging completed successfully")
        print(f"Total photos: {results['total_photos']}")
        print(f"HTML catalog: {cataloger.catalog_base}/photo_catalog.html")
        print(f"\n🎉 Photo recovery workflow complete!")
        print(f"📦 Delivery package ready in: {cataloger.catalog_base}")
        sys.exit(0)
    else:
        print("\nCataloging failed - check logs for details")
        sys.exit(1)


if __name__ == "__main__":
    main()


"""
================================================================================
DOCUMENTATION - CATALOGING
================================================================================

PHOTO CATALOGING
- Final organization step
- Collects all valid photos from Steps 15 and 17
- Generates thumbnails, consolidates metadata
- Creates interactive HTML catalog
- Prepares delivery package

SIX-PHASE PROCESS

1. PHOTO COLLECTION
   - From validation/valid/ (Step 15)
   - From repair/repaired/ (Step 17 if exists)
   - Rename to CASEID_0001.jpg format
   - Preserve original filename mapping

2. THUMBNAIL GENERATION
   - 3 sizes: small (150px), medium (300px), large (600px)
   - LANCZOS resampling for quality
   - JPEG quality 85, optimized
   - ~3 thumbnails per photo = 720+ total

3. METADATA CONSOLIDATION
   - Load EXIF from Step 14
   - Match by original filename
   - Extract datetime, camera, GPS
   - Calculate coverage statistics

4. INDEX CREATION
   - Chronological: sorted by datetime
   - By Camera: grouped by make/model
   - GPS: only photos with coordinates
   - All saved as JSON

5. HTML CATALOG GENERATION
   - Interactive web interface
   - Search, filter, sort functionality
   - Lightbox view for full images
   - Responsive design
   - Works offline

6. FINAL SUMMARY
   - catalog_summary.json
   - README.txt for client
   - Complete documentation

OUTPUT STRUCTURE
catalog/
  ├─ photos/              (CASEID_0001.jpg renamed photos)
  ├─ thumbnails/
  │  ├─ small/           (150x150px)
  │  ├─ medium/          (300x300px)
  │  └─ large/           (600x600px)
  ├─ metadata/
  │  ├─ complete_catalog.json
  │  └─ catalog.csv
  ├─ indexes/
  │  ├─ chronological_index.json
  │  ├─ by_camera_index.json
  │  └─ gps_index.json
  ├─ photo_catalog.html  (interactive catalog)
  ├─ catalog_summary.json
  └─ README.txt

HTML CATALOG FEATURES
- Grid layout with medium thumbnails
- Search by filename, camera, date
- Filter by camera
- Sort by ID, date, or camera
- Lightbox modal for full view
- Responsive design
- Offline capability
- No external dependencies

================================================================================
EXAMPLE OUTPUT
================================================================================

======================================================================
PHOTO CATALOGING
Case ID: PHOTO-2025-01-26-001
======================================================================

Checking cataloging tools...
[✓] PIL/Pillow: Found

Loading EXIF database from Step 14...
[✓] EXIF database loaded

======================================================================
PHOTO COLLECTION PHASE
======================================================================

Collecting from Step 15 (Validation)...
[✓] Collected 623 photos from validation

Collecting from Step 17 (Repair)...
[✓] Collected 28 photos from repair

[✓] Total photos collected: 651

======================================================================
THUMBNAIL GENERATION
======================================================================

Generating thumbnails for 651 photos...
[i] Progress: 651/651 (100%)

[✓] Thumbnails generated: 1953

======================================================================
METADATA CONSOLIDATION
======================================================================

[✓] Photos with EXIF: 589/651
[i] Photos with GPS: 312/651

======================================================================
INDEX CREATION
======================================================================

[✓] Chronological index: 589 photos with datetime
[✓] By camera index: 7 unique cameras
[✓] GPS index: 312 photos with GPS

======================================================================
HTML CATALOG GENERATION
======================================================================

[✓] HTML catalog generated: photo_catalog.html

[✓] Complete catalog saved: complete_catalog.json
[✓] CSV export saved: catalog.csv
[✓] Summary report saved: catalog_summary.json
[✓] README created: README.txt

======================================================================
CATALOGING COMPLETED
======================================================================
[✓] Total photos cataloged: 651
[✓] Thumbnails generated: 1953
[✓] Metadata coverage: 589/651 (90.5%)
[✓] Output: /outputs/PHOTO-2025-01-26-001_catalog
======================================================================

Cataloging completed successfully
Total photos: 651
HTML catalog: PHOTO-2025-01-26-001_catalog/photo_catalog.html

🎉 Photo recovery workflow complete!
📦 Delivery package ready in: PHOTO-2025-01-26-001_catalog

================================================================================
USAGE
================================================================================

INTERACTIVE MODE:
$ python3 step18_cataloging.py
Case ID: PHOTO-2025-01-26-001

COMMAND LINE MODE:
$ python3 step18_cataloging.py PHOTO-2025-01-26-001

REQUIREMENTS:
- Step 15 (Validation) must be completed
- Step 14 (EXIF Analysis) recommended
- Step 17 (Repair) optional
- PIL/Pillow: pip install Pillow --break-system-packages

TIME ESTIMATE:
- ~30-60 minutes depending on number of photos
- Thumbnail generation is the slowest part

================================================================================
FINAL DELIVERY PACKAGE
================================================================================

The catalog/ directory is the complete delivery package:

1. README.txt - Instructions for client
2. photo_catalog.html - Open in browser to view
3. photos/ - All recovered photos (renamed)
4. thumbnails/ - Preview images
5. metadata/ - Complete catalogs (JSON + CSV)
6. indexes/ - Search indexes

CLIENT INSTRUCTIONS:
1. Open photo_catalog.html in any browser
2. Search, filter, and sort photos
3. Click to view full size
4. All photos are in photos/ directory

METADATA COVERAGE TARGETS:
- Catalog completeness: 100%
- EXIF datetime: >90%
- Thumbnail success: >95%
- GPS coverage: 30-50% (smartphones)

================================================================================
"""