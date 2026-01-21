# Detaily testu

## Úkol

Obnoviť obrazové súbory priamym vyhľadávaním byte signatúr (magic bytes) v raw dátach forenzného obrazu bez závislosti na súborovom systéme.

## Obtiažnosť

Střední

## Časová náročnosť

240

## Automatický test

Áno - Python skript s Scalpel a PhotoRec automaticky vyhľadá byte signatúry (JPEG FF D8 FF, PNG 89 50 4E 47), extrahuje súbory, validuje ich a odstráni duplikáty

## Popis

File Carving je technika obnovy dát, ktorá ignoruje súborový systém a namiesto toho hľadá priamo byte signatúry súborov v raw dátach média. Každý typ súboru má charakteristické signatúry - JPEG začína FF D8 FF a končí FF D9, PNG začína 89 50 4E 47.

Prečo je tento krok kritický:
- Funguje aj bez súborového systému (naformátované, poškodené, nerozpoznané)
- Dokáže nájsť súbory, ktoré FS-based recovery nevidí
- Môže obnoviť čiastočne prepísané súbory
- EXIF metadáta zostávajú zachované (sú embedded v súboroch)
- Stratia sa pôvodné názvy súborov (generujú sa nové: 00000001.jpg)
- Stratí sa adresárová štruktúra a časové značky súborového systému
- Veľmi pomalý proces (2-8 hodín na 64GB médium)

Používame dva nástroje: Scalpel (rýchlejší, presnejší) a PhotoRec (pomalší, nájde viac súborov, lepší pre fragmenty). Carved súbory musia byť validované (ImageMagick identify) a deduplikované (SHA-256 hash).

## Jak na to

1. KONFIGURÁCIA - vytvor Scalpel config súbor s byte signatúrami pre JPEG (\xff\xd8\xff\xe0 až \xff\xd9), PNG (\x89PNG až \xae\x42\x60\x82), TIFF, GIF, RAW formáty
2. SCALPEL CARVING - spusti scalpel -c config.conf -o output/ image.dd, čakaj 2-4 hodiny, parse audit.txt pre počet obnovených súborov
3. PHOTOREC CARVING - spusti photorec /log /d output/ /cmd image.dd search v paranoid režime, čakaj 2-6 hodín, spočítaj súbory v recup_dir.*
4. VALIDÁCIA - skontroluj každý carved súbor pomocou file command a ImageMagick identify, roztrieď do valid/corrupted/invalid adresárov
5. DEDUPLIKÁCIA - vypočítaj SHA-256 hash pre každý validný súbor, odstráň duplikáty (Scalpel a PhotoRec nájdu tie isté súbory)
6. ORGANIZÁCIA - roztrieď finálne súbory podľa typu do adresárov (jpg/, png/, tiff/, raw/), premenuj systematicky (CASEID_jpg_000001.jpg), vytvor JSON katalóg

---

## Výsledek

Kolekcia obnovených obrazových súborov s automaticky generovanými názvami. Zachované: EXIF metadáta a obsah fotografií. Stratené: pôvodné názvy, adresárová štruktúra, časové značky FS. Štatistiky: počet carved súborov (raw), validných po kontrole, unikátnych po deduplikácii, úspešnosť validácie (cieľ >70%). Typicky 20-30% duplikátov medzi Scalpel a PhotoRec. Report obsahuje trvanie jednotlivých fáz, porovnanie nástrojov a katalóg súborov.

## Reference

NIST SP 800-86 - Section 3.1.2.3 (Data Carving)
Brian Carrier: File System Forensic Analysis - Chapter 14
Scalpel Documentation

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)

### 3. Foremost
```bash
foremost -t jpg,png,tif -o /case/recovered -i evidence.dd
```

## Automatizovaný skript vykoná

### 1. Príprava konfigurácie
```python
def prepare_carving_config(output_dir):
    config = {
        'tool': 'photorec',
        'image_formats': ['jpg', 'png', 'tiff', 'cr2', 'nef', 'arw'],
        'output_dir': output_dir,
        'max_file_size': 50 * 1024 * 1024,  # 50MB
    }
    return config
```

### 2. Spustenie PhotoRec
```python
def run_photorec(image_path, output_dir, formats):
    cmd = ['photorec', '/d', output_dir, '/cmd', image_path]
    
    # Zakázať všetky formáty
    cmd.append('fileopt,everything,disable')
    
    # Povoliť len image formáty
    for fmt in formats:
        cmd.append(f'fileopt,{fmt},enable')
    
    cmd.append('search')
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return parse_photorec_output(result.stdout)
```

### 3. Post-processing obnovených súborov
```python
def postprocess_carved_files(output_dir):
    recovered = []
    
    for filename in os.listdir(output_dir):
        filepath = os.path.join(output_dir, filename)
        
        # Validácia integrity
        if is_valid_image(filepath):
            file_info = {
                'filename': filename,
                'size': os.path.getsize(filepath),
                'hash': calculate_hash(filepath),
                'format': identify_format(filepath)
            }
            recovered.append(file_info)
        else:
            # Presunúť nevalidné do quarantine
            move_to_quarantine(filepath)
    
    return recovered
```

## Signature Database

### JPEG
```
Header: FF D8 FF E0 (JFIF)
        FF D8 FF E1 (EXIF)
Footer: FF D9
```

### PNG
```
Header: 89 50 4E 47 0D 0A 1A 0A
Footer: 49 45 4E 44 AE 42 60 82
```

### TIFF
```
Header: 49 49 2A 00 (little-endian)
        4D 4D 00 2A (big-endian)
```

### Canon CR2 (RAW)
```
Header: 49 49 2A 00 10 00 00 00 43 52
```

## Výstupný report
```json
{
  "case_id": "2026-01-21-001",
  "method": "file_carving",
  "tool": "photorec",
  "statistics": {
    "data_scanned_bytes": 32212254720,
    "files_carved": 487,
    "valid_images": 398,
    "corrupted_images": 89,
    "formats": {
      "jpg": 324,
      "png": 52,
      "tiff": 18,
      "cr2": 4
    }
  },
  "output_directory": "/case/recovered/carved",
  "execution_time_seconds": 5432,
  "timestamp": "2026-01-21T18:12:00Z"
}
```

## Výhody metódy
✅ Funguje aj keď je FS úplne zničený  
✅ Dokáže obnoviť súbory aj po formátovaní  
✅ Nezávislá od typu súborového systému  
✅ Dokáže obnoviť fragmentované súbory (čiastočne)  

## Nevýhody
❌ Obnovené súbory nemajú pôvodné názvy  
❌ Stratená adresárová štruktúra  
❌ Žiadne FS metadata (dátumy)  
❌ Pomalší proces  
❌ Vyššia miera false positives  

## Špeciálne prípady

### Fragmentované súbory
- PhotoRec má obmedzenú schopnosť rekonštrukcie
- Pre JPEG: často úspešné (header + data + footer)
- Pre RAW: zložitejšie (komplexná štruktúra)

### Prepísané dáta
- Ak boli sektory prepísané, súbor je neobnoviteľný
- Čiastočná obnova môže fungovať pre JPEG (progressive)

## Poznámky
- Proces môže trvať hodiny pre veľké médiá
- Odporúčané kombinovať s krokom 12A (ak je možné)
- Validácia obnovených súborov je kritická (krok 15)
