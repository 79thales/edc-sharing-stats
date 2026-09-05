# EDC Sharing Stats

[![Otevřít repozitář v HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=79thales&repository=edc-sharing-stats&category=integration)

## English overview

EDC Sharing Stats is a custom Home Assistant integration for electricity-sharing groups managed through the Czech EDC portal. For the latest available EDC day, it exposes shared electricity, consumption, grid import, unused production surplus, sharing coverage, and an estimated value based on a configurable CZK/kWh price. Current-month statistics additionally include total production surplus.

Historical EDC profile data is aggregated into hourly and daily Home Assistant long-term statistics. The integration supports a resumable, one-year history backfill, refresh and backfill diagnostics, and optional on-demand or scheduled email reports in Czech or English through Home Assistant `notify` entities.

Named report profiles provide independent recipients, languages, schedules and a selection of daily, weekly, monthly or yearly sections, combined into one email or sent separately. Profiles support current or completed periods, previews, manual sending, optional financial details, masked EANs and delivery status.

The EDC account email and password are stored in the Home Assistant config entry and may therefore be included in Home Assistant backups. Access and refresh tokens remain in memory only. Group names and full EANs are visible in diagnostic entities. New report profiles mask EANs by default; legacy reports include full EANs. Reports should only be sent through trusted notification targets.

This is an independent integration and is not an official product of, or supported by, Elektroenergetické datové centrum, a. s. The EDC web API is not publicly guaranteed and may change without notice.

## Česká dokumentace

Vlastní integrace pro Home Assistant, která načítá vyhodnocení skupiny sdílení elektřiny z českého portálu EDC.

## Funkce

- přihlášení k EDC přes uživatelské rozhraní Home Assistantu,
- automatické načtení a výběr skupiny sdílení,
- hodnoty za poslední dostupný den a za aktuální měsíc pro sdílení, spotřebu, dokup a přetoky,
- procentuální pokrytí spotřeby sdílenou elektřinou,
- nastavitelná prodejní cena v Kč/kWh,
- výpočet hodnoty nasdílené elektřiny jako `nasdílené kWh × prodejní cena`,
- automatické stažení profilových dat za předchozí a aktuální kalendářní měsíc,
- hodinová i denní historie vypočtená ze zdrojových intervalů EDC,
- ruční dohledání a doplnění dostupné historie EDC až jeden kalendářní rok zpět,
- hodinová aktualizace a podpora dlouhodobých statistik Home Assistantu,
- ruční pokus o okamžité načtení dat a diagnostika posledního i příštího pokusu,
- opětovné zadání hesla, pokud EDC uložené údaje odmítne,
- samostatné diagnostické entity pro všechny sdílející i cílové EANy ve skupině,
- ruční i automatické denní, týdenní, měsíční a roční reporty na jednu nebo více e-mailových adres,
- volba češtiny nebo angličtiny pro předmět i obsah e-mailových reportů,
- souhrnný report se všemi čtyřmi obdobími v jediném e-mailu.

> [!IMPORTANT]
> Hodnota sdílení neodečítá investiční ani provozní náklady a nepředstavuje čistý zisk. Jde o hodnotu skutečně nasdílené energie při nastavené ceně.

## Instalace přes HACS

1. V HACS otevřete **Integrace**.
2. V nabídce zvolte **Vlastní repozitáře**.
3. Přidejte `https://github.com/79thales/edc-sharing-stats` jako typ **Integrace**.
4. Vyhledejte a nainstalujte **EDC Sharing Stats**.
5. Restartujte Home Assistant.
6. Otevřete **Nastavení → Zařízení a služby → Přidat integraci** a vyhledejte **EDC Sharing Stats**.

## Ruční instalace

Zkopírujte adresář `custom_components/edc_sharing` do adresáře `custom_components` ve své konfiguraci Home Assistantu a Home Assistant restartujte.

## Nastavení

Průvodce vyžaduje:

- e-mail a heslo k portálu EDC,
- skupinu sdílení dostupnou danému účtu,
- prodejní cenu elektřiny v Kč/kWh.

Skupinu a cenu lze později změnit přes **Nastavení → Zařízení a služby → EDC Sharing Stats → Nastavit**. Přístupový i obnovovací token zůstává pouze v paměti; po restartu se integrace přihlásí znovu uloženými přístupovými údaji.

Pokud účet obsahuje více skupin sdílení, lze integraci přidat opakovaně a při každém nastavení vybrat jinou skupinu podle názvu vráceného EDC. Každý nalezený sdílející a cílový EAN má vlastní diagnostickou entitu se stavem obsahujícím celé číslo EAN. Entit může být na obou stranách libovolný počet a jejich zobrazované názvy lze běžně změnit v nastavení entity Home Assistantu.

## E-mailové reporty

### Samostatné profily příjemců a rozvrhů

Otevřete **Nastavení → Zařízení a služby → EDC Sharing Stats → Nastavit → Profily reportů → ＋**.
Zadejte název profilu, jeho příjemce (`notify` entity vytvořené v SMTP), jazyk a vyberte období.
Nový profil je zpočátku pozastavený; přepínačem **Automatické odesílání zapnuto** zapnete jeho rozvrh.

| Nastavení | Význam |
| --- | --- |
| Období v reportu | Libovolná kombinace denního, týdenního, měsíčního a ročního reportu |
| Všechna období v jednom e-mailu | Zapnuto: jeden společný e-mail; vypnuto: samostatný e-mail za každé období |
| Rozsah období | Probíhající týden/měsíc/rok, nebo předchozí uzavřené období |
| Četnost a čas | Denně, vybrané dny týdne, měsíčně nebo ročně; roční plán má vlastní měsíc |
| Den v měsíci | 1–28, aby byl termín platný ve všech měsících |
| Pouze při změně dat | Při plánovaném pokusu se nezměněné hodnoty znovu neposílají; oprava dat EDC se počítá jako změna |
| Energie / finance | Zvolte, které údaje příjemci dostanou; alespoň jedna skupina musí zůstat zapnutá |
| EAN | Skrýt, poslední čtyři číslice (výchozí), nebo celé EAN |

Například můžete sobě posílat každý den český souhrn dne, měsíce a aktuálního roku; účetní každý pátý den uzavřený předchozí měsíc; jinému příjemci v pondělí anglický týdenní přehled.
Četnost odesílání je nezávislá na obsahu: aktuální rok lze posílat každý týden, uzavřený rok jednou ročně.
Denní část vždy používá **poslední dostupný den EDC**, nikoliv automaticky dnešek.

Po výběru uloženého profilu lze upravit nastavení, profil pozastavit/zapnout, duplikovat, zobrazit náhled, odeslat nyní, odstranit nebo zobrazit stav.
**Náhled nic neodesílá. Odeslat nyní** vyžaduje potvrzení v následujícím formuláři, odešle všem příjemcům profilu a funguje i při pozastavení nebo nezměněných datech.
Duplikát dostane nové ID a je pozastavený.

Stav uvádí poslední pokus, poslední úspěšné předání a příští plánovaný pokus. Úspěšné předání SMTP není potvrzením doručení do schránky.
Chyba jednoho příjemce nezastaví ostatní. Výsledky předání se uchovávají samostatně po příjemcích a zprávách i přes restart, bez ukládání textů e-mailů nebo SMTP chyb.
Opakovaný termín v podzimní změně času neposílá znovu již úspěšně předané zprávy; neexistující jarní čas se přeskočí.
Zmeškané termíny při vypnutém HA se automaticky nedohánějí. Selhání se automaticky neopakuje v krátké smyčce; další pokus je podle rozvrhu nebo ruční.
Pokud proces skončí přesně mezi předáním SMTP a uložením výsledku, nelze vyloučit opakované předání.

Report ukazuje skutečný rozsah dostupných **denních** dat a počet dnů oproti požadovanému období. Neúplné období je označené, chybějící dny nejsou vydávány za nulovou spotřebu. Tento přehled neověřuje úplnost každého měřicího intervalu uvnitř dne.
Výpočty jsou stále **za celou zvolenou skupinu**, nikoliv za jednotlivého příjemce nebo EAN.

Dosavadní zapnuté rozvrhy se zobrazí jako profily `EDC — daily/weekly/monthly/yearly/summary` se zachovanými příjemci, časy a jazykem. První uložení profilu je uloží do nového seznamu; dále se rozvrhy upravují už pouze přes profily. Prázdný seznam profilů automatické odesílání vypne.
Původní tlačítka na zařízení nadále používají výchozí příjemce a jazyk v **Obecném nastavení a původních tlačítkách**; nastavení konkrétního profilu se na ně nevztahuje.

### SMTP a původní tlačítka

### Jak vytvořit e-mailového příjemce

1. Otevřete **Nastavení → Zařízení a služby → Přidat integraci**.
2. Vyhledejte a přidejte integraci **SMTP**.
3. Zadejte odesílací adresu, SMTP server, port, zabezpečení, uživatelské jméno a heslo nebo heslo aplikace vašeho poskytovatele.
4. Během nastavení zadejte první cílovou e-mailovou adresu.
5. Další adresy přidáte přes **Nastavení → Zařízení a služby → SMTP → Přidat příjemce**.

Každá cílová adresa vytvoří samostatnou `notify` entitu. Vyberte ji v konkrétním profilu reportů. Pro původní tlačítka vyberte výchozí příjemce a jazyk v **Nastavit → Obecné nastavení a původní tlačítka**. Staré rozvrhy (do prvního uložení profilů) mají výchozí čas 07:30, týdenní report v pondělí a měsíční i aktuální roční report pátý den měsíce. Nové profily mají čas a četnost nezávislé.

Nastavení SMTP lze před reporty ověřit přes **Nastavení → Vývojářské nástroje → Akce → `notify.send_message`**. Jako cíl vyberte vytvořenou `notify` entitu a odešlete zkušební zprávu.

Reporty lze odeslat i ručně pomocí tlačítek **Odeslat denní report**, **Odeslat týdenní report**, **Odeslat měsíční report** a **Odeslat roční report** na zařízení integrace. Denní report obsahuje poslední den dostupný v EDC, týdenní předchozí uzavřený týden od pondělí do neděle a měsíční předchozí uzavřený kalendářní měsíc. Roční report obsahuje aktuální kalendářní rok od 1. ledna do posledního dne, pro který EDC skutečně vrátilo data. Tlačítko **Odeslat souhrnný report** spojí všechny čtyři části do jediného e-mailu. Každý report uvádí skupinu, všechny sdílející a cílové EANy, spotřebu, nasdílenou elektřinu, dokup ze sítě, přetok výrobny, nevyužitý přetok, pokrytí a hodnotu sdílení.

## Vytvářené senzory

- nasdíleno, spotřeba, dokup, nevyužitý přetok, pokrytí a tržba za poslední den dostupný v EDC,
- nasdíleno, spotřeba, dokup, přetok výrobny, nevyužitý přetok, pokrytí a hodnota sdílení za aktuální měsíc,
- nastavená prodejní cena.

Integrace vytváří 14 základních hodnotových senzorů. Nejde o duplicity: šest patří poslednímu dni dostupnému v EDC, sedm aktuálnímu měsíci a jeden představuje nastavenou prodejní cenu. Každý senzor má vlastní jedinečný identifikátor a lokalizovaný název. U šesti denních senzorů atribut `data_date` uvádí skutečné datum měření; EDC obvykle zveřejňuje vyhodnocení se zpožděním, takže nemusí jít o dnešní datum.

Navíc vzniká diagnostický časový senzor **Poslední pokus o načtení dat**. Jeho stav uvádí okamžik posledního pokusu; atributy `result`, `last_success`, `next_attempt` a `error` ukazují výsledek, poslední úspěšné načtení, očekávaný další automatický pokus a případnou chybu. Diagnostický senzor zůstává dostupný i tehdy, když se samotné načtení nezdaří.

Přímo v diagnostické části zařízení jsou také entity **Stav stahování historie** a **Data EDC dostupná od**. První viditelně ukazuje stav `Nespuštěno`, `Probíhá`, `Pozastaveno`, `Selhalo` nebo `Dokončeno`; po otevření entity jsou v atributech procenta postupu, prohledávaný rozsah, počet importovaných dnů a hodin i případná chyba. Druhá entita ukazuje nejstarší datum skutečně nalezené v odpovědích EDC; dokud stav není `Dokončeno`, může se při hledání posouvat dále do minulosti. Podrobné atributy `history_backfill_*` zůstávají také u senzoru posledního pokusu kvůli zpětné kompatibilitě.

Stejných šest senzorů uvádí v atributech také `daily_statistic_id` a `hourly_statistic_id`. Uživatel tak může přesné identifikátory své skupiny rovnou zkopírovat do karty **Graf statistik**, aniž by ručně hledal interní číslo skupiny.

## Historie a dlouhodobé statistiky

Při načtení integrace se automaticky stáhnou profilová data od prvního dne předchozího kalendářního měsíce do současnosti. EDC povoluje v přehledu nejvýše 31 dní, proto integrace delší období sama rozdělí na několik požadavků a výsledky sloučí bez duplicit. Zdrojové intervaly se sečtou po jednotlivých hodinách i kalendářních dnech. Jednou denně se celé období znovu načte, takže se doplní nově uzavřené intervaly i případné opravy na straně EDC.

Historické hodnoty se zapisují podporovaným API jako externí dlouhodobé statistiky. Nevytvářejí falešné zpětně datované změny stavů v databázi Recorderu. Denní řady mají identifikátory ve tvaru `edc_sharing:<ID skupiny>_shared_daily`, `consumption_daily`, `grid_daily`, `unused_daily`, `coverage_daily` a `revenue_daily`. Stejné názvy s koncovkou `_hourly` obsahují hodinové hodnoty. Lze je vybrat v panelu Historie nebo v kartě **Graf statistik**; zobrazovaným typem je `mean`.

Běžné senzory se nadále obnovují jednou za hodinu a Home Assistant jejich stavy ukládá od okamžiku instalace. Energetické senzory mají třídu stavu `total` a podporují také standardní dlouhodobé statistiky.

Okamžité načtení lze spustit tlačítkem **Načíst data EDC nyní** na zařízení skupiny v **Nastavení → Zařízení a služby → EDC Sharing Stats**. Tlačítko pouze požádá EDC o aktuálně zveřejněná data; nevytvoří data, která EDC ještě nezpřístupnilo. Po dokončení se aktualizuje diagnostický senzor popsaný výše.

Tlačítko **Doplnit dostupnou historii EDC za poslední rok** spustí jednorázové hledání směrem do minulosti. Počáteční mez se při každém novém spuštění určí jako stejné kalendářní datum předchozího roku. Při spuštění 3. září 2026 se tedy hledá nejvýše do 3. září 2025. Integrace postupuje od nejnovějších dat dozadu v blocích nejvýše 31 dní; v tomto příkladu proto samostatně načte také blok od 1. července do 1. srpna 2026. Ojedinělý prázdný blok ani blok z doby před zapojením obou rolí EAN nepovažuje za konec historie. Takový neúplný blok přeskočí, pokračuje dál a nejstarší skutečně dostupné datum určí jen z úplných dat sdílení vrácených portálem. Každý použitelný blok se průběžně zapíše do dlouhodobých statistik. Uložený kurzor i začátek období umožní po restartu automaticky pokračovat od posledního dokončeného bloku. Po dokončení lze tlačítko použít znovu, například kvůli dodatečným opravám dat na straně EDC.

Zdrojové intervaly EDC se uchovávají v dlouhodobých statistikách jako hodinové a denní součty. Samostatné čtvrthodinové řady se nevytvářejí, aby zbytečně nezvětšovaly databázi Recorderu.
Hodinové body používají jednoznačné UTC časové značky. Při podzimním přechodu času zůstanou obě opakované místní hodiny oddělené; při jarním přechodu integrace nevytváří statistiku pro neexistující místní hodinu.

## Omezení a bezpečnost

- Integrace používá webové API portálu EDC, které není veřejně garantované a může se změnit.
- Jednotlivé požadavky na portál a přihlášení mají timeout 30 sekund. Běžná aktualizace se po přechodné chybě opakuje v následujícím hodinovém intervalu; doplňování historie se zastaví se stavem `Selhalo` a lze je bezpečně obnovit.
- Účty vyžadující další interaktivní krok nebo vícefaktorové ověření zatím nejsou podporované.
- E-mail účtu EDC a heslo jsou uloženy v konfigurační položce Home Assistantu a mohou být součástí záloh. Chraňte přístup k adresáři konfigurace, skrytému úložišti `.storage` a zálohám.
- Přístupový a obnovovací token jsou pouze v paměti API klienta. Integrace je neukládá do úložiště průběhu historie, atributů entit ani vlastních logů.
- Diagnostické entity záměrně zobrazují celý EAN a název skupiny. Dlouhodobé statistiky obsahují energetické hodnoty a interní ID skupiny.
- E-mailové reporty obsahují název skupiny a zvolené hodnoty. Nové profily standardně maskují EAN; celé EAN obsahují původní reporty a profily s výslovně zapnutým úplným zobrazením. Odesílají se výhradně přes vybrané Home Assistant `notify` entity; používejte pouze důvěryhodné příjemce a SMTP server.

## Podpora

Chyby a návrhy hlaste v [GitHub Issues](https://github.com/79thales/edc-sharing-stats/issues).

Tento projekt není oficiálním produktem ani podporovanou integrací Elektroenergetického datového centra, a. s.
