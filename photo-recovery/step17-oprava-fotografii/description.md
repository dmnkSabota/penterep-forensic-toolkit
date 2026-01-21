# Detaily testu

## Úkol
Pokúsiť sa opraviť identifikované poškodené fotografie pomocou automatizovaných techník a manuálnych metód.

## Obtiažnosť
Střední

## Časová náročnosť
45

## Automatický test
Čiastočne - Automatické opravy pre bežné typy poškodení (invalid header/footer, corrupt segments), manuálne techniky vyžadujú hex editor a expertízu pre komplexné prípady.

## Popis

Oprava fotografií kombinuje automatizované nástroje (PIL, ImageMagick, jpeginfo) s manuálnymi technikami pre obnovenie poškodených súborov. Úspešnosť závisí od typu poškodenia: chybný header/footer (90%+ opraviteľnosť), invalid segment (80%), truncated file (50-70%), fragmentácia (5-15%).

**Prečo je tento krok kritický:**

- **Maximalizácia recovery:** Každá opravená fotografia zvyšuje finálny počet validných súborov
- **Prioritizácia:** Rýchle opravy s vysokou úspešnosťou (header/footer) majú prednosť pred pomalými s nízkou úspešnosťou (fragmentácia)
- **Forenzná integrita:** Oprava len rekonštruuje existujúce dáta, nepridáva nové (žiadne AI inpainting)
- **Dokumentácia:** Jasné zaznamenanie použitých metód a výsledkov pre klienta

## Jak na to

1. **Analýza poškodených súborov** - Načítaj corrupted súbory z validation/corrupted/ (z kroku 15). Analyzuj JPEG štruktúru každého súboru: SOI marker (FF D8), EOI marker (FF D9), segmenty (APP0, APP1, DQT, SOF, SOS). Diagnostikuj typ: invalid_header, missing_footer, truncated_file, invalid_segment. Kategorizuj opraviteľnosť: high (>80%), medium (50-80%), low (<50%). Vytvor corruption_analysis.json.

2. **Oprava invalid header** - Pre súbory s corrupt headerom: nahraď prvé 3 bytes validným SOI (FF D8 FF). Rekonštruuj JFIF APP0 segment. Nájdi Start of Scan (FF DA), zlepi validný header + image data od SOS. Validuj pomocou PIL verify(). Tools: Python struct, xxd/hexedit. Úspešnosť: 90-95%.

3. **Oprava missing footer** - Over že súbor nemá FF D9 na konci. Metóda 1: pridaj b'\xff\xd9'. Ak zlyhal: Metóda 2 - nájdi posledný FF marker, obreži tam, pridaj EOF. Validuj ImageMagick identify. Tools: Python file append, jpeginfo. Úspešnosť: 85-90%.

4. **Oprava invalid segments** - Parsuj segmenty, identifikuj corrupt. Zachovaj kritické (SOI, SOF, DQT, DHT, SOS, EOI), odstráň poškodené APP segmenty. Zrekonštruuj súbor. Validuj multi-tool (PIL + ImageMagick + jpeginfo). Úspešnosť: 80-85%.

5. **Oprava truncated files** - Metóda 1: PIL LOAD_TRUNCATED_IMAGES = True, load partial, save. Metóda 2: nájdi posledný validný FF marker, obreži, pridaj padding + EOF. Metóda 3: zachovaj prvých 50%, dopíš koniec. Výsledok: čiastočná fotografia. Úspešnosť: 50-70%.

6. **Validácia a organizácia** - Validuj 3 nástrojmi: PIL verify() + load(), ImageMagick identify, jpeginfo -c. Kategorizuj: fully_repaired, partially_repaired, repair_failed. Organizuj: repair/repaired/ (úspešné), repair/failed/ (neopravené). Vypočítaj štatistiky, vygeneruj repair_report.json. Update finálny počet validných: valid_before + repair_successful.

---

## Výsledek

**Repair Statistics:** Z 7 corrupt súborov pokus o opravu na 5 (2 fragmentované preskočené). Úspešne opravené: 4 (80% success rate). Breakdown: missing_footer (1/1, 100%), invalid_segment (2/2, 100%), truncated_file (1/3, 33%).

**Final Count:** Pred opravou: 236 validných (96.33%). Po oprave: 240 validných (97.96%). Improvement: +1.63pp. Neopraviteľné: 3 súbory v failed/ (nebudú odovzdané).

**Validation:** Všetky 4 opravené fully validated (PIL + ImageMagick + jpeginfo OK). Priemerný čas: 3 min/súbor. ROI: 4 fotografie za 15 minút = dobrý výsledok.

**Organization:** repair/repaired/ (4 ready for cataloging), repair/failed/ (3 unrepairable), repair/logs/corruption_analysis.json, repair/reports/repair_report.json.

## Reference

- ISO/IEC 10918-1 - JPEG Standard (ITU-T Recommendation T.81)
- JPEG File Interchange Format (JFIF) Specification v1.02
- NIST SP 800-86 - Guide to Integrating Forensic Techniques (Section 3.1.4 - Data Recovery and Repair)
- DFRWS 2007 - Automatic Reassembly of File Fragments
- Python Pillow Documentation - Error Handling and Truncated Images
- ImageMagick Command-Line Processing Reference

## Stav
K otestování

## Nález
(prázdne - vyplní sa po teste)
        
    except Exception as e:
        return False, str(e)
```

### 2. JPEG - Rekonštrukcia hlavičky
```python
def repair_jpeg_header(filepath):
    """
    Opraviť poškodenú JPEG hlavičku
    """
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        # Search for valid JPEG segments
        soi_index = data.find(b'\xff\xd8')
        
        if soi_index > 0:
            # Remove garbage before SOI
            clean_data = data[soi_index:]
            
            with open(filepath, 'wb') as f:
                f.write(clean_data)
            
            return True, "Header cleaned"
        
        return False, "No valid JPEG marker found"
        
    except Exception as e:
        return False, str(e)
```

### 3. PNG - CRC oprava
```python
def repair_png_crc(filepath):
    """
    Prepočítať a opraviť CRC checksums v PNG
    """
    try:
        import struct
        import zlib
        
        with open(filepath, 'rb') as f:
            data = bytearray(f.read())
        
        # PNG chunks start at byte 8
        pos = 8
        repaired = False
        
        while pos < len(data) - 12:
            # Read chunk length
            chunk_len = struct.unpack('>I', bytes(data[pos:pos+4]))[0]
            chunk_type = data[pos+4:pos+8]
            chunk_data = data[pos+8:pos+8+chunk_len]
            
            # Calculate correct CRC
            correct_crc = zlib.crc32(chunk_type + chunk_data) & 0xffffffff
            
            # Replace CRC
            struct.pack_into('>I', data, pos+8+chunk_len, correct_crc)
            repaired = True
            
            # Move to next chunk
            pos += 12 + chunk_len
        
        if repaired:
            with open(filepath, 'wb') as f:
                f.write(data)
            return True, "CRC checksums repaired"
        
        return False, "No repairs needed"
        
    except Exception as e:
        return False, str(e)
```

### 4. Truncated JPEG - Partial recovery
```python
def repair_truncated_jpeg(filepath):
    """
    Pokus o partial recovery pre truncated JPEG
    """
    try:
        from PIL import Image, ImageFile
        
        # Enable loading of truncated images
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        
        img = Image.open(filepath)
        img.load()
        
        # Save as new complete file
        repair_path = filepath.replace('.jpg', '_recovered.jpg')
        img.save(repair_path, 'JPEG', quality=95)
        
        # Validate
        if validate_jpeg(repair_path):
            os.replace(repair_path, filepath)
            return True, "Partial recovery successful"
        
        return False, "Validation failed"
        
    except Exception as e:
        return False, str(e)
```

## Automatizovaný repair workflow

```python
def repair_batch(files_to_repair):
    """
    Batch oprava všetkých poškodených súborov
    """
    results = []
    
    for file_info in files_to_repair:
        filepath = file_info['path']
        issue = file_info['issue']
        
        # Select repair strategy
        repair_func = select_repair_strategy(issue, filepath)
        
        if repair_func:
            success, message = repair_func(filepath)
            
            # Validate after repair
            if success:
                validation = validate_image(filepath)
                final_status = validation['status']
            else:
                final_status = 'REPAIR_FAILED'
            
            results.append({
                'file_id': file_info['file_id'],
                'filename': file_info['filename'],
                'original_issue': issue,
                'repair_attempted': True,
                'repair_success': success,
                'repair_message': message,
                'final_status': final_status
            })
        else:
            results.append({
                'file_id': file_info['file_id'],
                'filename': file_info['filename'],
                'original_issue': issue,
                'repair_attempted': False,
                'reason': 'No automated repair available'
            })
    
    return results
```

## Pokročilé manuálne nástroje

Pre prípady kde automatická oprava zlyhá:

### JPEG Recovery LAB (Windows)
- Profesionálny nástroj na JPEG recovery
- Dokáže rekonštruovať fragmentované súbory
- Podpora RAW formátov

### Stellar Repair for Photo
- Multi-formát support
- Batch repair
- Preview pred uložením

### VG JPEG Repair Online
- Online nástroj
- Bezplatný pre menšie súbory

### ImageMagick
```bash
# Convert a pokus o repair
convert corrupt.jpg -strip repaired.jpg
```

## Výstupný report

```json
{
  "case_id": "2026-01-21-001",
  "repair_summary": {
    "total_attempted": 50,
    "successful_repairs": 38,
    "failed_repairs": 12,
    "success_rate": 0.76
  },
  "repairs": [
    {
      "file_id": 87,
      "filename": "f12345678.jpg",
      "original_issue": "Missing JPEG footer",
      "repair_success": true,
      "final_status": "VALID"
    },
    {
      "file_id": 143,
      "filename": "IMG_0542.jpg",
      "original_issue": "Truncated file",
      "repair_success": false,
      "recommendation": "Try JPEG Recovery LAB for advanced repair"
    }
  ],
  "unrecoverable_files": [
    {
      "file_id": 256,
      "filename": "f87654321.jpg",
      "reason": "Too much data corruption"
    }
  ],
  "timestamp": "2026-01-21T20:30:00Z"
}
```

## Štatistiky úspešnosti

```json
{
  "repair_statistics": {
    "by_issue_type": {
      "missing_footer": {
        "attempted": 15,
        "successful": 15,
        "success_rate": 1.0
      },
      "truncated": {
        "attempted": 20,
        "successful": 14,
        "success_rate": 0.7
      },
      "header_corruption": {
        "attempted": 10,
        "successful": 6,
        "success_rate": 0.6
      },
      "severe_corruption": {
        "attempted": 5,
        "successful": 0,
        "success_rate": 0.0
      }
    }
  }
}
```

## Manuálny postup pre zlyhané opravy

### Formulár pre manuálnu opravu
1. **Súbor:** `IMG_0542.jpg`
2. **Problém:** Truncated, severe corruption
3. **Odporúčaný nástroj:** JPEG Recovery LAB
4. **Postup:**
   - Import súboru do nástroja
   - Analýza poškodenia
   - Manual reconstruction
   - Export opraveného súboru

5. **Výsledok:** [ ] Úspešná oprava [ ] Neúspešná

## Poznámky
- Nie všetky súbory sa dajú opraviť
- Automatická oprava funguje pre ~70-80% prípadov
- Komplexné poškodenia vyžadujú manuálny zásah
- Dokumentovať všetky pokusy o opravu
