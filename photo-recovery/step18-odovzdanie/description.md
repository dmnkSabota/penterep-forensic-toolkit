# Detaily testu

## Úkol

Odovzdať všetky výsledky klientovi, uzavrieť CoC a finalizovať prípad.

## Obtiažnosť

Stredná

## Časová náročnosť

90 minút

## Automatický test

Nie

## Popis

Odovzdanie klientovi je záverečný krok celého procesu obnovy fotografií. Zahŕňa prípravu záverečného balíka, kontaktovanie klienta, samotné odovzdanie (osobne, kuriérom alebo online), uzavretie CoC, získanie spätnej väzby a archiváciu prípadu.

Tento krok predstavuje zámerné ukončenie automatizácie. Fyzické odovzdanie dôkazového materiálu s overením totožnosti, získanie podpisov a uzavretie CoC sú právne úkony vyžadujúce ľudskú zodpovednosť, ktoré nie je možné nahradiť softvérom.

Vstupom sú výstupy z predchádzajúcich krokov: adresár s katalógom fotografií, záverečná správa, README a kontrolný zoznam odovzdania. Analytik vykonáva celý proces manuálne podľa nižšie uvedeného postupu.

## Jak na to

**1. Príprava záverečného balíka:**

Skopíruj katalóg fotografií a záverečnú správu. Vytvor súbor `MANIFEST.json` so zoznamom všetkých súborov a ich SHA-256 kontrolnými súčtami. Over integritu HTML katalógu manuálnym otvorením v prehliadači. Voliteľne skomprimuj celý balík do ZIP archívu.

**2. Kontaktovanie klienta:**

Vygeneruj informačný e-mail s počtom obnovených fotografií, hodnotením kvality obnovy a možnosťami odovzdania. Odpoveď sa očakáva do 24 hodín, opätovný kontakt po 3 dňoch bez reakcie.

**3. Samotné odovzdanie:**

Pri osobnom odovzdaní: over totožnosť klienta, odovzdaj balík aj pôvodné médium, vysvetli použitie katalógu a získaj podpis protokolu. Pri kuriérskej preprave: dvojité balenie, poistenie zásielky, sledovanie, podpis pri prevzatí. Pri elektronickom odovzdaní: zabezpečený odkaz s heslom zaslaným samostatnou cestou, platnosť 7 dní, kontrolné súčty pre overenie integrity, pôvodné médium kuriérom.

**4. Uzavretie CoC:**

Pridaj záverečný záznam „vrátené klientovi", získaj podpisy všetkých strán, over úplnosť záznamu bez medzier, vygeneruj PDF dokumentáciu CoC a nastav stav prípadu na `UZAVRETÝ`. Pôvodné médium je vrátené klientovi, forenzná kópia je archivovaná.

**5. Spätná väzba od klienta:**

Odošli dotazník spokojnosti 24–48 hodín po odovzdaní: 5 otázok (kvalita obnovy 1–5, počet fotografií 1–5, komunikácia 1–5, odporučenie áno/nie, návrhy na zlepšenie). Cieľ: priemerné hodnotenie 4.5 z 5.0. Na základe výsledkov požiadaj o zákaznícke hodnotenie.

**6. Uzavretie prípadu:**

Vytvor záverečnú správu o priebehu prípadu (časová os, výsledky, hodnotenie spokojnosti). Archivuj všetky súbory s retenčnou lehotou 7 rokov v zmysle GDPR čl. 30. Aktualizuj stav prípadu v databáze na `UZAVRETÝ` a zaznamenaj súhrn priebehu vrátane ponaučení pre budúce prípady.

## Výsledek

Záverečný balík pre klienta obsahuje: katalóg fotografií s interaktívnym HTML prehľadom, záverečnú technickú správu, pokyny pre klienta a súbor `MANIFEST.json` s SHA-256 kontrolnými súčtami všetkých odovzdaných súborov.

Dokumentácia: informačný e-mail odoslaný, odovzdávací protokol podpísaný oboma stranami, CoC má stav `UZAVRETÝ` bez medzier v zázname, kompletný auditný záznam je uložený.

Archivácia prípadu: všetky súbory archivované s retenčnou lehotou 7 rokov, šifrované AES-256, stav v databáze `UZAVRETÝ`.

Fyzické odovzdanie a podpisy: mimo rozsah automatizácie – realizované manuálne analytikom.

## Reference

ISO/IEC 27037:2012 – Uchovávanie digitálnych dôkazov
NIST SP 800-86 – Section 3.4 (Reporting)
ACPO Good Practice Guide – Principle 4 (Documentation)
ISO 9001:2015 – Spokojnosť zákazníka
GDPR čl. 30 – Záznamy o spracovateľských činnostiach

## Stav

Manuálny proces – netestovateľný automaticky

## Nález

Záverečný balík bol pripravený: katalóg fotografií, záverečná správa, pokyny pre klienta a súbor `MANIFEST.json` s SHA-256 kontrolnými súčtami všetkých odovzdaných súborov. Informačný e-mail a šablóna odovzdávacieho protokolu s podpisovými blokmi boli vygenerované. Dotazník spokojnosti obsahuje 5 otázok s cieľom 4.5+/5.0. Všetky dokumenty spĺňajú požiadavky ISO/IEC 27037:2012 a GDPR čl. 30. CoC stav: UZAVRETÝ. Fyzické odovzdanie a podpisy: mimo rozsah automatizácie.