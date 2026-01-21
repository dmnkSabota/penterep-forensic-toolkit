# Detaily testu

## Úkol

Analyzovať forenzný obraz média a určiť typ súborového systému, jeho stav (rozpoznaný/poškodený), partície a metadáta potrebné pre výber optimálnej stratégie obnovy fotografií.

## Obtiažnosť

Snadné

## Časová náročnosť

10

## Automatický test

Áno - Python skript s The Sleuth Kit vykoná analýzu partícií (mmls), typu FS (fsstat), adresárovej štruktúry (fls) a identifikáciu obrazových súborov

## Popis

Analýza súborového systému je prvý krok forenznej analýzy, ktorý určuje, ako budeme pristupovať k obnove dát. Súborový systém je "organizačná štruktúra" média - určuje, ako sú súbory uložené, pomenované, organizované do adresárov.

Prečo je tento krok kritický:
- Určuje, ktorá stratégia obnovy bude použitá (krok 11)
- Rozpoznaný FS → môžeme použiť štruktúru adresárov (rýchlejšie, zachová názvy)
- Poškodený FS → musíme použiť file carving (pomalšie, stratia sa názvy)
- Informácie o type FS určujú kompatibilné nástroje
- Analýza partícií odhalí, či médium má viac oddielov

Analyzujeme: Partičnú tabuľku, typ súborového systému (FAT32, exFAT, NTFS, ext4...), stav FS, metadata (cluster size, kapacita), čitateľnosť adresárovej štruktúry.

## Jak na to

1. Príprava - nainštaluj The Sleuth Kit (mmls, fsstat, fls nástroje), overiť že forenzný obraz existuje a má overenú integritu
2. FÁZA 1: Analýza partícií - spusti mmls na detekciu partičnej tabuľky (DOS/MBR, GPT alebo superfloppy), urči offset primárnej partície
3. FÁZA 2: Analýza súborového systému - spusti fsstat (s offsetom ak potrebné) na detekciu typu FS a metadát (sector size, cluster size, volume label)
4. FÁZA 3: Test adresárovej štruktúry - spusti fls -r na overenie čitateľnosti adresárov, počítaj aktívne a vymazané súbory
5. FÁZA 4: Identifikácia fotografií - vyhľadaj obrazové súbory (.jpg, .png, .raw...) v directory listingu, zráta počty podľa formátov
6. FÁZA 5: Vyhodnotenie stratégie - automaticky urči odporúčanú stratégiu: FS-based recovery (ak FS rozpoznaný + adresáre čitateľné) alebo File carving (ak FS poškodený/nerozpoznaný)

---

## Výsledek

Komplexný report o stave súborového systému. Identifikovaný typ FS, stav (zdravý/poškodený), počet partícií, čitateľnosť adresárovej štruktúry, počet nájdených obrazových súborov. Automaticky určená odporúčaná stratégia obnovy a náročnosť. Pri rozpoznanom FS → Krok 11, pri nerozpoznanom → Krok 12B (File Carving).

## Reference

ISO/IEC 27037:2012 - Section 7 (Analysis)
NIST SP 800-86 - Section 3.1.2 (Examination Phase)
The Sleuth Kit Documentation

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)

### Analýza každej partície
```python
def analyze_filesystem(image_path, offset=0):
    # fsstat na analýzu FS
    cmd = ['fsstat', '-o', str(offset), image_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    fs_info = {
        'type': extract_fs_type(result.stdout),
        'state': determine_fs_state(result.stdout),
        'recognized': result.returncode == 0
    }
    return fs_info
```

## Podporované súborové systémy
- **FAT12/16/32** - najbežnejšie na USB/SD kartách
- **exFAT** - moderné flash médiá
- **NTFS** - Windows disky
- **ext2/3/4** - Linux
- **HFS+/APFS** - macOS
- **ISO 9660** - CD/DVD

## Výstupný report
```json
{
  "case_id": "2026-01-21-001",
  "image_file": "evidence.dd",
  "partitions": [
    {
      "number": 1,
      "offset": 2048,
      "size_sectors": 62521344,
      "filesystem": "FAT32",
      "state": "RECOGNIZED",
      "label": "SDCARD",
      "uuid": "1234-5678"
    }
  ],
  "analysis_timestamp": "2026-01-21T16:15:00Z",
  "recommendations": {
    "recovery_method": "filesystem_scan",
    "tool": "fls + icat"
  }
}
```

## Stavy súborového systému

### ✅ ROZPOZNANÝ (Healthy)
- FS štruktúry sú intaktné
- Možno čítať directory entries
- **Metóda obnovy:** Filesystem-based scan (krok 12A)

### ⚠️ POŠKODENÝ (Damaged)
- Niektoré štruktúry sú čitateľné
- Čiastočne funkčný FS
- **Metóda obnovy:** Kombinovaný prístup (12A + 12B)

### ❌ NEROZPOZNANÝ (Unrecognized)
- Žiadna známa FS signature
- Raw data alebo úplné premazanie
- **Metóda obnovy:** File carving (krok 12B)

## Rozhodnutie pre krok 11
Výstup tohto kroku určuje vetvenie v kroku 11:
- **Rozpoznaný FS** → Krok 12A (skenovanie FS)
- **Nerozpoznaný FS** → Krok 12B (file carving)

## Poznámky
- Niektoré média môžu mať viacero partícií
- RAID polia vyžadujú rekonštrukciu pred analýzou
- Šifrované partície (LUKS, BitLocker) vyžadujú dešifrovanie
