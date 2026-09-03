# Přehled změn

## 0.1.15 – 2026-09-03

- nečíselné hodnoty `NaN` vrácené EDC se již nepřenášejí do ročních součtů a neznehodnotí celý report,
- nová diagnostická entita **Stav stahování historie** viditelně ukazuje, zda doplňování nebylo spuštěno, probíhá, je pozastavené, selhalo nebo bylo dokončeno; v atributech obsahuje procenta a podrobnosti,
- nová diagnostická entita **Data EDC dostupná od** ukazuje nejstarší datum skutečně nalezené během prohledávání a ve svých atributech také stav hledání,
- automatická kontrola kompatibility nyní načítá všechny moduly integrace proti Home Assistant Core 2026.8 i 2026.9.

## 0.1.14 – 2026-09-03

- dohledávání historie nově používá pohyblivé období jednoho kalendářního roku od dne spuštění místo pevného počátečního data,
- bloky se skládají od nejnovějšího směrem dozadu; například při spuštění 3. září 2026 se samostatně ověří období 1. července až 1. srpna 2026,
- diagnostika uvádí začátek prohledávaného období i nejstarší datum skutečně nalezené v datech EDC,
- roční report nyní zobrazuje aktuální kalendářní rok od 1. ledna do posledního dostupného dne EDC; samostatný automatický report se odesílá měsíčně ve zvolený den.

## 0.1.13 – 2026-09-03

- nové tlačítko vyhledá a doplní veškerou historii, kterou EDC pro skupinu zpřístupní,
- historie se prochází zpětně v povolených blocích nejvýše 31 dní a prázdné bloky hledání nepřeruší,
- každý dokončený blok se ihned ukládá do hodinových a denních dlouhodobých statistik,
- průběh se ukládá a po restartu Home Assistantu automaticky pokračuje,
- požadavky na EDC se řadí za sebe, aby se doplňování historie nekřížilo s běžnou aktualizací nebo sestavením reportu,
- nejstarší skutečně dostupné datum se určí z vrácených dat, nikoliv z pevného předpokladu,
- atributy diagnostického senzoru ukazují stav, postup, nejstarší nalezené datum, počet importovaných hodin a dnů i případnou chybu.

## 0.1.12 – 2026-09-03

- souhrnný report se všemi čtyřmi obdobími lze nově naplánovat na každý den v nastavený čas,
- souhrnný report lze zapnout současně s libovolnou kombinací samostatného denního, týdenního, měsíčního a ročního exportu.

## 0.1.11 – 2026-09-03

- přidáno tlačítko pro okamžitý pokus o načtení dat z EDC,
- nový diagnostický senzor ukazuje čas posledního pokusu a v atributech také výsledek, poslední úspěch, další plánovaný pokus a případnou chybu,
- v nastavení integrace lze pro předmět i obsah e-mailových reportů zvolit češtinu nebo angličtinu.

## 0.1.10 – 2026-09-03

- přímo pod výběr příjemců reportů přidán postup vytvoření e-mailové `notify` entity přes integraci SMTP,
- README nyní obsahuje podrobný postup přidání jednoho i více příjemců a otestování odesílání.

## 0.1.9 – 2026-09-02

- přidány ručně spustitelné denní, týdenní, měsíční a roční reporty přes tlačítkové entity,
- souhrnné tlačítko spojí všechny čtyři periody do jediného e-mailu,
- report lze automaticky odesílat na jednu nebo více vybraných e-mailových `notify` entit,
- denní report používá poslední dostupný den EDC, týdenní poslední uzavřený týden, měsíční poslední uzavřený měsíc a roční poslední uzavřený rok,
- čas odesílání a den měsíčních/ročních reportů lze nastavit v možnostech integrace.

## 0.1.8 – 2026-09-02

- přidána samostatná diagnostická entita pro každý sdílející a cílový EAN; počet EANů není omezený a entity lze v Home Assistantu přejmenovat,
- jeden účet EDC nyní může mít současně nastaveno více skupin sdílení,
- výběr skupiny nadále používá názvy skupin poskytnuté portálem EDC.

## 0.1.7 – 2026-09-02

- opraveno zpracování odpovědi EDC obsahující více 15minutových řádků pro stejný den; denní hodnoty jsou nyní součtem všech intervalů,
- přidána hodinová agregace spotřeby, sdílení, dokupu, nevyužitého přetoku, pokrytí a tržby,
- stávající denní statistiky a senzory zůstávají beze změny.

## 0.1.6 – 2026-09-02

- senzory původně označené „dnes“ nyní zobrazují poslední den, pro který už EDC zveřejnilo vyhodnocení,
- datum zdrojových dat je dostupné v atributu `data_date`,
- názvy těchto senzorů v češtině i angličtině jasně uvádějí, že jde o poslední dostupný den.

## 0.1.5 – 2026-09-02

- příprava repozitáře pro zařazení do výchozího katalogu HACS,
- validace HACS nyní probíhá bez ignorovaných kontrol,
- přidáno přímé tlačítko pro otevření repozitáře v HACS.

## 0.1.4 – 2026-09-02

- automatické stažení denních výsledků za předchozí a aktuální kalendářní měsíc,
- rozdělení požadavků do limitu EDC nejvýše 31 dní a sloučení výsledků bez duplicit,
- bezpečný idempotentní import šesti denních řad do dlouhodobých statistik Home Assistantu,
- průběžné doplnění nově uzavřených dnů a oprav EDC jednou denně.

## 0.1.3 – 2026-09-02

- přidána vlastní ikona integrace pro Home Assistant 2026.3 a novější,
- doplněn anglický runtime překlad, aby se místo obecných názvů `Energy` a `Monetary balance` zobrazovaly jednoznačné názvy senzorů,
- dokumentováno chování historie a vysvětlen počet vytvářených senzorů.

## 0.1.2 – 2026-09-02

- opraveno přihlášení při již existující relaci EDC v Home Assistantu,
- EDC je výslovně požádáno o nové ověření uloženými přihlašovacími údaji,
- autorizační kód se zachytí před automatickým přesměrováním na portál,
- chybějící `loginAction` se správně hlásí jako technická chyba místo neplatných údajů.

## 0.1.1 – 2026-09-01

- opraveno přihlášení po přechodu EDC na JavaScriptem vykreslovanou přihlašovací stránku Keycloakify,
- technické chyby přihlašovacího toku se již nezobrazují jako neplatný e-mail nebo heslo,
- přidány testy parseru aktuálního formátu `kcContext`.

## 0.1.0 – 2026-09-01

- první veřejná verze,
- přihlášení k portálu EDC a obnovení hesla,
- výběr skupiny sdílení,
- denní a měsíční energetické senzory,
- nastavitelná prodejní cena,
- výpočet hodnoty nasdílené výroby,
- český překlad a podpora HACS.
