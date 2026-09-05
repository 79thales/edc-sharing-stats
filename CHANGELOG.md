# Přehled změn / Changelog

## 0.1.20 – 2026-09-05

### Čeština

- samostatné pojmenované profily s vlastními příjemci, jazykem, výběrem období a denním/týdenním/měsíčním/ročním rozvrhem,
- vybraná období v jednom e-mailu nebo samostatně; probíhající a uzavřená období nezávisle na četnosti odesílání,
- náhled, ruční odeslání, pozastavení, duplikování, odstranění a stav profilu v nastavení integrace,
- volitelná energie/finance a skrytí či maskování EAN; označení neúplného rozsahu denních dat,
- uchování výsledků předání po příjemcích, ochrana proti opakovanému termínu a volba posílat jen změněná data,
- dosavadní rozvrhy se převedou na profily; původní tlačítka a identifikátory entit zůstávají zachované.

### English

- independent named profiles with their own recipients, language, report periods and daily/weekly/monthly/yearly schedules,
- combine selected periods or send them separately; choose current or completed periods independently of sending frequency,
- preview, send now, pause, duplicate, delete and inspect delivery status from the integration options,
- optional energy/financial details, hidden or masked EANs, and explicit daily-data coverage for incomplete periods,
- persistent per-recipient handoff records, duplicate-schedule protection and an option to send only changed data,
- existing schedules are adapted into profiles; original report buttons and entity identifiers are preserved.

## 0.1.19 – 2026-09-04

### Čeština

- všechny požadavky na EDC API a přihlášení mají explicitní 30sekundový timeout; pomalý nebo nedostupný portál tak nemůže ponechat aktualizaci čekat na dlouhém výchozím timeoutu `aiohttp`,
- chybné tokenové, seznamové a číselné odpovědi EDC se nyní mění na sanitizované chyby integrace; nízkoúrovňové síťové hlášky se již nepropagují do diagnostických atributů,
- hodinová historie rozlišuje obě opakované hodiny při podzimním přechodu na standardní čas a používá jednoznačné UTC timestampy; neexistující jarní lokální hodina je odmítnuta místo vytvoření kolidující statistiky,
- přibyly regresní testy pro timeout, autentizaci, vadné odpovědi, oba DST přechody, lokální půlnoc, metadata externích statistik, opakovaný import a opravené hodnoty,
- entity ID, unique ID, statistic ID, config-entry a storage schema, reporty i denní výpočty zůstávají beze změny.

### English

- all EDC API and sign-in requests now use an explicit 30-second timeout, preventing an unavailable portal from holding an update until the much longer default `aiohttp` timeout expires,
- malformed token, group-list, and numeric responses are converted to sanitized integration errors; low-level network error text is no longer propagated to diagnostic attributes,
- hourly history now distinguishes both occurrences of the repeated hour during the autumn DST transition and uses unambiguous UTC timestamps; a nonexistent spring-forward local hour is rejected instead of creating a colliding statistic,
- added regression coverage for timeouts, authentication, malformed responses, both DST transitions, local midnight, external-statistics metadata, repeated imports, and corrected values,
- entity IDs, unique IDs, statistic IDs, config-entry and storage schemas, report formatting, and daily calculations remain unchanged.

## 0.1.18 – 2026-09-04

### Čeština

- na začátek README byl přidán stručný profesionální anglický přehled funkcí pro HACS review; podrobná česká dokumentace zůstala zachována,
- bezpečnostní a privacy dokumentace nyní přesně rozlišuje trvale uložené přihlašovací údaje, tokeny pouze v paměti a údaje obsažené v diagnostických entitách, statistikách a volitelných e-mailových reportech,
- zavádějící název „zisk z výroby“ byl nahrazen přesnějším označením hodnoty sdílené elektřiny a anglické názvy používají pojmy „shared electricity“ a „grid import“; identifikátory entit a statistik se nemění,
- reálné EANy byly odstraněny z testovací fixture a nová automatická kontrola brání přidání 18místných EANů nebo skutečných e-mailových adres do textových souborů repozitáře,
- `.gitignore` nově chrání běžné soubory s přihlašovacími údaji, cookies, Home Assistant databází a exporty EDC; funkce integrace ani formát reportů se nemění.

### English

- added a concise, professional feature overview at the top of the README for HACS reviewers while retaining the detailed Czech documentation,
- clarified which credentials are persisted, which tokens remain in memory, and which data appears in diagnostic entities, long-term statistics, and optional email reports,
- replaced the misleading “production profit” label with “shared electricity value” and standardized English entity labels on “shared electricity” and “grid import”; entity IDs and statistic IDs remain unchanged,
- removed real EAN values from a test fixture and added automated checks that reject 18-digit EAN literals or non-example email addresses in repository text files,
- expanded ignore rules for common credential, cookie, Home Assistant database, and EDC export files; integration behavior and report formatting are unchanged.

## 0.1.17 – 2026-09-04

### Čeština

- poznámky k vydání jsou nově dostupné v češtině i angličtině,
- lokální metadata Visual Studia jsou vyloučena z verzování.

### English

- release notes are now available in both Czech and English,
- local Visual Studio metadata is excluded from version control.

## 0.1.16 – 2026-09-03

### Čeština

- historický blok z doby, kdy skupina ještě neobsahovala současně výrobní i odběrný EAN, již nezastaví dohledávání historie,
- přeskočený neúplný blok se započítá jako zpracovaný a hledání pokračuje až k pohyblivé roční hranici,
- roční a souhrnné e-mailové reporty přeskočí neúplné starší bloky a sestaví výsledek ze všech skutečně dostupných dnů,
- běžné načítání aktuálních dat zůstává přísné a neúplnou odpověď EDC nadále oznámí jako chybu.

### English

- a historical block from a time when the sharing group did not yet contain both a producer and a consumer EAN no longer stops the history backfill,
- an incomplete block is recorded as processed and the search continues to the rolling one-year boundary,
- annual and combined email reports skip incomplete older blocks and use all days for which complete data is available,
- regular updates of current data remain strict and still report an incomplete EDC response as an error.

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
