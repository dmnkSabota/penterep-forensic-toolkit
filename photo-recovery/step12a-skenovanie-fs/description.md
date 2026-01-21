# Detaily testu

## Úkol

Využiť funkčný súborový systém na identifikáciu a obnovu všetkých obrazových súborov (aktívnych aj vymazaných) so zachovaním pôvodných názvov, adresárovej štruktúry a metadát.

## Obtiažnosť

Střední

## Časová náročnosť

60

## Automatický test

Áno - Python skript s The Sleuth Kit (fls + icat) automaticky naskenuje FS (rekurzívne listing), vyfiltruje obrazové súbory, extrahuje ich pomocou inode a zachová originálnu štruktúru

## Popis

File System-Based Recovery je preferovaná stratégia obnovy, pretože využíva informácie zo súborového systému samotného. Keď sa súbor vymaže, obsah zostane na disku, len sa označí priestor ako "voľný". Metadata súboru (meno, veľkosť, pozícia) zostanú v adresárovom zázname.

Prečo je tento krok kritický:
- Zachová pôvodné názvy súborov (IMG_0001.JPG, DSC_0145.JPG)
- Zachová adresárovú štruktúru (DCIM/100CANON/, DCIM/101CANON/)
- Zachová časové značky (Created, Modified, Accessed)
- Zachová všetky EXIF metadáta a atribúty súborov
- Zachová poradie súborov
- Rýchlejšia než file carving (30 min - 2 hod vs 2-8 hod)
- Môže obnoviť čiastočne prepísané súbory

Princíp: pomocou fls prečítame zoznam všetkých súborov vrátane vymazaných (značených * v listingu), vyfiltrujeme obrazové formáty (jpg, png, tiff, raw), pomocou icat extrahujeme obsah podľa inode/metadata adresy. Fungovanie závisí od toho, či metadata sú intaktné.

## Jak na to

1. SKENOVANIE - spusti fls -r -d -p s offsetom partície (z kroku 10) na rekurzívne získanie kompletného file listingu vrátane vymazaných súborov (označené *)
2. FILTROVANIE - z listingu vyfiltruj obrazové súbory pomocou regex na prípony (jpg|jpeg|png|tif|tiff|gif|bmp|raw|cr2|nef|arw|dng|heic), rozdeľ na aktívne a vymazané
3. EXTRAKCIA - pre každý súbor: parse inode z listingu (formát: r/r 123: /path/file.jpg), spusti icat s inode číslom, ulož do cieľového adresára so zachovaním pôvodnej cesty
4. VALIDÁCIA - skontroluj extrahované súbory pomocou file command a ImageMagick identify, roztried do valid/corrupted/invalid, vymaž prázdne a neplatné
5. METADATA - pre každý validný súbor: extrahuj FS metadata (timestamps, size, atribúty), extrahuj EXIF pomocou exiftool, ulož do metadata katalógu (JSON)
6. ORGANIZÁCIA - zachovaj pôvodnú adresárovú štruktúru, vytvor podsložky active/ a deleted/, ulož štatistiky (počet nájdených, extrahovaných, validných, s EXIF)

---

## Výsledek

Kolekcia obnovených súborov s pôvodnými názvami a adresárovou štruktúrou. Aktívne súbory v active/, vymazané v deleted/, poškodené v corrupted/. Úspešnosť typicky >95% pre aktívne súbory, 70-90% pre vymazané (závisí od prepísania). Štatistiky: celkový počet záznamov FS, aktívne vs vymazané, obrazové súbory nájdené, úspešne extrahované, validné, s EXIF metadátami. Metadata katalóg obsahuje FS timestamps a EXIF pre ďalšiu analýzu. Zachované: názvy, štruktúra, timestamps, EXIF, atribúty.

## Reference

ISO/IEC 27037:2012 - Section 7.3 (Data Extraction)
NIST SP 800-86 - Section 3.1.2.2 (File System Recovery)
The Sleuth Kit Documentation (fls, icat)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)
        if entry.info.meta.flags == pytsk3.TSK_FS_META_FLAG_UNALLOC:
            # Vymazaný súbor
            if is_image_file(entry.info.name.name):
                recovered.append({
                    'inode': entry.info.meta.addr,
                    'name': entry.info.name.name,
                    'size': entry.info.meta.size,
                    'mtime': entry.info.meta.mtime
                })
    
    return recovered
```

## Automatizovaný skript vykoná

### 1. Skenovanie vymazaných súborov
```python
def scan_deleted_files(image_path, fs_offset):
    # fls na získanie zoznamu
    cmd = ['fls', '-r', '-d', '-o', str(fs_offset), image_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parsovanie výstupu
    deleted_files = parse_fls_output(result.stdout)
    
    # Filter na image súbory
    photos = filter_image_files(deleted_files)
    return photos
```

### 2. Extrakcia obnoviteľných fotografií
```python
def extract_photos(image_path, fs_offset, photos, output_dir):
    for photo in photos:
        # icat na extrakciu
        output_path = os.path.join(output_dir, photo['name'])
        cmd = ['icat', '-o', str(fs_offset), image_path, str(photo['inode'])]
        
        with open(output_path, 'wb') as f:
            subprocess.run(cmd, stdout=f)
        
        # Zachovať metadata
        os.utime(output_path, (photo['atime'], photo['mtime']))
```

## Filtrovanie image súborov
Podporované formáty:
- **JPEG:** `.jpg`, `.jpeg`
- **PNG:** `.png`
- **TIFF:** `.tif`, `.tiff`
- **RAW:** `.cr2`, `.nef`, `.arw`, `.dng`
- **BMP:** `.bmp`
- **GIF:** `.gif`
- **HEIC:** `.heic`, `.heif`

```python
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', 
                   '.cr2', '.nef', '.arw', '.dng', '.bmp', 
                   '.gif', '.heic', '.heif'}

def is_image_file(filename):
    ext = os.path.splitext(filename.lower())[1]
    return ext in IMAGE_EXTENSIONS
```

## Výstupný report
```json
{
  "case_id": "2026-01-21-001",
  "method": "filesystem_scan",
  "total_deleted_files": 1547,
  "image_files_found": 342,
  "recovered_photos": [
    {
      "inode": 12845,
      "original_name": "IMG_20250115_143022.jpg",
      "size_bytes": 2458624,
      "deleted_date": "2026-01-18T10:34:12Z",
      "recovery_status": "success",
      "output_path": "/case/recovered/IMG_20250115_143022.jpg"
    }
  ],
  "recovery_timestamp": "2026-01-21T16:45:00Z",
  "success_rate": 0.94
}
```

## Výhody metódy
✅ Zachované pôvodné názvy súborov  
✅ Zachovaná adresárová štruktúra  
✅ Dostupné FS metadata (dátumy vytvorenia/modifikácie)  
✅ Rýchlejšie ako carving  
✅ Presnejšia identifikácia súborov  

## Limitácie
⚠️ Funguje len ak FS je rozpoznaný  
⚠️ Vymazané súbory môžu byť čiastočne prepísané  
⚠️ TRIM (SSD) môže fyzicky odstrániť dáta  

## Poznámky
- Niektoré súbory môžu byť fragmentované
- FAT32: limitovaná fragmentácia
- NTFS: MFT obsahuje rozsiahle metadata
- ext4: extent-based alokácia
