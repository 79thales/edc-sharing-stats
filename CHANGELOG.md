# Přehled změn / Changelog

## 0.2.0 – 2026-10-07

### Čeština

- Přidány hodinové externí statistiky pro každé odběrné místo: nasdílená energie, spotřeba, dokup ze sítě a pokrytí sdílením. ID obsahuje skupinu i EAN, aby stejné místo v různých skupinách nekolidovalo. Atribut `hourly_statistic_id` příslušného senzoru odkazuje na novou statistiku. Starší historii lze doplnit opětovným spuštěním backfillu.
- Hodnoty představují jednotlivé hodiny EDC, nikoli kumulativní čítače nebo živý výkon. Import pracuje s UTC, rozlišuje opakovanou hodinu při změně času a nahrazuje stejné časové body místo jejich přičítání. Stávající Energy statistiky a jejich denní příjmy se nemění.
- Kredit za základ hodinových statistik jednotlivých míst patří [@jirisida](https://github.com/jirisida), fork `feature/target-hourly-history`; doplněno oddělení skupin a ochrana překrývajících se importů.
- QR platba je nově viditelná také v náhledu vyúčtování, ještě před vystavením. Používá účet skupiny a zbývající částku po odečtení pouze ručně potvrzených úhrad; období a identifikace odběratele/EANu odpovídají zvolenému rozsahu.
- Náhled QR není finální výzva k úhradě: nemá variabilní symbol a u obrázku je výslovné upozornění **Neplaťte podle tohoto náhledu**. Finální QR s variabilním symbolem vzniká až po potvrzení vystavení. Náhled nic neukládá, nerezervuje číslo dokladu a neposílá e-mail.
- Bez nastaveného účtu, při nulovém zůstatku, neúplných datech nebo nejednoznačně přiřazené úhradě se QR v náhledu nevytváří. QR nadále vzniká lokálně v paměti, bez externí služby nebo souboru.
- Doplněny regresní testy částky, částečných/potvrzených úhrad, překryvů a českého/anglického upozornění i reálné HA testy PNG a náhledu bez zápisů. CI instaluje deklarované závislosti integrace; testy minimální HA verze běží nezávisle na dostupnosti fixtures pro nejnovější stabilní HA. Kontrola nejnovější verze zůstává povinná, bez náhrady starší nebo beta verzí.
- Vystavené doklady, jejich QR a variabilní symboly, uložená historie, stávající reporty, statistiky a ID entit zůstávají beze změny.

### English

- Added per-target hourly external statistics for shared electricity, consumption, grid import and sharing coverage. IDs include both the group and EAN to avoid collisions across groups. The corresponding sensor exposes an `hourly_statistic_id` attribute. Run history backfill again to populate older periods.
- Values describe individual EDC hours, not cumulative counters or live power. Imports use UTC, distinguish repeated DST hours and replace matching timestamps instead of adding them again. Existing Energy statistics and daily income booking are unchanged.
- Credit to [@jirisida](https://github.com/jirisida) for the per-target hourly statistics foundation in `feature/target-hourly-history`; this integration adds group-scoped IDs and safeguards for overlapping imports.
- Payment QR codes now appear in settlement previews before issue. They use the group's bank account and the remaining balance after deducting only manually confirmed receipts, with the selected period and customer/EAN reference.
- The preview QR is not a final payment request: it has no variable symbol and is explicitly labelled **Do not pay from this preview**. The final QR receives its variable symbol only after issue is confirmed. Previewing does not save anything, reserve a document number or send email.
- Preview QR generation is suppressed when no account is configured, the balance is zero, daily data is incomplete or a receipt allocation is ambiguous. Images continue to be generated locally in memory, without external services or files.
- Added regressions for amounts, partial/confirmed receipts, overlapping periods and Czech/English warnings, plus real HA tests of PNG generation and read-only previews. CI installs declared integration dependencies, and minimum-version HA tests run independently of fixture availability for the latest stable HA. Latest-version validation remains required, with no older or beta substitution.
- Issued documents, their QR codes and variable symbols, retained history, existing reports, statistics and entity IDs are unchanged.

## 0.1.37 – 2026-10-07

### Čeština

- Opraveno nechtěné přesměrování ozubeného kola na generátor dashboardu. Generátor ani platby už nejsou registrované jako náhrada hlavní konfigurace EDC; **Konfigurovat** znovu otevře společné menu nastavení konkrétní skupiny.
- Generátor a **Platby a vyúčtování** zůstávají volbami v tomto menu. Tlačítko generátoru na zařízení skupiny je zachovaná rychlá zkratka, nikoli výchozí dashboard domácnosti. Oba pomocné panely zůstávají skryté z postranního menu a přístupné pouze správci.
- Přidán regresní test původní chybné registrace a reálné HA testy metadat panelů i nativního menu pro dvě nezávislé skupiny, včetně správného odkazu na každou instanci a návratu bez změn options.
- Bez změn ID entit, údajů konfigurace, credentials, reportů, plateb, EDC komunikace, statistik nebo uložené historie. Starší releasy a jejich instalační balíčky se nepřepisují.

### English

- Fixed the Configure button unexpectedly opening the dashboard generator. Neither helper panel now overrides the EDC configuration route; **Configure** opens the selected sharing group's common options menu again.
- The dashboard generator and **Payments and settlements** remain available from that menu. The group-device generator button is retained as a shortcut, not the home's default dashboard. Both helper panels remain hidden from the sidebar and restricted to administrators.
- Added a regression for the original incorrect registration and real HA tests verifying panel metadata and native options flows for two independent sharing groups, including entry-specific links and returning without changing options.
- Entity IDs, configuration data, credentials, reports, payments, EDC requests, statistics and retained history are unchanged. Previous releases and installer assets are preserved.

## 0.1.36 – 2026-10-07

### Čeština

- Opraven chybějící návrat z generátoru dashboardu: vlevo v hlavičce je nyní šipka **Zpět do integrace**, která vždy otevře stránku EDC. Funguje i na mobilu a při otevření přímým odkazem, bez závislosti na historii prohlížeče.
- Stejný návrat je i v **Platby a vyúčtování**. Hlavička zůstává při posunu viditelná, nabídka HA je vpravo. Odkaz zůstává dostupný i při načítání, chybě spojení nebo chybějících skupinách/profilech.
- Přidány JavaScript regresní testy skutečné inicializace panelů, českých/anglických popisků a zachování návratu a HA testy načtení nových frontendových modulů. Návrat sám nic nevytváří, nevystavuje ani neodesílá, ale nezruší již potvrzenou a zahájenou operaci; rozpracovaný YAML je potřeba před odchodem zkopírovat nebo stáhnout.
- Pouze oprava navigace, bez změn generování dashboardů, reportů, evidence plateb, dat EDC, ID entit, konfigurace nebo historie. Zvýšení verze také obnoví verzované odkazy na frontendové moduly.

### English

- Fixed the missing return navigation in the dashboard generator. A **Back to integration** arrow on the left of the header always opens the EDC integration page, including on mobile and direct entry, without relying on browser history.
- Added the same return link to **Payments and settlements**. The header stays visible while scrolling, with the HA menu on the right. Returning remains available during loading, connection errors and missing groups/profiles.
- Added JavaScript regressions exercising actual panel initialization, Czech/English labels and persistent return navigation, plus HA tests loading the updated frontend modules. Returning does not initiate creation, issue or sending, but does not cancel an already confirmed, in-progress operation; copy or download generated YAML before leaving.
- Navigation-only fix: dashboard generation, reports, the payment ledger, EDC data, entity IDs, configuration and history are unchanged. The version bump also refreshes versioned frontend module URLs.

## 0.1.35 – 2026-10-07

### Čeština

- Nová samostatná administrátorská sekce **Platby a vyúčtování**. Nejprve musí existovat uložený profil reportů; přebírají se jeho příjemci, jazyk, EANy a finanční rozsah. Pro soukromé osoby vzniká **Vyúčtování sdílené elektřiny**, nikoli automatický daňový doklad nebo potvrzení banky.
- Náhled a výslovné vystavení za poslední měsíc, aktuální rok nebo vlastní období od–do včetně. Používají se jen uložené denní součty; chybějící/nekonzistentní data blokují konečné vystavení. Nejde o ověření úplnosti každého intervalu EDC. Doklad dostane pevné číslo, variabilní symbol a podklady; již vystavené dny se po změně ceny nebo opravě EDC samovolně nepřepočítají.
- Volitelné ruční potvrzování úhrad je výchozím stavem vypnuté. **Vystavení ani odeslání není platba. Odečítají se jen potvrzené úhrady; nepotvrzené částky se stále nabízejí k zaplacení i v ročním vyúčtování.** Hodnota 1 000 Kč a potvrzeno 400 Kč znamená zůstatek/QR 600 Kč; bez potvrzení zůstává k zaplacení 1 000 Kč.
- Měsíční, roční a vlastní překrývající se doklady odkazují na stejné unikátní položky EAN/den. Opakovaná výzva nevytváří další dluh. U částečných úhrad se rozdělení mezi menší období nebo EANy neodhaduje; nejednoznačné přiřazení blokuje vystavení/QR. Chybné ruční potvrzení lze zrušit se zachováním auditního záznamu.
- Nezaokrouhlená energie a hodnota zůstávají zachované. Haléře se přidělí denním položkám jednou při prvním vystavení za daný EAN; překrývající se doklady je znovu nezaokrouhlují, aby potvrzený haléř nevznikl podruhé jako doplatek.
- Výslovné odeslání přes SMTP profil obsahuje celé vyúčtování a QR zbývající částky přímo v těle e-mailu, nikoli QR přílohu. Předání SMTP není potvrzené doručení. Tiskové HTML lze stáhnout nebo uložit do PDF pomocí prohlížeče; serverové PDF přílohy se nevytvářejí. Všichni příjemci jednoho profilu dostanou stejný obsah; změněný/odstraněný profil blokuje odeslání starého dokladu.
- Oddělené versionované privátní HA úložiště, pouze správce, revize a potvrzení náhledu, atomické zápisy a ochrana opakovaných operací. Nečitelné úložiště se automaticky nemaže/resetuje. Osobní údaje v dokladech zůstávají lokální a mohou být součástí HA záloh.
- Bez změn stávajících reportů, jejich plánování, EDC požadavků, cenového chování senzorů, Energy statistik, ID entit, credentials a uložené historie. Nic se automaticky nevystavuje ani nepotvrzuje jako zaplacené. Přidány finanční, JavaScript a reálné HA fixture regresní testy pro minimum i dynamicky zjištěný latest stable.

### English

- Added an independent, administrator-only **Payments and settlements** section. An explicitly saved report profile is required first; its recipients, language, EAN scope and financial mode are reused. Documents are private electricity-sharing settlements, not automatically generated tax invoices or bank confirmations.
- Preview and explicitly issue the previous month, current year or an inclusive custom date range using cached daily totals only. Missing/inconsistent daily data blocks final issue; this does not verify every intraday EDC interval. Documents receive a stable number, variable symbol and frozen source data; previously issued days are not silently recalculated after price changes or EDC corrections.
- Optional manual payment tracking is off by default. **Issuing and sending are not payment. Only confirmed receipts are deducted; unconfirmed amounts remain offered for payment, including annual settlements.** CZK 1,000 minus a manually confirmed CZK 400 leaves CZK 600 payable/in the QR; without confirmation, the full CZK 1,000 remains offered.
- Monthly, annual and custom overlapping documents reference the same unique EAN/day charges. Repeated reminders never create additional debt. Partial receipts are not guessed across smaller periods or EAN selections; ambiguous allocation blocks issue/QR. Incorrect manual confirmations can be reversed while preserving the audit trail.
- Unrounded energy and raw value are retained. Cents are assigned to daily charges once on first issue per EAN; overlapping statements do not independently round them again or turn an already confirmed cent into a new payable balance.
- Explicit SMTP sending puts the full settlement and QR for the remaining balance in the email body, not a QR attachment. SMTP handoff does not certify inbox delivery. Download printable HTML or use the browser's Save as PDF; no server-generated PDF attachment is created. All recipients of one profile receive the same content; changed/deleted routing blocks sending old documents.
- Separate versioned private HA storage, administrator-only access, revision/preview checks, atomic saves and retry protection. Unreadable storage is never automatically deleted/reset. Personal document data remains local and may be included in HA backups.
- Existing reports/schedules, EDC requests, sensor pricing behavior, Energy statistics, entity IDs, credentials and history are unchanged. Nothing is automatically issued or marked paid. Added financial, JavaScript and real HA fixture regressions for the minimum and dynamically resolved latest stable release.

## 0.1.34 – 2026-10-07

### Čeština

- Nové konfigurační tlačítko a položka nastavení **Vygenerovat dashboard** nabídnou odkaz na administrátorský generátor ve stylu EDC Share2.
- Vlastní název a adresa, výběr skupiny, čeština/angličtina, volitelné jednotlivé cílové EANy, detaily a tabulka Energy. YAML lze kopírovat i stáhnout; přímé založení nového dashboardu vyžaduje náhled a potvrzení správce.
- Skutečná ID přejmenovaných entit se načítají z veřejného registru. Vypnuté či dosud chybějící senzory se vynechají. Historické grafy používají původní data externích statistik EDC místo času aktualizace senzoru.
- Jen nativní Lovelace karty a API přihlášeného správce, bez dalších tokenů, externího generování a přímých zásahů do `.storage`. Existující dashboardy se nepřepisují; při neúplném uložení zůstává nově založený dashboard i export YAML zachovaný.
- Beze změn cen, reportů, datové komunikace EDC, statistik, stávajících ID entit a uložené historie. Přidány unit/JavaScript testy a reálné HA fixture testy pro minimum 2026.8.0 i dynamicky zjištěný latest stable s přesně odpovídajícím testovacím pluginem.

### English

- Added a **Generate dashboard** configuration button and settings action, linking to an administrator-only generator in the EDC Share2 style.
- Custom name and URL path, sharing-group and language selection, optional individual supply points, details and Energy table. YAML can be copied or downloaded; direct creation requires a preview and explicit administrator confirmation.
- Actual entity IDs, including user renames, are resolved through the public entity registry. Disabled or not-yet-created sensors are omitted. History charts use original EDC external-statistic dates rather than sensor update times.
- Native Lovelace cards and the signed-in administrator's API only: no extra tokens, external generation service or direct `.storage` edits. Existing dashboards are never overwritten; an incomplete save preserves the newly created dashboard and the YAML fallback.
- No changes to pricing, reports, EDC requests, statistics, existing entity IDs or retained history. Added unit/JavaScript tests and real HA fixture tests for minimum 2026.8.0 and dynamically resolved latest stable, each with an exactly matching test plugin.

## 0.1.33 – 2026-10-07

### Čeština

- Jednotné odznaky Home Assistant, HACS, Release, Downloads total, Downloads latest a Validation jsou nyní součástí vydaného tagu, nejen hlavní větve.
- Absolutní odkazy na loga a jednotná šířka 180 px pro správné zobrazení README v HACS.
- HACS zobrazuje dokumentaci nainstalované verze. Pro nový vzhled aktualizujte integraci na toto vydání; samotné obnovení cache staré README nezmění.
- Regresní kontrola úplné hlavičky README v release CI a kontrola kompatibility s přesně zjištěnou nejnovější stabilní verzí Home Assistantu.
- Bez změn funkční logiky, ID entit, nastavení nebo uložených dat. Staré tagy a ZIPy zůstávají zachované včetně počtů stažení.

### English

- The unified Home Assistant, HACS, Release, Downloads total, Downloads latest and Validation badges are now included in the release tag, not only the default branch.
- Absolute logo URLs and a consistent 180 px width fix README rendering in HACS.
- HACS displays documentation for the installed version. Update to this release to see the new header; refreshing the cache alone does not change an older release's README.
- Added a release CI regression for the complete README header and a compatibility check against the exact latest stable Home Assistant version.
- No changes to functional behavior, entity IDs, configuration or retained data. Existing tags and ZIP assets remain intact, preserving their download counts.

## 0.1.32 – 2026-10-07

### Čeština

- Instalační balíček `edc_sharing.zip` pro HACS a automatické odznaky stažení celkem i posledního vydání v README. Počítají pouze stažení instalačního balíčku včetně aktualizací, nikoli unikátní uživatele. Počítání začíná tímto vydáním; starší stažení bez přílohy nelze zpětně dopočítat.
- Horní počítadlo v HACS se vztahuje k vybranému vydání, zatímco odznak celkových stažení sčítá instalační balíčky všech vydání. Stažení zdrojového kódu, instalace výchozí větve ani ukázkové dashboardy se do odznaků nezapočítávají. Starší vydání si zachovávají původní způsob instalace.
- Nový postup vydávání vytváří ZIP pouze z verzovaných souborů integrace a nejdříve jej přiloží ke konceptu vydání. Kontroluje shodu verze s tagem, strukturu balíčku a bilingvní poznámky. Již zveřejněné přílohy nepřepisuje, aby neztratil jejich počty stažení.
- Bez změn entit, nastavení integrace, statistik nebo uložených dat; bez přidání telemetrie.

### English

- A HACS installer asset, `edc_sharing.zip`, and automatic README badges for total and latest-release installer downloads. Counts cover only installer downloads, including updates, not unique users. Counting starts with this release; downloads from older releases without an installer asset cannot be recovered.
- HACS's download indicator refers to the selected release, while the total badge combines installer downloads across releases. Source-code downloads, default-branch installations and sample dashboards are not counted by the badges. Older releases retain their original installation method.
- The release workflow packages only committed integration files and attaches the installer to a draft release before publication. It checks the tag against the manifest version, validates the archive layout and extracts bilingual release notes. Published assets are never overwritten, preserving their download counts.
- No changes to entities, integration options, statistics or retained data, and no added telemetry.

## 0.1.31 – 2026-10-05

### Čeština

- Volitelný výběr placených cílových EANů pro Energy dashboard, s individuálními cenami a samostatnými i společnými součtovými statistikami příjmu a placené sdílené energie.
- Zpožděná denní data se zapisují ke skutečnému dni EDC. Součty se obnovují z uložené historie také po restartu, opravách dat a doplnění starších období.
- V nastavení integrace otevřete „Příjem ze sdílení v Energy dashboardu“. Vyberte placená místa a v Energy zvolte jejich společnou nebo jednotlivou externí statistiku příjmu. Výchozí výběr je prázdný.
- Denní příjem se účtuje do poslední hodiny dne; hodinový graf nepředstavuje skutečný průběh příjmu. Změna ceny přepočítá dostupnou historii. Po změně výběru míst zvolte novou společnou statistiku v Energy.

### English

- Optional paid-target selection for the Energy dashboard, using individual prices and separate per-target and combined cumulative statistics for sharing income and paid shared energy.
- Delayed daily values are assigned to their actual EDC day. Totals are rebuilt from retained history after restarts, revised data and older history backfill.
- Open "Sharing income in the Energy dashboard" in the integration options. Select paid supply points and choose their combined or individual external income statistic in Energy. The default selection is empty.
- Daily income is booked in the day's final hour; the hourly chart does not represent an actual hourly income profile. Price changes recalculate available history. After changing the selected targets, select the new combined statistic in Energy.

## 0.1.30 – 2026-10-03

### Čeština

- Integrace se nyní úspěšně spustí i u nového sdílení, pokud EDC ve starším bloku úvodního dvouměsíčního načítání ještě nevrací výrobní i odběrný EAN. Neúplný historický blok se pouze přeskočí; kompletní novější data se nadále načtou.
- Děkujeme [@jirisida](https://github.com/jirisida) za nahlášení a návrh opravy v PR [#6](https://github.com/79thales/edc-sharing-stats/pull/6).

### English

- The integration now starts successfully for a newly active sharing group when an older block in the initial two-month refresh does not yet contain both the production and target EANs. The incomplete historical block is skipped while complete recent data continues to load.
- Thanks to [@jirisida](https://github.com/jirisida) for reporting the issue and proposing the fix in PR [#6](https://github.com/79thales/edc-sharing-stats/pull/6).

## 0.1.29 – 2026-10-03

### Čeština

- Cílová odběrná místa nyní používají aktuální Home Assistant API `via_device_id` pro vazbu na skupinu sdílení. Odstraňuje to deprekační varování a zachovává strom zařízení i v budoucích verzích Home Assistantu.

### English

- Target supply-point devices now use Home Assistant's current `via_device_id` API to link to their sharing group. This removes the deprecation warning while preserving the device hierarchy for future Home Assistant releases.

## 0.1.28 – 2026-10-01

### Čeština

- QR platba nyní podporuje také průběžný aktuální rok, pokud jsou dostupná souvislá denní data. Zpráva v QR uvádí přesný rozsah dat.
- U profilů jednotlivých odběrných míst obsahuje zpráva QR lokální název, lokaci a celý cílový EAN; společný QR za skupinu s více místy zůstává skupinový.

### English

- QR payments now also support the current year when a continuous range of daily data is available. The QR reference states the exact covered range.
- Target-specific QR references include the local name, location and full target EAN; a shared QR for a multi-target group remains group-level.

## 0.1.27 – 2026-09-28

### Čeština

- Stabilizační vydání: testování QR e-mailu již nevyžaduje lokálně nainstalovaný QR balíček v běžném validačním jobu.

### English

- Stabilization release: QR email tests no longer require a locally installed QR package in the regular validation job.

## 0.1.26 – 2026-09-28

### Čeština

- QR platební kód je nyní vložen jako datový obrázek přímo v HTML e-mailu. Nepoužívá SMTP přílohy, media source ani dočasné soubory.

### English

- The payment QR code is now an inline data image in the HTML email body. It does not use SMTP attachments, media source or temporary files.

## 0.1.25 – 2026-09-28

### Čeština

- Volitelný účet pro QR platby pro každou skupinu sdílení a QR kód SPAYD 1.0 přímo v e-mailu SMTP; platba se vytváří jen pro kladnou hodnotu úplného měsíčního nebo ročního období.
- QR kód, včetně dopočtu IBAN a zprávy pro příjemce, vzniká pouze lokálně a dočasný PNG soubor se po předání SMTP odstraní.

### English

- Optional per-group Czech QR payment account and an inline SMTP SPAYD 1.0 QR code; a payment request is created only for a positive value from a complete monthly or yearly period.
- The IBAN, payment message and QR image are generated locally, and the temporary PNG is removed after SMTP handoff.

## 0.1.24 – 2026-09-15

### Čeština

- Volba posledního dostupného dne jednotlivých cílových EANů s datem u každého místa; původní společný den skupiny zůstává výchozí.
- Předměty reportů obsahují profil, skupinu nebo místo a období; souhrny uvádějí zahrnuté typy období. Skrytí EANů platí také v předmětu.

### English

- Optional latest available day per target EAN with an explicit date for each supply point; the shared group day remains the default.
- Profile report subjects include the profile, group or supply point and period; summaries list included period types. EAN visibility also applies to subjects.

## 0.1.23 – 2026-09-15

### Čeština

- Volitelný finanční souhrn skupiny podle cen jednotlivých cílových EANů, včetně rozpisu a kontroly shody s denními souhrny skupiny.
- Přehled profilů zobrazuje vybraná odběrná místa, příjemce a způsob výpočtu skupinových financí; upozorňuje na společný obsah pro všechny příjemce profilu.

### English

- Optional group financial totals using individual target EAN prices, with a breakdown and reconciliation against daily group totals.
- The profile overview shows supply-point scope, recipients and the group financial calculation mode, and explains that all profile recipients receive the same content.

## 0.1.22 – 2026-09-14

### Čeština

- cílové EANy mohou mít vlastní zobrazovaný název, lokalitu a volitelnou prodejní cenu; EANy se automaticky zjistí po načtení dat EDC a spravují se v novém kroku **Detaily EAN a ceny**,
- pro každý cílový EAN vznikne samostatné zařízení s denními a měsíčními hodnotami spotřeby, nasdílené elektřiny, dokupu, pokrytí, hodnoty sdílení a použité ceny,
- profily reportů nyní volí mezi původním reportem celé skupiny a reportem vybraných cílových EANů; v jednom profilu lze odeslat samostatnou část pro více EANů, pro různé příjemce se vytvoří další profil,
- individuální výpočty i reporty používají denní řady konkrétního cílového EANu a jeho vlastní cenu, zatímco všechny existující skupinové senzory, statistiky, tlačítka a ceny zůstávají beze změny.

### English

- target EANs can now have a local display name, location and optional sale-price override; EANs are discovered automatically after fetching EDC data and are managed through the new **EAN details and prices** step,
- every target EAN receives a separate device with latest-day and current-month consumption, shared electricity, grid import, coverage, sharing value and effective price,
- report profiles can select the original whole-group report or selected target EANs; one profile can include a separate section for multiple targets, while separate profiles support different recipients,
- individual calculations and reports use the daily rows for the selected target EAN and its own price, while all existing group sensors, statistics, buttons and price behavior remain unchanged.

## 0.1.21 – 2026-09-12

### Čeština

- pět nových senzorů využití přetoku pro poslední dostupný den, aktuální týden, měsíc, rok a všechna uložená data; metrika počítá `nasdíleno / přetok výrobny × 100` a není zaměněna s pokrytím spotřeby,
- vstupní hodnoty a skutečný rozsah dat jsou dostupné v atributech; denní agregace se ukládají bez duplicit, takže roční a celkový senzor přežijí restart a rozšíří se při backfillu,
- společný přehled všech profilů reportů přímo v nastavení, včetně příjemců, období, rozvrhu, zapnuto/pozastaveno a výsledků i termínů odesílání,
- označení nenalezených či nedostupných příjemců, časy v časovém pásmu HA a návrat z detailu na přehled; zobrazení nic neodesílá ani nenačítá z EDC.

### English

- five new surplus-utilization sensors for the latest available day, current week, month, year and all retained data; the metric is `shared / production surplus × 100` and remains distinct from consumption coverage,
- source values and the actual data range are exposed as attributes; daily aggregates are persisted by date without duplication, allowing yearly and total values to survive restarts and expand during backfill,
- a shared report profile overview in integration options, showing recipients, periods, schedules, enabled/paused state, delivery results and attempt times,
- missing or unavailable recipients are identified, times use the HA time zone, and profile details link back to the overview; viewing it does not send reports or fetch EDC data.

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
