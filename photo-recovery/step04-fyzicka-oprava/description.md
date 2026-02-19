# Detaily testu

## Úkol

Vykonať fyzickú opravu poškodeného média.

## Obtiažnosť

Stredná

## Časová náročnosť

30–180 minút (závisí od typu opravy)

## Automatický test

Nie

## Popis

Fyzická oprava je proces, pri ktorom sa pokúšame obnoviť funkčnosť poškodeného úložného média natoľko, aby bolo možné z neho vytvoriť forenzný obraz. Tento krok je aktivovaný iba vtedy, keď test čítateľnosti (Krok 3) určí stav média ako UNREADABLE.

Každá oprava mení fyzický stav dôkazu a musí byť kompletne zdokumentovaná pre Chain of Custody. Niektoré zásahy sú nezvratné a úspešnosť nie je garantovaná – pred začatím je nutné získať písomný informovaný súhlas klienta.

## Jak na to

**1. Informovaný súhlas klienta:**

Pripravte súhlasný formulár s jasným popisom rizík: oprava môže nenávratne zničiť zostávajúce dáta, úspech nie je garantovaný, niektoré zásahy sú nezvratné. Nechajte klienta podpísať pred akýmkoľvek fyzickým zásahom. Kópiu archivujte do Case dokumentácie.

**2. Fotodokumentácia PRED opravou:**

Minimálne tri fotografie povinné: celkový záber média s mierkou, detailný záber oblasti plánovanej opravy, fotografia pripravených nástrojov a pracoviska. Tieto fotografie slúžia ako baseline pre porovnanie po oprave.

**3. Klasifikácia a vykonanie opravy:**

Zvoľte typ opravy podľa poškodenia:

- **Jednoduchá** – čistenie kontaktov izopropylalkoholom, vyrovnanie ohnutých pinov pinzetou, odstránenie prachu z konektorov
- **Stredná** – výmena USB konektora spájkovaním, odstránenie korózie skalpelom, oprava zlomeného púzdra epoxidovým lepidlom
- **Komplexná** – chip-off technika (odpájanie pamäťového čipu z PCB), oprava prasklej PCB vodivým lepidlom, prenos čipu na donorovú PCB – vyžaduje mikroskop a špecializované vybavenie

Pri každom kroku opravy vytvorte fotografiu dokumentujúcu aktuálny stav. Používajte vhodné nástroje – antištatickú pinzetu, mikroskop pre SMD komponenty, teplotne kontrolovanú spájkovačku (max. 350°C).

**4. Fotodokumentácia PO oprave:**

Odfotografujte médium v rovnakých záberoch ako pred opravou. Táto symetria umožňuje priame before/after porovnanie v dokumentácii.

**5. Overenie opravy:**

Pripojte opravené médium cez write-blocker a spustite Readability Test (Krok 3). Na základe výsledku:
- READABLE alebo PARTIAL → pokračujte Krokom 5
- UNREADABLE → jeden ďalší pokus inou metódou, alebo kontaktujte klienta s odporúčaním zaslania do špecializovaného cleanroom laboratória

**6. Aktualizácia Chain of Custody a report:**

Zaznamenajte vykonanú opravu do CoC logu – typ zásahu, dátum a čas, meno technika, výsledok. Vygenerujte repair report obsahujúci before/after fotografie, step-by-step popis operácií s časovými značkami, použité nástroje a materiály, a výsledok readability testu. Archivujte do Case dokumentácie.

## Výsledek

Oprava vykonaná a zdokumentovaná. CoC log aktualizovaný o záznam fyzického zásahu. Pri úspešnej oprave (READABLE alebo PARTIAL) workflow pokračuje Krokom 5. Pri neúspešnej oprave klient informovaný o možnostiach ďalšieho postupu. Repair report (PDF) s kompletnou before/after fotodokumentáciou archivovaný v Case.

## Reference

ISO/IEC 27037:2012 – Section 6.3.3 (Handling damaged devices)
NIST SP 800-86 – Section 3.1.1.4 (Special Considerations)
ACPO Good Practice Guide – Principle 2 (Competence)

## Stav

K otestovaniu

## Nález

(prázdne – vyplní sa po teste)

---

## Poznámky k implementácii

Teoretická časť (Kapitola 3.3.2, Krok 4) pokrýva fyzickú opravu ako jednoduchý krok s trojúrovňovou klasifikáciou. Implementácia zachováva túto klasifikáciu a dopĺňa ju o praktické prvky potrebné pre forenzné prostredie.

Informovaný súhlas klienta pred zásahom je právne nevyhnutný – bez neho je akákoľvek nezvratná oprava právne problematická. Symetrická fotodokumentácia before/after je prevzatá z ISO/IEC 27037 požiadaviek na dokumentáciu každej zmeny stavu dôkazu. Aktualizácia CoC logu po oprave uzatvára audit trail – krok 3 zaznamenal stav UNREADABLE, krok 4 musí zaznamenať čo sa s médiom stalo a kto zaň zodpovedá.