# Detaily testu

## Úkol

Extrahovať a analyzovať EXIF metadáta zo všetkých obnovených fotografií pre získanie časových značiek, informácií o fotoaparáte, nastavení, GPS súradníc a detekciu upravených fotografií.

## Obtiažnosť

Snadné

## Časová náročnosť

30

## Automatický test

Áno - Python skript s ExifTool automaticky extrahuje EXIF (DateTimeOriginal, Make, Model, GPS, ISO, clona), analyzuje 7 kategórií, vytvorí timeline a GPS mapu

## Popis

EXIF (Exchangeable Image File Format) sú metadáta embedded priamo v obrazových súboroch. Väčšina digitálnych fotoaparátov a smartfónov automaticky vkladá EXIF dáta do každej fotografie. Pri File Carving (12B) sme stratili FS timestamps, takže DateTimeOriginal je jediná spoľahlivá časová informácia.

Prečo je tento krok kritický:
- Časové informácie - DateTimeOriginal umožňuje vytvoriť presný timeline fotografií
- Identifikácia zariadenia - Make + Model + SerialNumber identifikujú konkrétny fotoaparát/telefón
- GPS lokalizácia - ak sú GPS dáta → geografická mapa kde bola fotka vytvorená
- Detekcia úprav - Software tag a rozdiel medzi DateTimeOriginal a ModifyDate indikujú úpravu
- Nastavenia fotoaparátu - ISO, clona, ohnisková vzdialenosť pre technickú analýzu
- Pri FS-based (12A) máme FS timestamps, pri File Carving (12B) len EXIF

Typické EXIF tagy: DateTimeOriginal (čas vytvorenia), Make/Model (fotoaparát), SerialNumber, ISO, FNumber (clona), ExposureTime, FocalLength, GPSLatitude/GPSLongitude, Software (editing).

## Jak na to

1. EXTRAKCIA - spusti exiftool -j -G -a -s -n -r na adresár s fotografiami, vygeneruj JSON a CSV output (pre Excel), trvanie závisí od počtu súborov
2. ANALÝZA ČASU - pre každú fotografiu: načítaj DateTimeOriginal/CreateDate, zisti časové rozpätie (earliest→latest), deteknuj fotky bez časových tagov, deteknuj ModifyDate > DateTimeOriginal (upravené)
3. ANALÝZA FOTOAPARÁTOV - zisti unikátne kombinácie Make+Model, zisti unikátne sériové čísla, vytvor distribúciu (top 5 fotoaparátov), identifikuj či sú fotky z viacerých zariadení
4. NASTAVENIA A GPS - analyzuj rozsah ISO/clona/ohnisková vzdialenosť (min/max/avg), spočítaj fotky s GPS súradnicami, vytvor interaktívnu GPS mapu (Leaflet.js HTML) ak GPS existujú
5. DETEKCIA ÚPRAV A ANOMÁLIÍ - deteknuj Software tag (Photoshop, Lightroom, GIMP, Instagram), deteknuj anomálie (chýbajúce EXIF, budúce dátumy, neobvyklé ISO), klasifikuj kvalitu EXIF dát
6. TIMELINE A REPORT - vytvor timeline (fotky zoskupené podľa dátumu), vygeneruj timeline graf (matplotlib), vytvor textový/PDF report so štatistikami, ulož JSON databázu pre ďalšie kroky

---

## Výsledek

Komplexná databáza EXIF metadát (JSON + CSV). Štatistiky: % fotografií s DateTimeOriginal (cieľ >90%), časové rozpätie (dni), počet unikátnych fotoaparátov, rozsah nastavení (ISO, clona), % fotografií s GPS, % upravených fotografií, % anomálií (cieľ <5%). Timeline vizualizácia (graf + HTML). GPS mapa (interaktívna HTML ak GPS existujú). EXIF quality score: excellent (>90% DateTimeOriginal), good (70-90%), fair (50-70%), poor (<50%). Interpretácia: vysoké % DateTimeOriginal = úspešná obnova, viacero fotoaparátov = normálne, GPS len na niektorých = smartphone vs fotoaparát.

## Reference

EXIF 2.32 Specification (CIPA DC-008-2019)
ISO 12234-2:2001 - Electronic still-picture imaging
ExifTool Documentation

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
```python
import exifread

def extract_exif_exifread(image_path):
    with open(image_path, 'rb') as f:
        tags = exifread.process_file(f)
    
    exif = {}
    for tag, value in tags.items():
        exif[tag] = str(value)
    return exif
```

## Automatizovaný skript vykoná

### 1. Extrakcia EXIF pre všetky fotografie
```python
def analyze_exif_batch(catalog):
    results = []
    
    for file_entry in catalog['files']:
        try:
            exif = extract_exif(file_entry['path'])
            
            result = {
                'file_id': file_entry['id'],
                'filename': file_entry['filename'],
                'exif_present': exif is not None,
                'exif_data': parse_exif(exif) if exif else None
            }
            results.append(result)
            
        except Exception as e:
            results.append({
                'file_id': file_entry['id'],
                'filename': file_entry['filename'],
                'exif_present': False,
                'error': str(e)
            })
    
    return results
```

### 2. Parsovanie relevantných EXIF polí
```python
def parse_exif(raw_exif):
    """
    Extrahovať najdôležitejšie EXIF polia
    """
    parsed = {
        # Základné info
        'make': raw_exif.get('Make'),
        'model': raw_exif.get('Model'),
        'software': raw_exif.get('Software'),
        
        # Dátum a čas
        'datetime_original': raw_exif.get('DateTimeOriginal'),
        'datetime_digitized': raw_exif.get('DateTimeDigitized'),
        
        # Nastavenia fotoaparátu
        'iso': raw_exif.get('ISOSpeedRatings'),
        'exposure_time': raw_exif.get('ExposureTime'),
        'f_number': raw_exif.get('FNumber'),
        'focal_length': raw_exif.get('FocalLength'),
        'flash': raw_exif.get('Flash'),
        
        # Rozlíšenie
        'width': raw_exif.get('ExifImageWidth'),
        'height': raw_exif.get('ExifImageHeight'),
        'orientation': raw_exif.get('Orientation'),
        
        # GPS (ak je dostupné)
        'gps_latitude': extract_gps_lat(raw_exif),
        'gps_longitude': extract_gps_lon(raw_exif),
        'gps_altitude': raw_exif.get('GPSAltitude'),
    }
    
    return {k: v for k, v in parsed.items() if v is not None}
```

### 3. GPS konverzia
```python
def extract_gps_lat(exif):
    """
    Konvertovať GPS súradnice z EXIF formátu na desatinné stupne
    """
    gps_lat = exif.get('GPSLatitude')
    gps_lat_ref = exif.get('GPSLatitudeRef')
    
    if gps_lat and gps_lat_ref:
        lat = convert_to_degrees(gps_lat)
        if gps_lat_ref == 'S':
            lat = -lat
        return lat
    return None

def convert_to_degrees(value):
    """
    Konverzia z [deg, min, sec] na desatinné stupne
    """
    d, m, s = value
    return d + (m / 60.0) + (s / 3600.0)
```

## Výstupná EXIF databáza (JSON)
```json
{
  "case_id": "2026-01-21-001",
  "total_files": 412,
  "files_with_exif": 358,
  "files_without_exif": 54,
  "exif_data": [
    {
      "file_id": 1,
      "filename": "IMG_20250115_143022.jpg",
      "exif": {
        "make": "Canon",
        "model": "Canon EOS 5D Mark IV",
        "datetime_original": "2025:01:15 14:30:22",
        "iso": 400,
        "exposure_time": "1/250",
        "f_number": 5.6,
        "focal_length": "85mm",
        "width": 6720,
        "height": 4480,
        "gps_latitude": 48.8566,
        "gps_longitude": 2.3522
      }
    }
  ],
  "timestamp": "2026-01-21T19:15:00Z"
}
```

## Štatistiky metadát
```json
{
  "statistics": {
    "devices": {
      "Canon EOS 5D Mark IV": 124,
      "iPhone 13 Pro": 89,
      "Samsung Galaxy S21": 67,
      "Unknown": 132
    },
    "date_range": {
      "earliest": "2024-03-12",
      "latest": "2026-01-18"
    },
    "gps_available": 234,
    "software_used": {
      "Adobe Photoshop": 45,
      "Instagram": 23,
      "GIMP": 12
    }
  }
}
```

## Užitočné vyhľadávacie možnosti

### Podľa dátumu
```python
def filter_by_date_range(exif_db, start_date, end_date):
    return [f for f in exif_db if start_date <= f['datetime_original'] <= end_date]
```

### Podľa zariadenia
```python
def filter_by_device(exif_db, make, model):
    return [f for f in exif_db if f['make'] == make and f['model'] == model]
```

### Podľa GPS lokality
```python
def filter_by_location(exif_db, lat, lon, radius_km):
    return [f for f in exif_db if distance(f['gps'], (lat, lon)) < radius_km]
```

## Export formáty

### CSV export
```csv
filename,make,model,datetime,iso,lat,lon
IMG_001.jpg,Canon,EOS 5D,2025-01-15 14:30:22,400,48.8566,2.3522
```

### HTML report s mapou
- Interaktívna mapa s GPS značkami
- Timeline fotografií
- Galéria organizovaná podľa zariadenia

## Poznámky
- Nie všetky fotografie obsahujú EXIF
- Carved súbory (krok 12B) často strácajú EXIF
- GPS dáta sú citlivé - privacy consideration
- EXIF môže byť modifikovaný/odstránený softwarom
