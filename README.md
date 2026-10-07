# EDC Sharing Stats

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.8.0%2B-41BDF5?logo=home-assistant&logoColor=white&style=flat)](https://www.home-assistant.io/)
[![HACS Integration](https://img.shields.io/badge/HACS-Integration-41BDF5?logo=home-assistant-community-store&logoColor=white&style=flat)](https://my.home-assistant.io/redirect/hacs_repository/?owner=79thales&repository=edc-sharing-stats&category=integration)
[![Latest release](https://img.shields.io/github/v/release/79thales/edc-sharing-stats?label=Release&logo=github&style=flat)](https://github.com/79thales/edc-sharing-stats/releases/latest)
[![Installer downloads, all releases](https://img.shields.io/github/downloads/79thales/edc-sharing-stats/edc_sharing.zip?label=Downloads%20total&displayAssetName=false&logo=github&style=flat)](https://github.com/79thales/edc-sharing-stats/releases)
[![Installer downloads, latest release](https://img.shields.io/github/downloads/79thales/edc-sharing-stats/latest/edc_sharing.zip?label=Downloads%20latest&displayAssetName=false&logo=github&style=flat)](https://github.com/79thales/edc-sharing-stats/releases/latest)
[![Validation](https://img.shields.io/github/check-suites/79thales/edc-sharing-stats/main?label=Validation&logo=github&style=flat)](https://github.com/79thales/edc-sharing-stats/actions)

<p align="center">
  <img src="https://raw.githubusercontent.com/79thales/edc-sharing-stats/main/custom_components/edc_sharing/brand/icon@2x.png" alt="EDC Sharing Stats" width="180">
</p>

HACS displays documentation for the installed version. The unified header is included from v0.1.33. Update this repository in HACS to see it; refreshing the page or updating only the default branch does not change an older release's README.

## English overview

EDC Sharing Stats is a custom Home Assistant integration for electricity-sharing groups managed through the Czech EDC portal. For the latest available EDC day, it exposes shared electricity, consumption, grid import, unused production surplus, sharing coverage, and an estimated value based on a configurable CZK/kWh price. Current-month statistics additionally include total production surplus. Separate surplus-utilization sensors show the percentage of production surplus actually used for sharing for the latest day, current week, month, year and all retained history.

Historical EDC profile data is aggregated into hourly and daily Home Assistant long-term statistics. The integration supports a resumable, one-year history backfill, refresh and backfill diagnostics, and optional on-demand or scheduled email reports in Czech or English through Home Assistant `notify` entities.

An optional paid-target selection exports cumulative CZK income and kWh statistics for the Energy dashboard, separately for each selected target and their combined selection. Delayed daily totals are attributed to the actual EDC day using each target's configured price; the daily amount is booked in that day's final hour rather than representing an hourly income profile.

Named report profiles provide independent recipients, languages, schedules and a selection of daily, weekly, monthly or yearly sections, combined into one email or sent separately. Profiles support current or completed periods, previews, manual sending, optional financial details, masked EANs and delivery status. With Home Assistant 2026.8 or newer and SMTP, a profile can also include a locally generated Czech QR payment request for a positive, complete monthly amount or the continuous currently available range of annual data.

An optional administrator-only payments section reuses saved profiles for private-person settlements over custom inclusive date ranges. Issuing and SMTP sending never confirm payment: only optional manual receipts reduce payable balances. Overlapping statements share unique EAN/day charges; frozen documents and private local storage remain separate from live reports and Energy statistics.

When EDC returns multiple target EANs, the integration also creates an individual device for each target supply point. You can assign a local name and location, optionally override the group electricity price for that target, and send either the original group report or target-specific report sections to different recipients. Target-specific QR payment references include the recipient name and full target EAN.

The EDC account email and password are stored in the Home Assistant config entry and may therefore be included in Home Assistant backups. Access and refresh tokens remain in memory only. Group names and full EANs are visible in diagnostic entities. New report profiles mask EANs by default; legacy reports include full EANs. Reports should only be sent through trusted notification targets.

This is an independent integration and is not an official product of, or supported by, Elektroenergetické datové centrum, a. s. The EDC web API is not publicly guaranteed and may change without notice.

The download badges count only downloads of the `edc_sharing.zip` release asset, including HACS updates and manual downloads. They do not count unique users, source-code archives or default-branch installations. Counting starts with v0.1.32; earlier downloads cannot be reconstructed. HACS's download indicator refers to the selected release, while the total badge combines installer downloads across releases. GitHub, HACS and badge caches may update at different times. No usage tracking is added to the integration.

### Dashboard generator (v0.1.34)

An administrator can generate a named dashboard in the EDC Share2 sections style: native tiles, percentage gauges, dated EDC history charts, details and optional individual supply-point sections. Choose downloadable YAML or explicitly create a **new** storage dashboard through Home Assistant's authenticated Lovelace API. Current entity IDs are resolved from the entity registry, including user renames. Existing dashboards, Energy settings, prices, reports and stored EDC data are never modified. Direct creation defaults to an administrator-only dashboard; it requires a preview and confirmation.

## Česká dokumentace

### Generátor dashboardu (v0.1.34)

V **Nastavení → Zařízení a služby → EDC → Konfigurovat → Vygenerovat dashboard** otevřete odkaz na generátor. U zařízení skupiny je také nové konfigurační tlačítko **Vygenerovat dashboard**. Protože backendové tlačítko Home Assistantu nemůže samo otevřít formulář v konkrétním prohlížeči, vytvoří oznámení s odkazem na stejný generátor. Tlačítko nic nezaloží ani nic neodešle e-mailem.

Šipka **Zpět do integrace** vlevo v pevné hlavičce generátoru i plateb vrací přímo na stránku EDC, také na mobilu nebo při otevření přímým odkazem. Nabídka HA zůstává vpravo. Návrat sám nic nevytváří ani neodesílá, ale nezruší již potvrzenou a zahájenou operaci; rozpracovaný YAML si před odchodem zkopírujte nebo stáhněte.

1. Zadejte **název a adresu dashboardu**, vyberte skupinu a češtinu nebo angličtinu.
2. Volitelně zahrňte jednotlivá odběrná místa (s jejich vlastními hodnotami a cenami), stránku detailů a tabulku Energy.
3. Vyberte **Vygenerovat YAML** nebo **Přímo založit nový dashboard** a vytvořte náhled.
4. YAML můžete zkopírovat nebo stáhnout jako soubor. Jde o **celou konfiguraci dashboardu**, nikoli jedinou kartu či pohled. Vložte jej do editoru surové konfigurace nového prázdného dashboardu.
5. Přímé založení je dostupné jen správci a vyžaduje samostatné potvrzení. Nový dashboard se přidá do bočního menu a standardně jej uvidí pouze správci; tuto volbu lze změnit před založením.

Vzhled vychází z EDC Share2: barevné dlaždice, dva sloupce uvnitř sekcí, nejvýše čtyři sloupce dashboardu, procentní ukazatele, finance, historie a podstránka detailů. Používá pouze nativní karty, bez Mushroom, dalších HACS karet či externích skriptů. Skutečná ID entit se načítají z registru; přejmenované entity jsou podporované a vypnuté či dosud nevytvořené senzory se vynechají. Dashboard je jednorázový výstup: vaše pozdější úpravy ani nová odběrná místa se automaticky nepřepisují nebo nepřidávají. Export obsahuje skutečná ID entit a názvy/lokality odběrných míst (ID mohou obsahovat EAN); před veřejným sdílením jej anonymizujte. Hesla, tokeny, e-mailoví příjemci ani bankovní účty se do něj nevkládají.

Historické grafy používají importované denní/hodinové statistiky s původním **datem EDC**, nikoli časem stažení. Roční přehled uvádí skutečný dostupný rozsah. EDC výsledky zůstávají zpožděné přibližně o jeden den. Volitelná tabulka Energy zobrazuje **celkovou stávající konfiguraci domu**, ne jen danou skupinu; generátor nevkládá EDC do Energy automaticky.

Existující adresa se odmítne — generátor nikdy nepřepisuje Home64, EDC Share2 ani jiné dashboardy. Založení používá přihlášenou relaci správce a nativní `lovelace/dashboards/create` a `lovelace/config/save`; nepíše přímo do `.storage` a nepotřebuje další token. Pokud se po založení nepodaří potvrdit uložení obsahu, nový dashboard zůstane zachovaný a YAML je stále dostupný pro ruční vložení. Automaticky se nic nemaže. Adresa `/edc-sharing-dashboard` patří generátoru; pokud ji již používá jiný panel, ten se nezmění a HA zaznamená upozornění.

### Platby a vyúčtování mezi soukromými osobami (v0.1.35)

V **Nastavení → Zařízení a služby → EDC → Konfigurovat → Platby a vyúčtování** otevřete administrátorskou sekci. Jde o soukromé **Vyúčtování sdílené elektřiny**, nikoli o automatický daňový doklad, bankovní účetnictví nebo ověření úhrad bankou. Generování vyúčtování nevypočítává DPH ani neposuzuje daňové povinnosti. Běžné reporty, jejich plánování, senzory, ceny a statistiky Energy se nemění.

1. **Nejdříve vytvořte profil reportů.** Používají se výhradně skutečně uložené profily: jejich příjemci, jazyk, skupinový nebo individuální rozsah a finanční nastavení. Starší výchozí nastavení původních tlačítek se nepovažuje za vytvořený profil. Bez profilu nelze začít nastavovat ani vystavovat nové doklady. Archiv již vystavených dokladů je dostupný i po odstranění profilu.
2. Uložte jméno a případně adresu vystavitele. **Ruční potvrzování úhrad je volitelné a výchozím stavem vypnuté.** Vypnutí této volby později nemaže dřívější potvrzení ani jejich vliv na zůstatek.
3. Vyberte profil s povolenými financemi, vyplňte jméno a případně adresu odběratele a splatnost. Zvolte poslední kalendářní měsíc, aktuální rok do dostupného dne nebo **vlastní období od–do včetně obou dnů**. Použije se pouze již uložená historie EDC, bez nových požadavků na portál. Jsou povolené minulé dny a nejvýše 3660 dnů v jednom dokladu; skutečný dostupný rozsah může být kratší. Splatnost nesmí být v minulosti.
4. Vytvořte a zkontrolujte náhled. Chybějící, záporné nebo neplatné denní hodnoty blokují konečné vystavení; chybějící den se nevydává za nulu. U skupinového dokladu je navíc nutná shoda individuálních nasdílených energií se skupinovým denním součtem. **Tato kontrola ověřuje dostupnost denních agregací, nikoli úplnost každého intervalu uvnitř dne.** Nový doklad nepředstavuje ověření správnosti vyúčtování samotným EDC.
5. Samostatným potvrzením **Vystavit** vznikne uložený doklad s číslem `EDC-rok-pořadí` a desetimístným variabilním symbolem. Číslo se přidělí až při vystavení a při opakování stejného dokladu se znovu nepřiděluje. Číselná řada a variabilní symbol jsou lokální pro otevřenou config entry/skupinu, nikoli společné pro všechny skupiny či účetní systémy. Vystavení nic neodešle a nepotvrdí úhradu.
6. Doklad lze stáhnout jako samostatné tiskové HTML nebo použít **Tisk / uložit do PDF** v prohlížeči. Integrace nevytváří serverové PDF ani PDF přílohu. Po samostatném potvrzení se celé vyúčtování odešle v těle HTML e-mailu přes `smtp.send_message`; zůstává také textová varianta. Pokud je u skupiny nastavený účet a zbývá kladná jednoznačná částka, **QR je přímo v těle e-mailu**, nikoli v příloze. Obsahuje zbývající částku, účet, variabilní symbol a popis období; u jednoho EANu i identifikaci odběratele a EAN. Bez účtu nebo při nulovém zůstatku QR nevzniká.

#### Vystaveno / odesláno není zaplaceno

- **Vystavení ani předání SMTP neznamená potvrzenou platbu.** Stav SMTP znamená pouze předání poskytovateli; nepotvrzuje doručení do schránky ani přijetí peněz. Selhání může mít nejistý výsledek: před opakováním zkontrolujte schránku. Automatické opakování odesílání není zapnuté.
- **Odečítají se pouze ručně potvrzené úhrady.** Dokud platba není potvrzená, částka zůstává nabízena k zaplacení, včetně ročního nebo vlastního přehledu. Bez potvrzení stav zní **Úhrada nepotvrzena**, nikoli tvrzení, že odběratel určitě nezaplatil. Integrace nemá spojení s bankou.
- **Opakovaná výzva ani překryv období nevytváří další dluh.** Evidence vede sdílení jednou pro kombinaci skupiny, cílového EANu a dne; měsíční a roční doklady odkazují na stejné položky. Celkový zůstatek se počítá z unikátních sdílení a úhrad, nikoli sečtením částek všech dokladů.
- Příklad: doklad má hodnotu **1 000 Kč**, ručně potvrzeno **400 Kč** → **zbývá 600 Kč**, a QR požaduje 600 Kč. Bez potvrzení těchto 400 Kč se nadále nabízí původních 1 000 Kč. Potvrzení celé zbývající částky ukončí nabídku platby a QR zmizí.
- Příklad překryvu: leden už má vystavený doklad, ale úhrada není potvrzená → roční vyúčtování lednovou částku **stále nabídne k úhradě**. Potvrzená lednová úhrada se odečte také z ročního zůstatku. Samotné vystavení lednového dokladu není důvod lednovou částku považovat za zaplacenou.
- Ruční potvrzení lze přiřadit celému dokladu nebo výslovně zvolenému EANu a dílčímu rozsahu. U částečné platby za širší období **nelze odhadnout**, jaká část připadá na menší překrývající se období nebo EAN. Takový náhled oznámí nejednoznačné přiřazení a zablokuje vystavení i QR. Zkontrolujte přiřazení; chybné potvrzení lze zrušit a zaznamenat správně. Pokud na něm závisí pozdější úplné potvrzení, je nutné nejprve zrušit to navazující. Auditní záznam se nemaže. Potvrzená úplná úhrada jednoznačně pokrývá i dílčí období.

#### Pevný podklad a rozsah příjemců

První vystavení uloží pro každý zahrnutý EAN a den nasdílenou energii a použitou cenu. Pro individuální profil se používá vlastní cena EANu, případně cena skupiny. Skupinový profil respektuje jeho volbu výchozí skupinové ceny nebo součtu individuálních cen. Nově zahrnuté dny použijí cenu nastavenou při vystavení; **již vystavené denní podklady se po změně ceny, popisu nebo opravě EDC samovolně nepřepočítají**. To se týká nové evidence vyúčtování, nikoli stávajících živých reportů a statistik Energy, které nadále fungují dosavadním způsobem. Nevytváří se historický ceník.

Decimal výpočet zachovává nezaokrouhlenou energii a denní hodnotu. Při prvním vystavení se součet **nových dnů každého EANu** zaokrouhlí na dvě místa metodou HALF_UP a haléře se jednou rozdělí mezi jeho denní položky metodou největších zbytků (při shodě podle data). Tyto uložené haléřové položky používají všechna další překrývající se vyúčtování a úhrady. Dílčí období se z raw hodnot nezávisle znovu nezaokrouhlují, aby již zaplacený haléř nevznikl podruhé jako doplatek. U velmi malých částek může zvolený první rozsah vystavení ovlivnit přiřazení jednotlivého haléře ke dni; raw energie a hodnota zůstávají zachované. Součet položek a zůstatek jsou stabilní a nikdy nevznikají součtem duplicitních dokladů.

Tato první verze nemá funkci opravných/dobropisových dokladů ani změnu již uloženého denního podkladu. Před potvrzením vystavení proto zkontrolujte zejména cenu a EANy. Zrušení **potvrzení úhrady** není zrušení vyúčtované hodnoty. Název/adresa nově vystaveného dokladu se mohou změnit po novém náhledu, ale tím se nepřepíše dříve uložená energie nebo cena.

**Všichni příjemci jednoho profilu obdrží stejný doklad se všemi EANy jeho rozsahu.** Integrace nerozděluje obsah automaticky mezi adresy. Pro oddělená soukromá vyúčtování vytvořte samostatný profil pro každého odběratele. Vyúčtování obsahuje plné EANy i tehdy, když běžný report profilu EAN maskuje: jde o identifikaci položek dokladu. Před vystavením i odesláním zkontrolujte příjemce a rozsah. Pozastavený profil lze použít pro výslovné ruční vystavení/odeslání; jeho plán se nemění. Když se po vystavení změní příjemci, jazyk nebo finanční rozsah profilu, případně se profil odstraní, odeslání starého dokladu se zablokuje. Vystavte nový výslovně zkontrolovaný doklad; shodné sdílení se tím nezapočítá podruhé. Vystavený doklad si zachovává původní jména, adresy, účet, číslo a podklady; stav úhrad a zůstatek se při otevření nebo odeslání aktualizuje z evidence potvrzení.

#### Uložení a bezpečnost

Nová evidence používá vlastní versionované privátní HA `Store`, oddělené podle config entry a skupiny. Nemění úložiště historie EDC, reportů ani config-entry schema. Doklady, účet, plné EANy, jména a adresy se ukládají lokálně a mohou být v zálohách Home Assistantu. `private` neznamená dodatečné šifrování. Hesla EDC/SMTP, tokeny ani cookies se do evidence nevkládají. Přístup k panelu i všem čtecím/zapisovacím akcím má pouze správce přes přihlášené Home Assistant WebSocket API. Chybové odpovědi a vlastní logy neobsahují obsah dokladů, příjemce nebo tajné údaje. Exporty anonymizujte před veřejným sdílením.

Zápisy se serializují, kontrolují revizi a potvrzení vystavení se váže na přesný náhled. Ztracená odpověď a opakování stejné operace nevytvoří druhý doklad ani druhou úhradu. Odeslání nejprve uloží úmysl předání SMTP; stejná operace se automaticky neposílá podruhé ani při nejistém výsledku. Nečitelné úložiště se **nikdy automaticky nevynuluje**. Opravu nebo zálohu řešte výslovně. Selhání nového panelu neblokuje stávající nastavení a načítání EDC. Nic se samo nevystavuje, neposílá ani nepotvrzuje jako zaplacené.

### Payments and private settlements (v0.1.35)

Open **Configure → Payments and settlements**. An explicitly saved report profile must exist first; billing reuses its recipients, language, EAN scope and financial mode rather than maintaining separate email settings. Issue a private electricity-sharing settlement for the previous month, current year or an inclusive custom range of past dates (up to 3660 days), using cached daily totals only. Missing/invalid daily data or inconsistent group totals block final issue; this is a daily-presence check, not validation of every intraday EDC interval. No VAT is calculated and no tax compliance or bank payment is certified.

Both EDC panels have a **Back to integration** arrow on the left of their sticky header, including on mobile and when opened directly. The HA menu remains on the right. Returning does not initiate creation or sending, but does not cancel an already confirmed, in-progress operation; copy or download generated YAML before leaving the generator.

Preview and explicitly issue a numbered, locally retained document. Download printable HTML or use the browser's Print / Save as PDF; there is no server-generated PDF attachment. Explicit SMTP sending places the document and optional QR for the **remaining** amount in the email body, with a plain-text alternative. Issuing and SMTP handoff **do not confirm payment**; handoff does not certify inbox delivery. Manual payment tracking is optional and off by default. Only confirmed receipts reduce balances. Unconfirmed amounts remain offered for payment, also in annual summaries. For example, value CZK 1,000 minus a manually confirmed CZK 400 leaves CZK 600 payable; without that confirmation the full CZK 1,000 is still offered.

Each target EAN/day is one shared charge across overlapping documents: repeated reminders and monthly/annual overlaps never add debt twice. Stored daily prices and energy are frozen after first issue; new days use the then-configured price. Raw energy/value precision is retained. Each EAN's newly issued range is rounded HALF_UP once; residual cents are assigned to days by largest remainder, with date as tie-breaker. All later statements and receipts reuse those same cents instead of independently rounding overlapping subranges. Existing live reports and Energy statistics retain their original behavior and are not payment records. Partial receipts are never guessed across a smaller period or EAN selection; ambiguous allocation blocks issue/QR until corrected. Full confirmed settlement covers its included subranges. Reversing a confirmation preserves its audit record; dependent full confirmations must be reversed first.

All recipients in one profile receive the same complete document, including full EANs. Use separate profiles to isolate customers. Changed or deleted routing blocks sending old documents; a newly reviewed statement still references the same charges. Local private, versioned HA storage includes personal details and bank accounts and is part of backups, not separately encrypted. Admin-only authenticated actions, atomic saves, revision/preview checks and retry IDs protect the ledger. Corrupt storage is not reset. No bank API, telemetry, new EDC requests, scheduled billing, automatic payment confirmation or changes to existing entity/statistic IDs are introduced.

Numbering and variable symbols are local to the selected config entry/group, not a global accounting series. This first version does not support credit/corrective documents or editing frozen daily charge data. Review prices and EANs before issuing. Reversing a manual receipt does not cancel the underlying sharing value.

### Příjem ze sdílení v Energy dashboardu

V nastavení integrace otevřete **Příjem ze sdílení v Energy dashboardu** a vyberte placené cílové EANy. Výchozí výběr je prázdný. Nově nalezené EANy se do příjmu nepřidávají automaticky; neplacená místa ponechte nevybraná. Cena každého vybraného EANu odpovídá nastavení **Detaily EAN a ceny**, případně ceně skupiny.

Integrace vytvoří externí dlouhodobé statistiky **Příjem ze sdílení (Energy)** v CZK a **Placená sdílená energie (Energy)** v kWh pro vybranou kombinaci míst i pro každé vybrané místo jednotlivě. V nastavení Energy připojení k síti vyberte pro kompenzaci exportu možnost **Použít entitu sledující celkovou kompenzaci** a příslušnou statistiku příjmu. Jde o externí statistiky, nikoli o živé senzory: ID společného výběru najdete v atributech diagnostického senzoru dostupnosti historie, ID jednotlivého místa v atributech jeho diagnostického EAN senzoru. Použijte společný součet nebo jednotlivá místa podle požadovaného přehledu; jejich současné započtení by příjem zdvojilo. Volba představuje hodnotu sdílení, nikoli čistý zisk nebo potvrzenou úhradu.

Příjem se importuje ke skutečnému kalendářnímu dni EDC, i pokud data přišla o den nebo více později. Podklad tvoří uložené denní součty jednotlivých míst; celá denní částka je zaúčtovaná do poslední skutečné hodiny daného dne. Hodinový graf proto neukazuje skutečný průběh sdílení. Dnešní data se neimportují. Společný výběr obsahuje pouze dny, které mají uložené záznamy všech vybraných míst; období s chybějícími záznamy se nevydává za nulový příjem. U míst přidaných později může být společná historie kratší než historie původního místa.

Opakované načtení, restart, překryv historie a opravy EDC přepočítají součty ze stejné uložené historie místo přičítání nového příjmu ke starému. Změna ceny přepočítá dostupnou historii podle aktuální ceny; časový ceník není podporován. Změna kombinace vybraných EANů vytvoří jinou společnou statistiku, kterou je potřeba znovu vybrat v Energy. Staré statistiky se nemažou; prázdný výběr zastaví nové importy a případnou starou volbu odstraňte také z Energy. Nastavení se provádí samostatně pro každou skupinu sdílení.

Energy používá součtové dlouhodobé statistiky; denní a měsíční živé senzory tržby kvůli zpoždění EDC pro toto nastavení nepoužívejte. Viz [dokumentace statistik Home Assistantu](https://data.home-assistant.io/docs/statistics/).

Vlastní integrace pro Home Assistant, která načítá vyhodnocení skupiny sdílení elektřiny z českého portálu EDC.

## Funkce

- přihlášení k EDC přes uživatelské rozhraní Home Assistantu,
- automatické načtení a výběr skupiny sdílení,
- hodnoty za poslední dostupný den a za aktuální měsíc pro sdílení, spotřebu, dokup a přetoky,
- procentuální pokrytí spotřeby sdílenou elektřinou,
- využití přetoku výrobny za poslední dostupný den, tento týden, měsíc, rok a celkem,
- nastavitelná prodejní cena v Kč/kWh,
- výpočet hodnoty nasdílené elektřiny jako `nasdílené kWh × prodejní cena`,
- automatické stažení profilových dat za předchozí a aktuální kalendářní měsíc,
- hodinová i denní historie vypočtená ze zdrojových intervalů EDC,
- ruční dohledání a doplnění dostupné historie EDC až jeden kalendářní rok zpět,
- hodinová aktualizace a podpora dlouhodobých statistik Home Assistantu,
- ruční pokus o okamžité načtení dat a diagnostika posledního i příštího pokusu,
- opětovné zadání hesla, pokud EDC uložené údaje odmítne,
- samostatné diagnostické entity pro všechny sdílející i cílové EANy ve skupině,
- samostatné zařízení a hodnoty pro každý cílový EAN, s volitelným vlastním názvem, lokalitou a prodejní cenou,
- ruční i automatické denní, týdenní, měsíční a roční reporty na jednu nebo více e-mailových adres,
- volba češtiny nebo angličtiny pro předmět i obsah e-mailových reportů,
- souhrnný report se všemi čtyřmi obdobími v jediném e-mailu.
- volitelná QR platba podle českého formátu SPAYD pro úplný měsíční nebo roční report s kladnou částkou.

> [!IMPORTANT]
> Hodnota sdílení neodečítá investiční ani provozní náklady a nepředstavuje čistý zisk. Jde o hodnotu skutečně nasdílené energie při nastavené ceně.

## Instalace přes HACS

1. V HACS otevřete **Integrace**.
2. V nabídce zvolte **Vlastní repozitáře**.
3. Přidejte `https://github.com/79thales/edc-sharing-stats` jako typ **Integrace**.
4. Vyhledejte a nainstalujte **EDC Sharing Stats**.
5. Restartujte Home Assistant.
6. Otevřete **Nastavení → Zařízení a služby → Přidat integraci** a vyhledejte **EDC Sharing Stats**.

### Počet stažení

Odznaky nahoře ukazují **stažení instalačního ZIPu celkem** a **stažení posledního vydání**. Od v0.1.32 vydání poskytují přílohu `edc_sharing.zip`, kterou používá také HACS. Horní ikona stažení v HACS patří vybranému vydání, nikoli součtu všech verzí.

Počítadla zahrnují opakovaná stažení a aktualizace, nejde tedy o počet uživatelů nebo aktivních instalací. Nezahrnují stažení zdrojového kódu, instalace výchozí větve ani starší vydání bez instalační přílohy. Hodnoty se mohou zobrazit se zpožděním kvůli cache. Integrace kvůli tomu neposílá žádnou telemetrii.

## Ruční instalace

Zkopírujte adresář `custom_components/edc_sharing` do adresáře `custom_components` ve své konfiguraci Home Assistantu a Home Assistant restartujte.

U vydání s přílohou `edc_sharing.zip` lze místo toho rozbalit její obsah přímo do `custom_components/edc_sharing`. Soubor `manifest.json` musí být přímo v tomto adresáři, nikoli v další vnořené složce. Automatický GitHub archiv **Source code (zip)** má odlišnou strukturu a není instalační přílohou HACS.

## Nastavení

Průvodce vyžaduje:

- e-mail a heslo k portálu EDC,
- skupinu sdílení dostupnou danému účtu,
- prodejní cenu elektřiny v Kč/kWh.

Skupinu a cenu lze později změnit přes **Nastavení → Zařízení a služby → EDC Sharing Stats → Nastavit**. Přístupový i obnovovací token zůstává pouze v paměti; po restartu se integrace přihlásí znovu uloženými přístupovými údaji.

Pokud účet obsahuje více skupin sdílení, lze integraci přidat opakovaně a při každém nastavení vybrat jinou skupinu podle názvu vráceného EDC. Každý nalezený sdílející a cílový EAN má vlastní diagnostickou entitu se stavem obsahujícím celé číslo EAN. Entit může být na obou stranách libovolný počet.

### Detaily jednotlivých EANů

EAN se nezadávají ručně. Stiskněte na zařízení skupiny **Načíst data EDC nyní**; integrace z aktuální odpovědi EDC automaticky zjistí všechny sdílející a cílové EANy. Potom otevřete **Nastavení → Zařízení a služby → EDC Sharing Stats → Nastavit → Detaily EAN a ceny** a vyberte EAN.

Pro každý EAN lze uložit vlastní **zobrazovaný název** a **lokalitu**. Tyto údaje jsou vidět u diagnostické entity; u cílového EANu také pojmenují jeho samostatné zařízení a objeví se v cíleném reportu. Lokalita je popisek integrace, nikoli automatické přiřazení oblasti Home Assistantu — skutečnou oblast lze nadále vybrat běžně v registru zařízení.

U každého **cílového** EANu lze ponechat prodejní cenu celé skupiny, nebo ji nahradit vlastní cenou. Vlastní cena ovlivní pouze nové individuální senzory a reporty daného cílového EANu. Stávající skupinové senzory, jejich hodnota sdílení a původní tlačítka reportů vždy používají beze změny výchozí cenu skupiny.

## E-mailové reporty

### Datum jednotlivých míst a předměty e-mailů

V profilu s rozsahem cílových EANů lze zvolit **Datum denního reportu cílových EANů → Poslední dostupný den každého EANu**. Každé místo pak použije nejnovější den ze své uložené historie a v reportu uvede jeho datum. Místa mohou mít rozdílná data; nejde o součet za společný den. EAN bez uložených dat zůstane označený jako nedostupný. Výchozí volba **Poslední den celé skupiny** zachovává dosavadní chování. Skupinové finanční souhrny nadále porovnávají shodné kalendářní dny.

Předmět samostatného reportu obsahuje název profilu, skupinu nebo odběrné místo, typ reportu a datum či rozsah období, například `EDC | Majitel | Chata | Denní: 2026-09-14`. U více míst se zobrazí jejich počet; souhrnný e-mail uvádí vybrané typy období. Názvy míst respektují nastavené zobrazení EANů. Souhrn s jediným obdobím používá konkrétní datum stejně jako samostatný report.

Target report profiles can optionally use each EAN's latest cached day, with an explicit date per supply point. The default remains the latest group day. Profile email subjects now include the profile name, supply-point or group scope and report period; multi-period summaries list their included period types.

V profilu s rozsahem **Celá skupina** lze zvolit **Výpočet financí celé skupiny**:

- **Výchozí cena skupiny** zachovává dosavadní výpočet nasdílené energie cenou skupiny.
- **Součet podle cen jednotlivých EANů** přidá rozpis nasdílené energie, použité ceny a částky pro každé odběrné místo. EAN bez vlastní ceny použije cenu skupiny. Celková částka se potvrdí pouze tehdy, když součet individuální nasdílené energie souhlasí s hodnotou skupiny v každém zahrnutém dni; jinak je rozpis označený jako částečný. Kontrola neověřuje úplnost intervalů uvnitř dne. Ceny jsou aktuálně nastavené ceny, nikoli historický ceník.

Přehled profilů ukazuje příjemce, rozsah celé skupiny nebo konkrétní vybraná odběrná místa a zvolený výpočet skupinových financí. **Všichni příjemci jednoho profilu dostávají stejný obsah.** Pro příjemce, který smí vidět pouze své odběrné místo, vytvořte samostatný profil s jeho EANem.

Group report profiles can optionally calculate financial totals using individual target EAN prices, with a per-supply-point breakdown. The default remains the group price. Totals are confirmed only when individual shared energy matches group data for every included day; this does not verify intraday interval completeness. Prices are the current configured prices. The profile overview shows recipients and supply-point scope; all recipients of one profile receive the same content.

### QR platba v měsíčních a ročních reportech

Pro každou skupinu lze v **Nastavit → Účet pro QR platby** uložit české číslo účtu a čtyřmístný kód banky. Volitelné předčíslí účtu se zadává ve tvaru `předčíslí-číslo`; IBAN se pro QR platbu dopočítá lokálně. Tento účet patří právě otevřené skupině a při změně skupiny v obecném nastavení se z bezpečnostních důvodů odstraní.

Potom v konkrétním profilu zapněte **Přiložit výzvu k platbě QR kódem**. QR obsahuje lokálně vytvořený text SPAYD 1.0, částku v Kč, účet skupiny a zprávu s obdobím. U profilu jednotlivého odběrného místa uvádí také jeho místní název, lokaci (je-li nastavená) a celý cílový EAN. V e-mailu SMTP je QR vložen přímo do HTML obsahu, bez přílohy. Žádný údaj se neposílá službě pro generování QR kódů.

Výzva k platbě vznikne pouze tehdy, když je hodnota sdílení kladná a jsou zapnuté finance. Měsíční report vyžaduje **úplný kalendářní měsíc**. U aktuálního ročního reportu lze vytvořit QR za souvislou řadu dostupných denních dat v daném roce; zpráva pro příjemce proto uvádí přesný konec, případně začátek i konec tohoto rozsahu. Denní, týdenní, nulové a roční reporty s mezerou v denních datech QR platbu úmyslně neobsahují. U skupinového součtu podle individuálních cen EANů musí být navíc potvrzena shoda individuálních denních hodnot se souhrnem skupiny. Pro konečný měsíční nebo roční výkaz proto obvykle zvolte rozsah **Uzavřené období**.

U profilu typu **Vybraná odběrná místa** obsahuje zpráva QR platby místní název, lokaci (je-li nastavená) a celý cílový EAN — i když je běžné zobrazení EANu v reportu skryté nebo maskované. Tyto údaje se nepíší do logu ani trvalého úložiště reportů. U souhrnného QR za skupinu s více odběrnými místy zůstává zpráva skupinová, protože jedna částka nejde pravdivě přiřadit jedinému EANu.

> **Pozor:** QR pro aktuální rok obsahuje hodnotu za uvedený průběžný rozsah dat, nikoli doplatek po dřívějších měsíčních platbách. Integrace nevede evidenci úhrad; měsíční a roční QR proto pro stejného plátce zapínejte jen tehdy, když je jejich souběh záměrný.

QR platba vyžaduje Home Assistant **2026.8 nebo novější** a příjemce z integrace **SMTP**; ostatní reporty i běžné `notify.send_message` zůstávají beze změny. QR PNG vzniká jen v paměti a žádný soubor se do Home Assistantu neukládá.

### Samostatné profily příjemců a rozvrhů

Otevřete **Nastavení → Zařízení a služby → EDC Sharing Stats → Nastavit → Profily reportů → ＋**.
Zadejte název profilu, jeho příjemce (`notify` entity vytvořené v SMTP), jazyk a vyberte období.
Nový profil je zpočátku pozastavený; přepínačem **Automatické odesílání zapnuto** zapnete jeho rozvrh.

Po otevření **Profilů reportů** se zobrazí společný přehled všech profilů: zapnuto/pozastaveno, příjemci, vybraná období a jejich rozsah, společný či samostatný e-mail, jazyk, rozvrh a poslední i příští pokus o odeslání. U příjemců jsou uvedeny názvy i identifikátory `notify` entit; chybějící nebo nedostupná entita je označená. Časy se zobrazují v časovém pásmu HA. Přehled se obnovuje opětovným otevřením; nic neodesílá ani nestahuje z EDC. Z detailu profilu se vrátíte volbou **Zpět na přehled profilů**.

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
| Rozsah reportu | Celá skupina zachovává původní souhrn; vybrané cílové EANy přidají samostatnou část pro každé vybrané odběrné místo |
| Cílové EANy | Použijí se jen pro rozsah cílových EANů; pro jiné příjemce vytvořte další profil |

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

Report s rozsahem **Celá skupina** počítá původní hodnoty za celou zvolenou skupinu. Report s rozsahem **Vybrané cílové EANy** počítá samostatně spotřebu, nasdílenou energii, dokup ze sítě, pokrytí a hodnotu pro každý vybraný cílový EAN. Přetok výrobny a nevyužitý přetok jsou fyzikální hodnoty celé výrobní strany skupiny, proto se do individuálního reportu příjemce úmyslně nepřisuzují.

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
- nastavená prodejní cena,
- využití přetoku za poslední dostupný den, tento týden, měsíc, rok a celou uloženou historii.

Integrace vytváří 19 základních hodnotových senzorů. Nejde o duplicity: šest patří poslednímu dni dostupnému v EDC, sedm aktuálnímu měsíci, jeden představuje nastavenou prodejní cenu a pět zobrazuje využití přetoku v různých obdobích. Každý senzor má vlastní jedinečný identifikátor a lokalizovaný název. U šesti denních senzorů atribut `data_date` uvádí skutečné datum měření; EDC obvykle zveřejňuje vyhodnocení se zpožděním, takže nemusí jít o dnešní datum.

Pro každý cílový EAN, který EDC vrátí, navíc vznikne samostatné zařízení s 11 hodnotami: nasdíleno, spotřeba, dokup, pokrytí a hodnota za poslední dostupný den i za aktuální měsíc a vlastní/zděděná prodejní cena. Měsíční hodnoty obsahují atributy skutečného dostupného rozsahu a cenu použitou ve výpočtu. Stabilní `unique_id` obsahuje ID skupiny, EAN a název hodnoty; uživatel si může výsledné `entity_id` v Home Assistantu dále upravit. Cílové EANy nemají vlastní senzor přetoku výrobny ani nevyužitého přetoku, protože tyto hodnoty patří celé výrobní straně skupiny.

**Pokrytí spotřeby** udává, kolik procent spotřeby příjemce pokryla sdílená elektřina (`nasdíleno / spotřeba`). **Využití přetoku** naproti tomu udává, kolik procent celkového přetoku výrobny bylo skutečně využito pro sdílení (`nasdíleno / přetok výrobny`). Při nulovém nebo záporném přetoku je hodnota `0 %`, stejně jako u stávajících procentních výpočtů s nulovým jmenovatelem. Výpočet používá nezaokrouhlené agregované hodnoty a UI doporučuje jedno desetinné místo.

Každý senzor využití přetoku obsahuje diagnostické atributy `shared_kwh`, `production_surplus_kwh`, `unused_surplus_kwh`, `data_start`, `data_end` a `available_days`. Hodnoty pro rok a celkem se počítají ze všech denních dat, která integrace dosud načetla a uložila; u nové instalace se rozsah rozšíří po spuštění ročního backfillu. Opakované načtení stejného dne uložený den nahradí, takže nedochází k dvojímu započtení.

Nové entity používají stabilní koncovky `surplus_utilization_latest_available_day`, `surplus_utilization_this_week`, `surplus_utilization_this_month`, `surplus_utilization_this_year` a `surplus_utilization_total`. Například pro zařízení `Dvořák osady ležáku 64` vzniknou entity ve tvaru `sensor.dvorak_osady_lezaku_64_surplus_utilization_…`; konkrétní ID lze po vytvoření ověřit a případně uživatelsky přejmenovat v registru entit Home Assistantu.

Navíc vzniká diagnostický časový senzor **Poslední pokus o načtení dat**. Jeho stav uvádí okamžik posledního pokusu; atributy `result`, `last_success`, `next_attempt` a `error` ukazují výsledek, poslední úspěšné načtení, očekávaný další automatický pokus a případnou chybu. Diagnostický senzor zůstává dostupný i tehdy, když se samotné načtení nezdaří.

Přímo v diagnostické části zařízení jsou také entity **Stav stahování historie** a **Data EDC dostupná od**. První viditelně ukazuje stav `Nespuštěno`, `Probíhá`, `Pozastaveno`, `Selhalo` nebo `Dokončeno`; po otevření entity jsou v atributech procenta postupu, prohledávaný rozsah, počet importovaných dnů a hodin i případná chyba. Druhá entita ukazuje nejstarší datum skutečně nalezené v odpovědích EDC; dokud stav není `Dokončeno`, může se při hledání posouvat dále do minulosti. Podrobné atributy `history_backfill_*` zůstávají také u senzoru posledního pokusu kvůli zpětné kompatibilitě.

Stejných šest senzorů uvádí v atributech také `daily_statistic_id` a `hourly_statistic_id`. Uživatel tak může přesné identifikátory své skupiny rovnou zkopírovat do karty **Graf statistik**, aniž by ručně hledal interní číslo skupiny.

## Historie a dlouhodobé statistiky

Při načtení integrace se automaticky stáhnou profilová data od prvního dne předchozího kalendářního měsíce do současnosti. EDC povoluje v přehledu nejvýše 31 dní, proto integrace delší období sama rozdělí na několik požadavků a výsledky sloučí bez duplicit. Zdrojové intervaly se sečtou po jednotlivých hodinách i kalendářních dnech. Jednou denně se celé období znovu načte, takže se doplní nově uzavřené intervaly i případné opravy na straně EDC.

Historické hodnoty celé skupiny se zapisují podporovaným API jako externí dlouhodobé statistiky. Nevytvářejí falešné zpětně datované změny stavů v databázi Recorderu. Denní řady mají identifikátory ve tvaru `edc_sharing:<ID skupiny>_shared_daily`, `consumption_daily`, `grid_daily`, `unused_daily`, `coverage_daily` a `revenue_daily`. Stejné názvy s koncovkou `_hourly` obsahují hodinové hodnoty. Lze je vybrat v panelu Historie nebo v kartě **Graf statistik**; zobrazovaným typem je `mean`.

Denní agregace cílových EANů se při běžném načtení i při backfillu uchovávají v interní cache integrace. Díky tomu po restartu zůstávají individuální hodnoty za měsíc, rok a celkem správné pro reporty. Samostatné externí dlouhodobé statistiky pro každý cílový EAN tato verze nevytváří; existující dlouhodobé statistiky skupiny se tím nemění.

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
- Volitelné názvy, lokality a vlastní ceny EANů jsou uloženy v možnostech integrace a mohou být součástí záloh Home Assistantu. Název a lokalita se zobrazí na zařízení a mohou být zahrnuty v cíleném reportu.
- Volitelný účet QR platby je uložen v možnostech konkrétní skupiny a může být součástí záloh Home Assistantu. IBAN a QR obrázek se z něj vytvářejí lokálně pouze při odesílání; dočasný QR soubor se po předání SMTP odstraní.
- E-mailové reporty obsahují název skupiny a zvolené hodnoty. Nové profily standardně maskují EAN; celé EAN obsahují původní reporty a profily s výslovně zapnutým úplným zobrazením. Odesílají se výhradně přes vybrané Home Assistant `notify` entity; používejte pouze důvěryhodné příjemce a SMTP server.

## Podpora

Chyby a návrhy hlaste v [GitHub Issues](https://github.com/79thales/edc-sharing-stats/issues).

Tento projekt není oficiálním produktem ani podporovanou integrací Elektroenergetického datového centra, a. s.
