# Detaily testu

## Úkol

Vykonať fyzickú opravu poškodeného média.

## Obtiažnosť

Střední

## Časová náročnosť

60

## Automatický test

Nie

## Popis

Fyzická oprava je proces, pri ktorom sa pokúšame obnoviť funkčnosť poškodeného úložného média natoľko, aby bolo možné z neho vytvoriť forenzný obraz. Tento krok je aktivovaný iba vtedy, keď test čítateľnosti (Krok 3) určí stav média ako UNREADABLE. Nesprávny zásah môže nenávratne zničiť dáta, preto každá oprava mení fyzický stav dôkazu a musí byť kompletne zdokumentovaná pre Chain of Custody. Niektoré opravy sú nezvratné a úspešnosť nie je garantovaná - pred začatím je nutné získať informovaný písomný súhlas klienta s opravou a zdokumentovať pôvodný stav média.

## Jak na to

Získajte informovaný súhlas klienta s fyzickou opravou média. Pripravte formulár s jasným popisom rizík - oprava môže nenávratne zničiť zostávajúce dáta, nie je garantovaný úspech, a niektoré zásahy sú nezvratné. Nechajte klienta podpísať súhlasný dokument pred akýmkoľvek fyzickým zásahom.

Vytvorte komplexnú fotodokumentáciu PRED opravou. Minimálne tri fotografie sú povinné: celkový záber média s mierkou, detailný záber oblasti plánovanej opravy (napríklad poškodený konektor alebo prasklina), a fotografia pripravených nástrojov a pracoviska. Tieto fotografie slúžia ako baseline pre porovnanie po oprave.

Klasifikujte typ potrebnej opravy do jednej z troch kategórií. Jednoduchá oprava zahŕňa čistenie kontaktov izopropylalkoholom, vyrovnanie ohnutých pinov konektora pinzetou, alebo odstránenie prachu z konektorov. Stredná oprava zahŕňa výmenu USB konektora spájkovaním, odstránenie korózie z kontaktov skalpelom, alebo opravu zlomeného púzdra epoxidovým lepidlom. Komplexná oprava zahŕňa chip-off techniku (odpájanie pamäťového čipu z PCB), opravu prasklej PCB vodivým lepidlom, alebo prenos čipu na donorovú PCB - tieto opravy vyžadujú mikroskop a špecializované vybavenie.

Vykonajte opravu podľa zvolenej klasifikácie. Pri každom kroku opravy vytvorte fotografiu dokumentujúcu aktuálny stav. Napríklad pri výmene konektora: foto pred odpájkovaním starého konektora, foto po odstránení starého konektora s viditeľnými pad-mi na PCB, foto nového konektora počas spájkovania, a foto po dokončení spájkovania. Používajte vhodné nástroje - antištatickú pinzetu, mikroskop pre SMD komponenty, teplotne kontrolovanú spájkovačku (maximálne 350°C pre prevencia poškodenia čipov).

Vytvorte fotodokumentáciu PO oprave. Odfotografujte médium v rovnakých záberoch ako pred opravou - celkový záber, detail opravovanej oblasti, a pracovisko. Táto symetria umožňuje priame porovnanie before/after stavu.

Pripojte opravené médium cez write-blocker a spustite Readability Test (Krok 3) pre overenie, či oprava bola úspešná. Na základe výsledku testu pokračujte: ak test vráti READABLE alebo PARTIAL, pokračujte Krokom 5 (Vytvorenie forenzného obrazu). Ak test opäť vráti UNREADABLE, máte dve možnosti - vykonať jeden ďalší pokus o opravu s inou metódou, alebo kontaktovať klienta s odporúčaním zaslania média do špecializovaného data recovery laboratória s cleanroom vybavením.

Vygenerujte repair report obsahujúci before/after fotografie, step-by-step popis vykonaných operácií s časovými značkami, použité nástroje a materiály, výsledok readability testu po oprave, a odporúčanie ďalšieho postupu. Archivujte report do Case dokumentácie.

## Výsledek

Oprava vykonaná a zdokumentovaná. Pri úspešnej oprave (Readability Test vrátil READABLE alebo PARTIAL) workflow pokračuje Krokom 5 (Vytvorenie forenzného obrazu). Pri neúspešnej oprave (Readability Test stále vracia UNREADABLE) kontaktujte klienta s možnosťami: ďalší pokus o opravu inou metódou, alebo zaslanie do špecializovaného laboratória. Vygenerovaný repair report (PDF) s kompletnou fotodokumentáciou before/after, detailným popisom vykonaných krokov, a výsledkom readability testu.

## Reference

ISO/IEC 27037:2012 - Section 6.3.3 (Handling damaged devices)
NIST SP 800-86 - Section 3.1.1.4 (Special Considerations)
ACPO Good Practice Guide - Principle 2 (Competence)

## Stav

K otestování

## Nález

(prázdne - vyplní sa po teste)