# Detaily testu

## Úkol

Vypočítať SHA-256 hash vytvoreného forenzného obrazu a porovnať so source_hash z imaging procesu pre matematické overenie integrity.

## Obtiažnosť

Jednoduchá

## Časová náročnosť

45 minút

## Automatický test

Áno

## Popis

Overenie integrity je druhá a finálna fáza dvojfázového procesu zabezpečenia integrity forenzných dát. Krok 5 vypočítal source_hash priamo z originálneho média počas imaging procesu. Tento krok vypočíta image_hash zo súboru forenzného obrazu uloženého na disku a porovná obe hodnoty. Zhoda hashov matematicky dokazuje, že súbor obrazu je bit-for-bit identický s dátami prečítanými z originálneho média.

Výpočet image_hash prebieha čítaním súboru obrazu z cieľového disku – nie z originálneho média. Toto je rýchlejšie a nespôsobuje žiadne dodatočné opotrebenie poškodeného originálu.

Pri úspešnej verifikácii (MATCH) je možné originálne médium bezpečne odpojiť od write-blockera a všetky ďalšie analýzy sa vykonávajú výhradne na overenom obraze. Pri nezhode (MISMATCH) je imaging proces nutné zopakovať.

## Jak na to

**1. Načítanie source_hash z Kroku 5:**

Systém automaticky načíta source_hash zo súboru `{case_id}_imaging.json`. Overte, že source_hash je kompletný 64-znakový hexadecimálny reťazec. Ak chýba alebo je neplatný, Krok 5 nebol dokončený správne.

**2. Lokalizácia forenzného obrazu:**

Systém automaticky nájde súbor obrazu v output adresári – podporované formáty sú `.dd`, `.raw` a `.E01`. Overte veľkosť súboru – musí zodpovedať kapacite originálneho média.

**3. Výpočet image_hash:**

Pre RAW obrazy (`.dd`, `.raw`) systém vypočíta SHA-256 hash pomocou Python hashlib v 4 MB blokoch s priebežným zobrazovaním postupu. Pre E01 obrazy použije `ewfverify`, ktorý zároveň overí integritu E01 kontajnera (CRC kontroly segmentov).

**4. Porovnanie hashov a aktualizácia CoC:**

Systém automaticky porovná source_hash a image_hash. Hashe musia byť úplne identické vo všetkých 64 znakoch. Pri MATCH aktualizujte Chain of Custody log o záznam úspešnej verifikácie a odpojte originálne médium. Pri MISMATCH vytvorte incident report, zastavte analýzu a opakujte Krok 5.

**5. Archivácia verification reportu:**

Uložte do Case dokumentácie:
- `{case_id}_verification.json` – výsledok verifikácie s oboma hashmi
- `{case_id}_image.sha256` – image_hash v štandardnom formáte

## Výsledek

SHA-256 image_hash vypočítaný a porovnaný so source_hash z Kroku 5. Pri MATCH workflow pokračuje do Kroku 7 – originálne médium je bezpečne odpojené a archivované, všetky ďalšie analýzy prebiehajú na overenom obraze. CoC log aktualizovaný o záznam verifikácie. Verification report archivovaný v Case dokumentácii. Pri MISMATCH incident report vytvorený, analýza zastavená, Krok 5 sa opakuje.

## Reference

NIST SP 800-86 – Section 3.1.2 (Examination Phase – Data Integrity Verification)
ISO/IEC 27037:2012 – Section 7.2 (Verification of integrity of digital evidence)
NIST FIPS 180-4 – Secure Hash Standard (SHA-256 algorithm)
RFC 6234 – US Secure Hash Algorithms

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Teoretická časť (Kapitola 3.3.2, Krok 6) pokrýva verifikáciu integrity porovnaním hashov.

Implementácia rozširuje tento krok o:

Automatické načítanie source_hash z JSON reportu Kroku 5 – eliminácia manuálneho zadávania. Validácia formátu hash hodnoty pred porovnaním – 64 hexadecimálnych znakov. Podpora viacerých formátov obrazov (RAW a E01) s odlišnými metódami výpočtu. Priebežné zobrazovanie postupu pri výpočte hashu pre veľké obrazy.

Tento krok implementuje optimalizovaný dvojfázový prístup ku overeniu integrity: source_hash sa vypočíta raz počas imagingu (Krok 5, dc3dd s integrovaným hashovaním), image_hash sa vypočíta z obrazu na disku (tento krok). Výsledkom je jedno čítanie originálneho média namiesto dvoch, čo je kritické pri práci s poškodeným alebo degradujúcim hardvérom. Táto optimalizácia spĺňa požiadavky NIST SP 800-86 a ISO/IEC 27037:2012.