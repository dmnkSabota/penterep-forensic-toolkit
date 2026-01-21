# Detaily testu

## Úkol

Konsolidovať výstupy z krokov 12A (FS-based recovery) a/alebo 12B (file carving) do jedného organizovaného datasetu obnovených fotografií s master katalógom.

## Obtiažnosť

Snadné

## Časová náročnosť

30

## Automatický test

Áno - Python skript automaticky zbiera súbory z oboch metód obnovy, vypočíta SHA-256 hashe, odstráni duplikáty a vytvorí konsolidovaný katalóg

## Popis

Extrakcia a konsolidácia je proces zjednotenia výsledkov z rôznych metód obnovy do jedného organizovaného datasetu. V závislosti od rozhodnutia v kroku 11 máme výstupy buď z kroku 12A (FS-based), alebo z kroku 12B (file carving), alebo z oboch (hybridná stratégia).

Prečo je tento krok kritický:
- Zjednotenie výsledkov z rôznych metód do jedného miesta
- Odstránenie duplikátov (FS-based a carving môžu nájsť tie isté súbory)
- Vytvorenie master katalógu so všetkými metadátami
- Štandardizácia názvov a organizácie súborov
- Príprava pre ďalšie kroky (EXIF analýza, validácia)
- Štatistiky: koľko súborov z každej metódy, koľko duplikátov

V prípade hybridnej stratégie: súbory z FS-based majú prioritu (zachované názvy a metadáta), carved súbory dopĺňajú čo FS-based nenašlo. Finálna štruktúra: recovered_photos/ s podnoresármi podľa zdroja a typu.

## Jak na to

1. ZBER ZDROJOV - identifikuj ktoré adresáre existujú (fs_recovered/ z kroku 12A, carved/ z kroku 12B), naskenuj všetky obrazové súbory v každom zdroji
2. INVENTARIZÁCIA - pre každý súbor: vypočítaj SHA-256 hash, zisti veľkosť, typ (MIME), zaznamenaj zdroj (fs_based alebo file_carving)
3. DETEKCIA DUPLIKÁTOV - porovnaj hashe medzi zdrojmi, ak hash existuje v oboch → je to duplikát, označ ktorý zachovať (fs_based má prioritu)
4. KOPÍROVANIE - skopíruj všetky unikátne súbory do recovered_photos/, zachovaj pôvodný názov ak je z FS-based, použi hash-based názov ak je carved
5. ORGANIZÁCIA - vytvor podadresáre: fs_based/, carved/, deduplicated/, roztrieď súbory podľa zdroja a typu (jpg/, png/, raw/)
6. KATALOGIZÁCIA - vytvor master_catalog.json s kompletným zoznamom: názov, hash, veľkosť, typ, zdroj, cesta, EXIF preview, štatistiky (total, z FS, z carving, duplikáty)

---

## Výsledek

Konsolidovaný dataset obnovených fotografií v štruktúrovanej adresárovej organizácii. Master katalóg (JSON) obsahuje kompletný inventár všetkých súborov s metadátami. Štatistiky: celkový počet obnovených, z FS-based recovery, z file carving, počet odstránených duplikátov. Pri hybridnej stratégii typicky 15-25% duplikátov. Súbory pripravené pre ďalšie kroky - EXIF analýza a validácia integrity.

## Reference

ISO/IEC 27037:2012 - Section 7.3 (Data consolidation)
NIST SP 800-86 - Section 3.1.3 (Analysis)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)

### 2. Deduplication
```python
def deduplicate_files(sources):
    """
    Odstránenie duplikátov na základe SHA-256 hashu
    """
    unique_files = {}
    duplicates = []
    
    for source in sources:
        for file_info in source['files']:
            file_hash = calculate_hash(file_info['path'])
            
            if file_hash not in unique_files:
                unique_files[file_hash] = {
                    'hash': file_hash,
                    'path': file_info['path'],
                    'method': source['method'],
                    'size': file_info['size']
                }
            else:
                duplicates.append({
                    'duplicate_of': unique_files[file_hash]['path'],
                    'duplicate_path': file_info['path']
                })
    
    return list(unique_files.values()), duplicates
```

### 3. Organizácia súborov
```python
def organize_files(files, output_dir):
    """
    Organizácia do štruktúry:
    /case/ID/consolidated/
        ├── with_metadata/      # Z FS recovery
        ├── carved/             # Z carving
        └── duplicates/         # Duplikáty
    """
    for file_info in files:
        if file_info['method'] == 'filesystem_scan':
            dest_dir = os.path.join(output_dir, 'with_metadata')
        else:
            dest_dir = os.path.join(output_dir, 'carved')
        
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(file_info['path'], dest_dir)
```

### 4. Vytvorenie master katalógu
```python
def create_master_catalog(files, case_id):
    catalog = {
        'case_id': case_id,
        'total_files': len(files),
        'files': []
    }
    
    for idx, file_info in enumerate(files, 1):
        entry = {
            'id': idx,
            'filename': os.path.basename(file_info['path']),
            'path': file_info['path'],
            'size_bytes': file_info['size'],
            'hash_sha256': file_info['hash'],
            'recovery_method': file_info['method'],
            'format': identify_format(file_info['path'])
        }
        catalog['files'].append(entry)
    
    return catalog
```

## Organizovaná štruktúra výstupu

```
/case/2026-01-21-001/consolidated/
├── with_metadata/
│   ├── IMG_20250115_143022.jpg
│   ├── IMG_20250116_090541.jpg
│   └── photos/
│       └── vacation_2025.jpg
├── carved/
│   ├── f12345678.jpg
│   ├── f12345679.png
│   └── f12345680.jpg
├── duplicates/
│   └── duplicate_files.txt
└── master_catalog.json
```

## Master katalóg (JSON)
```json
{
  "case_id": "2026-01-21-001",
  "total_files": 412,
  "total_size_bytes": 1247850496,
  "recovery_summary": {
    "filesystem_scan": 324,
    "file_carving": 88,
    "duplicates_removed": 15
  },
  "files": [
    {
      "id": 1,
      "filename": "IMG_20250115_143022.jpg",
      "path": "/case/.../with_metadata/IMG_20250115_143022.jpg",
      "size_bytes": 2458624,
      "hash_sha256": "a1b2c3d4...",
      "recovery_method": "filesystem_scan",
      "format": "JPEG"
    }
  ],
  "timestamp": "2026-01-21T18:45:00Z"
}
```

## Štatistický report
```json
{
  "statistics": {
    "sources": 2,
    "total_discovered": 427,
    "unique_files": 412,
    "duplicates": 15,
    "formats": {
      "jpeg": 358,
      "png": 42,
      "tiff": 10,
      "raw": 2
    },
    "size_distribution": {
      "< 1MB": 123,
      "1-5MB": 245,
      "5-10MB": 38,
      "> 10MB": 6
    }
  }
}
```

## Výhody konsolidácie
✅ Jednotný prístup k všetkým obnovným súborom  
✅ Odstránené duplikáty  
✅ Prehľadná organizácia  
✅ Pripravené pre ďalšie spracovanie (EXIF analýza)  

## Poznámky
- Deduplication šetrí miesto
- Duplikáty vznikajú keď oba kroky 12A a 12B obnovia ten istý súbor
- Master katalóg je vstup pre krok 14 (EXIF analýza)
