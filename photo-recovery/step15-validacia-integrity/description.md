# Detaily testu

## Úkol

Overiť fyzickú integritu všetkých obnovených fotografií a rozdeliť ich do kategórií: validné (plne funkčné), poškodené (čiastočne čitateľné, opraviteľné), neopraviteľné (nekompletné, false positives).

## Obtiažnosť

Snadné

## Časová náročnosť

30

## Automatický test

Áno - Python skript s ImageMagick, PIL, jpeginfo a pngcheck automaticky validuje každý súbor viacerými nástrojmi, testuje dekódovanie a pixel integrity

## Popis

Validácia integrity je kritický krok pred odovzdaním fotografií klientovi. Nie všetky obnovené súbory sú nutne plne funkčné - môžu byť čiastočne prepísané, fragmentované alebo false positives z file carvingu.

Prečo je tento krok kritický:
- Overenie že fotografie sú skutočne otvárateľné a funkčné
- Identifikácia poškodených súborov ktoré potrebujú opravu (krok 17)
- Eliminácia false positives (súbory ktoré nie sú fotografie)
- Kategorizácia pre ďalšie kroky (validné → katalogizácia, poškodené → oprava)
- Pri FS-based (12A) očakávame >95% validných, pri File Carving (12B) 70-85%
- Vymazané súbory majú nižšiu integritu než aktívne (čiastočne prepísané)

Typy poškodenia: chybný header (opraviteľné), chybný footer (opraviteľné), stredové bloky poškodené (čiastočne opraviteľné), fragmentácia (ťažké), false positive (neopraviteľné), nekompletný súbor (zriedka opraviteľné). Používame multi-tool approach: ImageMagick + PIL + format-specific (jpeginfo, pngcheck).

## Jak na to

1. ZÁKLADNÁ VALIDÁCIA - pre každý súbor: file command (MIME type check), xxd na prvých 8 bytes (magic bytes signature: JPEG=FFD8FF, PNG=89504E47, TIFF=49492A00), zisti veľkosť, vyradi prázdne súbory
2. DETAILNÁ VALIDÁCIA - ImageMagick identify -verbose (universálny test štruktúry), Python PIL Image.open + verify + load (test dekódovania pixelov), format-specific: jpeginfo -c pre JPEG (test segmentov), pngcheck -v pre PNG (test chunks a CRC)
3. ROZHODOVACIA LOGIKA - ak všetky nástroje OK → validný, ak aspoň jeden nástroj OK → poškodený (opraviteľný), ak všetky nástroje FAIL → neopraviteľný, zaznamenaj typ chyby (truncated, corrupt_data, invalid_header, invalid_segment)
4. KATEGORIZÁCIA A ORGANIZÁCIA - skopíruj súbory do adresárov: validation/valid/ (plne funkčné), validation/corrupted/ (pokus o opravu v kroku 17), validation/unrecoverable/ (false positives, vyradiť)
5. ANALÝZA POŠKODENÍ - pre poškodené súbory: identifikuj typ chyby z error messages, urči opraviteľnosť (Level 1: header/footer = ľahko, Level 2: segments = stredne, Level 3: pixel data = čiastočne, Level 4: fragmentácia = ťažko)
6. ŠTATISTIKY A REPORT - vypo čítaj integrity score (% validných), porovnaj aktívne vs vymazané súbory (ak 12A), vytvor JSON report s detailmi každého súboru, ulož zoznam opraviteľných súborov pre krok 17

---

## Výsledek

Klasifikácia všetkých obnovených fotografií. Štatistiky: počet validných (cieľ >90%), poškodených (potenciálne opraviteľných), neopraviteľných (false positives). Integrity score: % validných fotografií (FS-based >95%, File Carving 70-85%). Porovnanie aktívne vs vymazané: aktívne ~99% validné, vymazané ~78% validné (čiastočne prepísané). Analýza typov poškodení: truncated files, invalid segments, corrupt data, false positives. Organizované adresáre pre ďalšie kroky. Report obsahuje pre každý poškodený súbor: typ chyby, nástroj ktorý detekoval, opraviteľnosť, odporúčanú techniku opravy.

## Reference

ISO/IEC 10918-1 - JPEG Standard
PNG Specification - ISO/IEC 15948:2004
NIST SP 800-86 - Section 3.1.3 (Data Validation)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)

## Automatizovaný skript vykoná

### 1. Validácia všetkých fotografií
```python
def validate_all_images(catalog):
    results = []
    
    for file_entry in catalog['files']:
        filepath = file_entry['path']
        file_format = file_entry['format']
        
        validation = validate_image(filepath, file_format)
        
        result = {
            'file_id': file_entry['id'],
            'filename': file_entry['filename'],
            'status': validation['status'],
            'error': validation.get('error'),
            'details': validation.get('details')
        }
        results.append(result)
    
    return results
```

### 2. Format-specific validácia
```python
def validate_image(filepath, file_format):
    """
    Použiť špecifický validator podľa formátu
    """
    validators = {
        'JPEG': validate_jpeg,
        'PNG': validate_png,
        'TIFF': validate_tiff,
        'GIF': validate_gif
    }
    
    validator = validators.get(file_format, validate_generic)
    return validator(filepath)
```

### 3. JPEG validácia
```python
def validate_jpeg(filepath):
    try:
        # Pillow validation
        img = Image.open(filepath)
        img.verify()
        
        # Reopen and check dimensions
        img = Image.open(filepath)
        width, height = img.size
        
        if width == 0 or height == 0:
            return {
                'status': 'CORRUPTED',
                'error': 'Invalid dimensions'
            }
        
        # Try to load all data
        img.load()
        
        # Check JPEG markers
        with open(filepath, 'rb') as f:
            header = f.read(2)
            if header != b'\xff\xd8':
                return {
                    'status': 'CORRUPTED',
                    'error': 'Invalid JPEG header'
                }
            
            # Seek to end
            f.seek(-2, 2)
            footer = f.read(2)
            if footer != b'\xff\xd9':
                return {
                    'status': 'CORRUPTED',
                    'error': 'Missing JPEG footer (truncated)'
                }
        
        return {
            'status': 'VALID',
            'details': {
                'width': width,
                'height': height,
                'mode': img.mode
            }
        }
        
    except Exception as e:
        return {
            'status': 'CORRUPTED',
            'error': str(e)
        }
```

### 4. PNG validácia
```python
def validate_png(filepath):
    try:
        # Pillow validation
        img = Image.open(filepath)
        img.verify()
        
        img = Image.open(filepath)
        img.load()
        
        # Check PNG signature
        with open(filepath, 'rb') as f:
            signature = f.read(8)
            expected = b'\x89PNG\r\n\x1a\n'
            if signature != expected:
                return {
                    'status': 'CORRUPTED',
                    'error': 'Invalid PNG signature'
                }
        
        return {
            'status': 'VALID',
            'details': {
                'width': img.width,
                'height': img.height,
                'mode': img.mode
            }
        }
        
    except Exception as e:
        return {
            'status': 'CORRUPTED',
            'error': str(e)
        }
```

### 5. Detekcia čiastočného poškodenia
```python
def detect_partial_corruption(filepath):
    """
    Niektoré JPEG môžu byť čiastočne poškodené ale stále zobraziteľné
    """
    try:
        img = Image.open(filepath)
        pixels = list(img.getdata())
        
        # Check for missing data patterns
        if len(pixels) < (img.width * img.height):
            return 'PARTIAL_CORRUPTION'
        
        return 'VALID'
        
    except Exception:
        return 'CORRUPTED'
```

## Klasifikácia statusov

### ✅ VALID
- Súbor je plne funkčný
- Dá sa otvoriť a zobraziť
- Žiadne chyby

### ⚠️ PARTIAL_CORRUPTION
- Súbor sa dá otvoriť
- Niektoré časti dát chýbajú
- Zobraziteľný, ale s artefaktmi

### ❌ CORRUPTED
- Súbor sa nedá otvoriť
- Chýbajúce/neplatné hlavičky
- Vyžaduje opravu

### ❌ UNRECOVERABLE
- Príliš veľké poškodenie
- Oprava nie je možná

## Výstupný report
```json
{
  "case_id": "2026-01-21-001",
  "total_files": 412,
  "validation_summary": {
    "valid": 358,
    "partial_corruption": 32,
    "corrupted": 18,
    "unrecoverable": 4
  },
  "validation_results": [
    {
      "file_id": 1,
      "filename": "IMG_20250115_143022.jpg",
      "status": "VALID",
      "details": {
        "width": 6720,
        "height": 4480,
        "mode": "RGB"
      }
    },
    {
      "file_id": 87,
      "filename": "f12345678.jpg",
      "status": "CORRUPTED",
      "error": "Missing JPEG footer (truncated)",
      "repair_possible": true
    }
  ],
  "files_needing_repair": [87, 143, 256],
  "timestamp": "2026-01-21T19:45:00Z"
}
```

## Štatistiky podľa formátu
```json
{
  "by_format": {
    "JPEG": {
      "total": 358,
      "valid": 324,
      "corrupted": 34
    },
    "PNG": {
      "total": 42,
      "valid": 40,
      "corrupted": 2
    },
    "TIFF": {
      "total": 12,
      "valid": 11,
      "corrupted": 1
    }
  }
}
```

## Poznámky
- Validácia je kritická pred odovzdaním klientovi
- Niektoré carved súbory môžu byť čiastočne poškodené
- JPEG má dobrú toleranciu chýb (progressive format)
- PNG je citlivejší na poškodenie
