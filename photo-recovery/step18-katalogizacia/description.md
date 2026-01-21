# Detaily testu

## Úkol

Zozbierať všetky validné fotografie, organizovať ich do prehľadnej štruktúry, vytvoriť katalóg s metadata a pripraviť ich na odovzdanie klientovi.

## Obtiažnosť

Střední

## Časová náročnosť

45

## Automatický test

Áno - Python workflow automaticky zbiera fotografie z krokov 15 a 17, generuje thumbnaily, extrahuje EXIF metadata, vytvára indexy a HTML katalóg

## Popis

Katalogizácia je finálny organizačný krok pred vytvorením reportu. Cieľom je systematicky usporiadať všetky validné fotografie, priradiť jednotné pomenovanie, vytvoriť náhľady a pripraviť komplexný katalóg s metadátami.

Prečo je tento krok kritický:
- Poskytuje klientovi prehľadný katalóg všetkých obnovených fotografií
- Umožňuje rýchlu navigáciu cez thumbnaily a vyhľadávanie
- Zachováva všetky metadata (EXIF, GPS, camera info) v prehľadnej forme
- Vytvára chronologický timeline a indexy podľa fotoaparátu
- Pripravuje fotografie na delivery v profesionálnej forme
- 5 fáz: zber (z krokov 15+17) → thumbnaily (3 veľkosti) → metadata extrakcia → indexy (chronologický, camera, GPS) → HTML katalóg

Katalogizácia konsoliduje 236-240 fotografií, vytvára 720+ thumbnailov, extrahuje kompletné EXIF metadata (očakávané pokrytie >90%), generuje interaktívny HTML katalóg s vyhľadávaním a filtrovaním. Výsledok: profesionálny delivery package pripravený na odovzdanie.

## Jak na to

1. ZBER VŠETKÝCH VALIDNÝCH FOTOGRAFIÍ - identifikuj zdroje: validation/valid/ z kroku 15, repair/repaired/ z kroku 17 (ak existuje), skopíruj do catalog/photos/ s jednotným pomenovaním CASEID_0001.jpg až CASEID_NNNN.jpg, zachovaj mapovanie originálny→katalógový názov v collection_index.json
2. GENEROVANIE THUMBNAILOV - Python PIL/Pillow vytvor 3 veľkosti: small 150x150, medium 300x300, large 600x600, použiť LANCZOS resampling pre kvalitu, uložiť do catalog/thumbnails/small|medium|large/, quality=85 optimize=True, ulož thumbnail_index.json
3. EXTRAKCIA METADÁT - exiftool -j -G pre každú fotografiu, extrahuj: datetime_original, camera_make/model, ISO/aperture/shutter, GPS coordinates, rozlíšenie/megapixely, vytvor metadata_catalog.json a CSV pre Excel
4. VYTVORENIE INDEXOV - chronologický index (zoradené podľa DateTimeOriginal), by_camera index (zoskupené podľa fotoaparátu), GPS index (len fotky s GPS), ulož do catalog/indexes/, každý index vo formáte JSON
5. VYGENEROVANIE HTML KATALÓGU - vytvor interaktívny photo_catalog.html: grid layout s medium thumbnailami, vyhľadávanie (fulltext), filtrovanie (fotoaparát), zoradenie (ID/dátum/camera), lightbox modal pre plné zobrazenie, responzívny dizajn, funguje offline
6. FINÁLNY REPORT A ORGANIZÁCIA - vytvor súhrnný catalog_summary.json: počet fotografií, metadata coverage (% s EXIF), date range, zoznam fotoaparátov, odkazy na všetky súbory, catalog completeness 100%, ulož cataloging_report.json s kompletnou dokumentáciou

---

## Výsledek

Komplexný katalóg všetkých validných fotografií. Štruktúra: catalog/photos/ (240 fotografií s jednotným pomenovaním), catalog/thumbnails/ (720 thumbnailov v 3 veľkostiach), catalog/metadata/ (JSON a CSV katalógy), catalog/indexes/ (chronologický, camera, GPS), photo_catalog.html (interaktívny). Metriky: catalog completeness 100%, metadata coverage >90% (EXIF datetime), thumbnail success rate >95%, 2-3 unikátne fotoaparáty detekované, date range 20-30 dní. HTML katalóg funkcie: search, filter by camera, sort by date/ID, lightbox view, responsive design, offline capable. Delivery package pripravený na odovzdanie s README pre klienta.

## Reference

ISO/IEC 27037:2012 - Section 7.7 (Documentation and reporting)
NIST SP 800-86 - Section 3.3 (Reporting)
Dublin Core Metadata - Standard pre metadata katalogizáciu
EXIF Standard JEITA CP-3451

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
        
        # Find repair info if exists
        repair_info = find_by_id(repair, file_id) if repair else None
        
        # Create comprehensive entry
        entry = {
            'id': file_id,
            'filename': file_entry['filename'],
            'path': file_entry['path'],
            'size_bytes': file_entry['size'],
            'hash_sha256': file_entry['hash'],
            'format': file_entry['format'],
            'recovery_method': file_entry['recovery_method'],
            
            # EXIF metadata
            'exif': exif['exif'] if exif else None,
            
            # Validation
            'integrity_status': val_status['status'],
            
            # Repair (if applicable)
            'was_repaired': repair_info['repair_success'] if repair_info else False,
            
            # Derived fields
            'has_gps': exif and 'gps_latitude' in exif['exif'],
            'has_datetime': exif and 'datetime_original' in exif['exif'],
            'device': get_device_name(exif) if exif else 'Unknown'
        }
        
        catalog.append(entry)
    
    return catalog
```

### 2. SQLite databáza
```python
def create_sqlite_catalog(catalog, db_path):
    """
    Vytvorenie SQLite databázy pre efektívne queries
    """
    import sqlite3
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table
    cursor.execute('''
        CREATE TABLE photos (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER,
            hash_sha256 TEXT,
            format TEXT,
            recovery_method TEXT,
            integrity_status TEXT,
            was_repaired BOOLEAN,
            
            -- EXIF fields
            device_make TEXT,
            device_model TEXT,
            datetime_original TEXT,
            iso INTEGER,
            focal_length TEXT,
            gps_latitude REAL,
            gps_longitude REAL,
            
            -- Search index
            search_text TEXT
        )
    ''')
    
    # Insert data
    for entry in catalog:
        exif = entry.get('exif', {})
        
        search_text = create_search_text(entry)
        
        cursor.execute('''
            INSERT INTO photos VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?
            )
        ''', (
            entry['id'],
            entry['filename'],
            entry['path'],
            entry['size_bytes'],
            entry['hash_sha256'],
            entry['format'],
            entry['recovery_method'],
            entry['integrity_status'],
            entry['was_repaired'],
            
            exif.get('make'),
            exif.get('model'),
            exif.get('datetime_original'),
            exif.get('iso'),
            exif.get('focal_length'),
            exif.get('gps_latitude'),
            exif.get('gps_longitude'),
            
            search_text
        ))
    
    # Create indexes
    cursor.execute('CREATE INDEX idx_datetime ON photos(datetime_original)')
    cursor.execute('CREATE INDEX idx_device ON photos(device_make, device_model)')
    cursor.execute('CREATE INDEX idx_status ON photos(integrity_status)')
    cursor.execute('CREATE INDEX idx_search ON photos(search_text)')
    
    conn.commit()
    conn.close()
```

### 3. Fulltextové vyhľadávanie
```python
def create_search_text(entry):
    """
    Vytvoriť searchable text pre každú fotografiu
    """
    parts = [
        entry['filename'],
        entry['format'],
        entry['recovery_method'],
        entry['device']
    ]
    
    if entry.get('exif'):
        exif = entry['exif']
        if 'datetime_original' in exif:
            parts.append(exif['datetime_original'])
        if 'make' in exif:
            parts.append(exif['make'])
        if 'model' in exif:
            parts.append(exif['model'])
    
    return ' '.join(str(p) for p in parts if p)

def search_catalog(db_path, query):
    """
    Fulltextové vyhľadávanie v katalógu
    """
    import sqlite3
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM photos 
        WHERE search_text LIKE ?
        ORDER BY datetime_original DESC
    ''', (f'%{query}%',))
    
    results = cursor.fetchall()
    conn.close()
    
    return results
```

### 4. Generovanie thumbnails
```python
def generate_thumbnails(catalog, thumb_dir):
    """
    Vytvoriť náhľady pre HTML galériu
    """
    from PIL import Image
    
    os.makedirs(thumb_dir, exist_ok=True)
    
    for entry in catalog:
        try:
            img = Image.open(entry['path'])
            
            # Create thumbnail (200x200)
            img.thumbnail((200, 200))
            
            thumb_filename = f"thumb_{entry['id']}.jpg"
            thumb_path = os.path.join(thumb_dir, thumb_filename)
            
            img.save(thumb_path, 'JPEG', quality=85)
            
            entry['thumbnail'] = thumb_path
            
        except Exception as e:
            entry['thumbnail'] = None
            print(f"Failed to create thumbnail for {entry['filename']}: {e}")
```

### 5. HTML galéria
```python
def generate_html_gallery(catalog, output_path):
    """
    Vytvoriť interaktívnu HTML galériu
    """
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Photo Recovery Gallery - {catalog['case_id']}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }}
            .photo-card {{ border: 1px solid #ddd; padding: 10px; }}
            .photo-card img {{ width: 100%; height: auto; }}
            .photo-info {{ font-size: 12px; margin-top: 10px; }}
            .status-valid {{ color: green; }}
            .status-repaired {{ color: orange; }}
        </style>
    </head>
    <body>
        <h1>Photo Recovery Gallery</h1>
        <p>Total photos: {len(catalog)}</p>
        
        <div class="gallery">
    '''
    
    for entry in catalog:
        status_class = 'status-valid' if entry['integrity_status'] == 'VALID' else 'status-repaired'
        repair_badge = '🔧 Repaired' if entry['was_repaired'] else ''
        
        html += f'''
        <div class="photo-card">
            <img src="{entry['thumbnail']}" alt="{entry['filename']}">
            <div class="photo-info">
                <strong>{entry['filename']}</strong><br>
                Device: {entry['device']}<br>
                Date: {entry.get('exif', {}).get('datetime_original', 'Unknown')}<br>
                <span class="{status_class}">{entry['integrity_status']}</span> {repair_badge}
            </div>
        </div>
        '''
    
    html += '''
        </div>
    </body>
    </html>
    '''
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
```

## Výstupné formáty

### 1. JSON katalóg
Kompletná databáza v JSON formáte.

### 2. SQLite databáza
Pre programatický prístup a queries.

### 3. CSV export
```csv
id,filename,format,device,datetime,gps_lat,gps_lon,status,repaired
1,IMG_001.jpg,JPEG,Canon EOS 5D,2025-01-15,48.8566,2.3522,VALID,false
```

### 4. HTML galéria
Interaktívna web stránka s náhľadmi.

## Vyhľadávacie funkcie

```python
# By date range
search_by_date(db, '2025-01-01', '2025-01-31')

# By device
search_by_device(db, 'Canon', 'EOS 5D')

# By location (radius search)
search_by_location(db, 48.8566, 2.3522, radius_km=10)

# By keyword
search_by_keyword(db, 'vacation')
```

## Poznámky
- Katalóg je finálny dataset pre odovzdanie
- Umožňuje klientovi efektívne prehľadávať obnovené fotografie
- Všetky dáta z predchádzajúcich krokov sú integrované
