# Přehled změn / Changelog

## 0.2.11 – 2026-10-16

### Čeština

- Oprava #8: neúplný či null den nezastaví import ostatních úplných dnů a hodin historického bloku. Neověřené dny, včetně prázdných a jednostranných profilů, zůstávají uložené jako mezery; neodvozujeme z nich datum vzniku skupiny ani nulovou energii.
- Nový stav `Dokončeno s mezerami` rozlišuje dokončené prohledání od úplného pokrytí. Další ruční spuštění opakuje jen mezery; restart obnoví přerušený běh bez opakování již dokončeného varování. Uložené klíče dnů a UTC hodin brání zdvojení počítadel při opakování. Starší cache zůstává kompatibilní, skutečné chyby API nadále zastavují běh.
- Diagnostika obsahuje nevyřešené kalendářní rozsahy a pevné důvody bez identit či naměřených hodnot. Regresní testy pokrývají částečný první den, chybějící/null dny, jednostranný profil, opakování po Store reload, souběh, přerušení a oba přechody letního času.
- Ověřeno 243 unit testy a po 71 funkčních testech skutečného HA pro minimum 2026.8.0 a aktuální stabilní 2026.10.1. Aktualizujte přes HACS, restartujte HA a znovu spusťte doplnění historie. Integraci ani její uloženou historii nemažte. Dokončení s mezerami samo nepotvrzuje úplnost dat ani datum vzniku skupiny.

### English

- Fix #8: partial/null days no longer block valid daily/hourly history in the same block. Absent and one-sided profiles remain recorded as unresolved gaps rather than fabricated zero energy or inferred sharing validity.
- Add `Completed with gaps`, persisted pending ranges and explicit retries of only those ranges. Resume interrupted work after restart without automatically retrying a finished warning. Persist unique day/UTC-hour keys to prevent duplicate counters; preserve legacy caches and blocking API failures.
- Add regression coverage for boundary and absent/null days, one-sided profiles, Store reload and targeted retry, concurrent starts, cancellation and both DST transitions. Diagnostics expose only calendar ranges and fixed reason codes.
- Verified with 243 unit tests and 71 real HA functional tests each for minimum 2026.8.0 and current stable 2026.10.1. Update through HACS, restart HA and run history backfill again. Keep the integration and retained history. Completion with gaps does not confirm complete data or the sharing group's validity start.

## 0.2.10 – 2026-10-14

### Čeština

- Oprava peněžních detailů dashboardu: generátor váže cílové senzory podle registru a skutečného `unique_id`, včetně `sharing_value_*` a `electricity_sale_price`. Hodnota sdílení v CZK se již nezamění za nasdílenou energii v kWh. Denní i měsíční částka používá původní senzor příslušného místa; přejmenované entity se zachovávají. Neplatný stav nebo jednotka zobrazí pomlčku, nikoli nulu.
- Přehled dne, týdne, měsíce a roku doplňuje orientační částku při aktuální ceně skupiny a skutečný rozsah dostupných dnů. Nejde o potvrzení úhrady, historický ceník ani přepočet již vystavených dokladů. Generátor a přibalené šablony obsahují stejné opravené karty. Aktualizace sama nepřepisuje vlastní dashboardy; existující dashboard lze upravit samostatně bez změny entit nebo statistik.

- Trvalá diagnostika časových hranic EDC: při odmítnutí nerozpoznaného rozlišení se do logu `EDC časový kontrakt` zapíše počet řádků, rozlišení jednotlivých řádků a nejvýše šest anonymních vzorků `start/end`. Výpis neobsahuje EANy, hodnoty energie, názvy skupin, hesla, tokeny ani cookies. Nepodporovaný obsah se nahradí značkou typu.
- Diagnostika používá právě přijatou odpověď běžícího klienta. Nevytváří další přihlášení ani HTTP požadavek; u platného profilu nic navíc neloguje. Zachovává opravy časů a přihlašování z v0.2.9, dosavadní validaci, chování chybějících dat a serverové limity.
- Hodinový přehled v Detailech používá poslední tři dny, aby zobrazil zpožděná data EDC. Výběr konkrétního dne je oddělený na vlastní podstránce a nepřebíjí výchozí přehled. Generátor a přibalený YAML příklad zachovávají tuto kompozici pro skupinu i cílová místa. Grafy používají původní externí statistiky a hodinové hodnoty `mean` v kWh nebo procentech.
- Diagnostika je ověřena unit testy a funkčními testy skutečného HA pro minimum 2026.8.0 a aktuální stabilní 2026.10.1 s odpovídajícími testovacími pluginy. Český i anglický návod a poznámky k vydání jsou sjednocené.
- Aktualizujte přes HACS a restartujte Home Assistant. Není potřeba mazat ani přejmenovávat entity, statistiky či dashboardy. Historie, doklady a potvrzené úhrady se zachovávají. Použití diagnostiky je popsáno v [návodu](docs-profile-time-diagnostics.md).

### English

- Fix monetary dashboard details by resolving target sensors from the registry and their actual unique IDs, including `sharing_value_*` and `electricity_sale_price`. Never show a CZK sharing value as kWh. Daily and monthly amounts use the existing supply-point sensors, including renamed entities. Invalid states or units display a dash rather than zero.
- Add an estimated day/week/month/year amount at the current group price and the actual available-day range. This is not payment confirmation, a historical price list or a recalculation of issued statements. The generator and bundled examples contain the same corrected cards. Updating the integration does not overwrite custom dashboards; an existing dashboard may be updated separately without changing entities or statistics.

- Retain permanent EDC time-boundary diagnostics. When an unrecognized resolution is rejected, the `EDC časový kontrakt` log records row counts, per-row resolutions and at most six anonymous start/end samples. Exclude EANs, energy measurements, group names, passwords, tokens and cookies; replace unsupported content with a type marker.
- Use the response already received by the running client, without another login or HTTP request. Valid profiles produce no additional error log. Preserve v0.2.9 time/login fixes, existing validation, missing-data handling and server restrictions.
- Default hourly details show the last three days to include delayed EDC data. A separate subview selects a specific day without overriding the default overview. The generator and bundled YAML example preserve this composition for groups and targets, using existing external statistics with hourly means in kWh or percent.
- Verify diagnostics with unit tests and real HA functional tests for minimum 2026.8.0 and current stable 2026.10.1 with matching test plugins. Align Czech and English documentation and release notes.
- Update through HACS and restart Home Assistant. Keep existing entities, statistic IDs, dashboards, history, statements and confirmed payments. See [the diagnostic guide](docs-profile-time-diagnostics.md).

## 0.2.9 – 2026-10-14

### Čeština

- Oprava časových hranic profilů: minutový zápis `HH:mm` již není odmítnut jen kvůli chybějícím sekundám. Podporované jsou také původní nulové sekundy a jejich nulová desetinná část. Rozpoznání rozlišení, kontrola úplnosti a hodinové výpočty skupiny i příjemců používají stejný převod. Nenulové sekundy se nezaokrouhlují a neplatné intervaly se nadále odmítají.
- Čas `24:00` je povolen pouze jako konec dne. Denní součet nevytváří falešnou půlnoční hodinu. Různé zápisy stejného času neobcházejí kontrolu duplicity; oba podzimní výskyty hodiny zůstávají oddělené v UTC. Chybějící intervaly/null se nedoplňují nulou.
- Zrušeno místní šestihodinové blokování po přihlašovacím HTTP 403, které bylo přidáno ve v0.2.5. Odpovídající dříve uložené místní blokování se při načtení vyřadí; původní chyba zůstane evidovaná. Další pokus řídí běžné plánování HA, bez okamžitého opakování v jednom požadavku. Serverové `Retry-After`, ostatní omezení a ruční MFA/CAPTCHA se zachovávají.
- Diagnostika uchovává přesný krok přihlášení: zahájení autorizace, přesměrování, odeslání údajů, výměna kódu nebo obnova tokenu. Údaj se zachová v logu, úložišti i diagnostickém exportu bez hesel, tokenů, cookies či surového HTML.
- Aktualizujte přes HACS a restartujte HA. Nemažte integraci, konfiguraci, entity ani historii. Entity/statistic ID, vlastní názvy, dashboardy, doklady a úhrady se nemění. Pokud server přihlášení stále odmítá, uložená historie zůstává dostupná a diagnostika ukáže aktuální chybu.
- Ověření kódu: 212 úspěšných unit testů, všech devět povinných Linuxových CI kontrol a po 56 skutečných HA testech pro 2026.8.0 i aktuální stabilní 2026.10.1. Testy zahrnují skutečný HTTP průchod syntetického minutového profilu, import nového dne do Recorderu a zachování historie/entit. Podrobnosti jsou v [návodu](docs-api-resilience.md).

### English

- Accept minute-precision profile boundaries (`HH:mm`) alongside zero seconds and their zero fractional part. Resolution detection, completeness and group/target hourly aggregation share one parser. Nonzero seconds are not rounded and invalid intervals remain rejected.
- Permit `24:00` only as a day-ending boundary. Daily totals never become midnight hourly points. Equivalent clock strings cannot bypass duplicate detection; autumn DST occurrences remain separate in UTC. Missing intervals/null are never replaced with zero.
- Remove the local six-hour cooldown introduced in v0.2.5 after login HTTP 403, including matching persisted local blocks. Retain the original failure and let normal HA scheduling decide the next attempt without immediate in-request retries. Preserve server `Retry-After`, other restrictions and manual MFA/CAPTCHA requirements.
- Preserve the exact authentication step in logs, storage and diagnostics: authorization, redirects, credentials submission, code exchange or token refresh. Do not expose passwords, tokens, cookies or raw HTML.
- Update through HACS and restart HA without deleting configuration, entities or history. Entity/statistic IDs, custom names, dashboards, statements and payments remain unchanged. Retained history remains available if the server still rejects login.
- Verified code with 212 passing unit tests, all nine required Linux CI checks and 56 real HA tests per environment (2026.8.0 and current stable 2026.10.1), including real HTTP handling of a synthetic minute profile and new-day Recorder import with retained history/entities. See [the guide](docs-api-resilience.md) for details.

## 0.2.8 – 2026-10-14

### Čeština

- Oprava regrese validace zavedené v0.2.5: `NaN` nebo `Infinity` v jedné naměřené hodnotě již neodmítne celý jinak platný profil HTTP 200 a nezaloží patnáctiminutové čekání pro celé období. Platné nové dny a hodiny se zpracují i vedle nepoužitelných intervalů. Formát požadavku z v0.2.4 zůstává nezměněný: místní `YYYY-MM-DD`, poslední den včetně.
- Na rozdíl od starého převodu na nulu se vynechá celý dotčený interval. Neúplná hodina/den se neimportuje ani nevyúčtuje jako kompletní a nepřepíše dříve uložený platný den. Explicitní nula zůstává platné měření. `missing_measurement_days` a `missing_measurement_intervals` zahrnují také NaN/Infinity, nikoli automaticky celou historii. Neúplný backfill neposune kurzor.
- Chybný text, bool, chybějící pole, krátký vektor, změněná jednotka/role a konečné číslo mimo rozsah float se dál odmítají. Serverové zákazy, Retry-After a již uložené lhůty se neobcházejí. Nemění se entity, unique/statistic ID, jednotky, vlastní názvy, dashboard, uložené doklady ani platby.
- Aktualizujte přes HACS a restartujte HA. Nemažte konfiguraci ani historii. Sledujte výsledek nového načtení a skutečný poslední datový den; případnou dosud aktivní uloženou lhůtu nechte uplynout. Regresní testy kontrolují zpracování profilu na hranici API, zachování staršího dne, načtení nového dne se 96 čtvrthodinami a skutečné body Recorderu pro skupinu i odběratele.

### English

- Fix the v0.2.5 validation regression: a NaN/Infinity measurement no longer rejects an otherwise valid HTTP-200 profile or imposes a whole-period cooldown. Process valid new days/hours independently. Preserve the v0.2.4 local calendar request format and inclusive API end date.
- Skip the affected interval rather than substitute zero. Incomplete hours/days are not imported or billed as complete and cannot replace retained valid days. Existing gap counters include nonfinite measurements; an affected interval does not mean all history is missing. Incomplete backfill still preserves its cursor.
- Continue rejecting malformed fields, vectors, text, booleans, units/roles and finite numbers exceeding float range. Preserve server restrictions, Retry-After and existing deadlines. Entity/statistic IDs, units, custom names, dashboards, statements and payments are unchanged.
- Update through HACS and restart HA without deleting configuration/history. Check the actual fetch result and latest data date after any existing deadline expires. Regression tests exercise the API boundary, retained history, a new complete 96-interval day and actual Recorder points for the group and target.

## 0.2.7 – 2026-10-14

### Čeština

- Opravena regrese v0.2.6: neúspěch nového stahování už neznepřístupní existující platnou historii. Stejné skupinové a individuální senzory zobrazují poslední dostupný den, měsíční součty, využití přetoku i původní atributy s rozsahem a počtem dnů. Chybějící poslední den se nevymýšlí ani nepožaduje k zobrazení předchozích dnů; chování posledního dostupného dne odpovídá v0.2.4. Platná historie není označena jako neplatná nebo „zastaralá“ jen proto, že se nové stahování nezdařilo.
- Beze změny všech entity ID, unique ID, jednotek, ID statistik a vlastních názvů. Existující dashboard ani jeho karty nemusíte měnit, mazat nebo znovu generovat. Výrobní a cílové EANy se při startu obnoví z vlastní cache nebo z existujícího registru stejné instance; uložená identita EAN není tvrzení o aktuální platnosti alokace.
- Stav čtení zůstává poctivě `failed` / `authentication_failed`; `last_update_success` se nepřepíná na true kvůli cache. Atributy `data_source: retained_history` a `last_fetch_result` oddělují původ hodnot od stavu stahování; export navíc uvádí `history_available`. Diagnostika se aktualizuje i při opakovaných selháních. Výpadek neodstraní kWh, datum ani atributy, kvůli jejichž skrytí předchozí dashboard zobrazoval prázdno a náhradní nuly.
- Existující body Recorderu se při tomto startu nemažou, nepřepisují, nepřenášejí na dnešek ani znovu neimportují. Zobrazované souhrny se počítají pouze ze skutečných uložených dnů. Skutečně prázdná historie nadále není nulová energie; nakonfigurovaná cena není měření. Doklady, ceny v již vystavených dokladech a potvrzené platby se nemění.
- Serverové Retry-After a původní čekání se zachovají; dostupnost historie žádný síťový zákaz neobchází. Automatické importy, backfill a plánované reporty se po startu pouze s historií zapnou až po úspěšném čtení. Při odmítnutém hesle je historie dostupná a otevře se standardní reauth; bez časovače se heslo neopakuje do opravy přihlášení. Bez validní historie zůstává standardní setup retry/reauth.
- Aktualizujte v HACS a restartujte HA. Nemažte integraci, entity, `.storage`, statistiky ani dashboard. Výsledkem mají být původní hodnoty a skutečné datum posledního dostupného EDC dne, nikoli nové entity. Vlastní dashboard zůstává uložený beze změny. Podrobnosti v [návodu](docs-api-resilience.md).
- Ověření opravy: [Validate 38541682766](https://github.com/79thales/edc-sharing-stats/actions/runs/38541682766), všech devět povinných kontrol úspěšných. Po 47 skutečných HA funkčních testech na přesném minimu 2026.8.0/0.13.354 a nejnovější stabilní dvojici 2026.10.1/0.13.372; 193 unit testů, samostatné HA kompatibilitní kontroly, oba frontendy, HACS, Hassfest a lint. Nové scénáře pokrývají uchované kWh/atributy pod vlastními původními ID, skutečné body Recorderu, chybějící nebo null poslední den, opakovanou chybu, obnovu i odmítnuté heslo bez opakování přihlášení. EDC odpovědi v CI jsou syntetické; to nedokazuje příčinu původní chyby živého API ani dokončení aktualizace zákaznického HA.

### English

- Fix v0.2.6 hiding valid retained history after a failed fetch. Existing group/target sensors expose the last available day, period totals and original coverage attributes independently of network success. A pending final day does not invalidate previous days or become a fabricated zero; last-available-day behavior matches v0.2.4.
- Preserve entity/unique IDs, statistic IDs, units and custom names. No dashboard rewrite or regeneration is required. Restore producer/target identities from retained metadata or the same entry's existing registry; this is not a claim about current allocation validity.
- Keep fetch failures and `last_update_success` truthful. Separate data provenance using `data_source`, `last_fetch_result` and `history_available`; refresh diagnostics on repeated failures. Existing Recorder points are neither removed nor reimported at retained-history startup. No valid history still means unavailable energy, not a zero measurement.
- Retain server/legacy deadlines and disable automatic imports/backfill/reports until verified recovery. Rejected credentials trigger normal reauthentication without repeated coordinator logins while retained values remain accessible. Frozen statements and confirmed payments are unchanged.
- Update through HACS and restart HA without deleting integration, entities, storage, statistics or dashboards. The existing dashboard should display its original values and actual EDC data date under the same IDs. See the [guide](docs-api-resilience.md).
- Validation: [Validate 38541682766](https://github.com/79thales/edc-sharing-stats/actions/runs/38541682766) passed all nine required jobs, including 47 actual HA functional tests on each exact pair 2026.8.0/0.13.354 and current stable 2026.10.1/0.13.372, 193 unit tests, separate compatibility checks, both frontends, HACS, Hassfest and lint. New cases cover original custom IDs and retained values/attributes, actual Recorder points, an omitted/null final day, repeated failures, recovery and rejected credentials without repeated logins. CI uses synthetic EDC responses; it does not establish the original live API failure's cause or confirm a customer installation update.

## 0.2.6 – 2026-10-14

### Čeština

- Oprava chybějícího záznamu při prvním neúspěšném startu z v0.2.5. První selhání má WARNING v protokolu HA a trvale uložený bezpečný důvod, HTTP status, fázi, čas a původ čekání. Zachovávají se také povolené validační kódy/pole a kalendářní rozsah. Čekací výjimka původní chybu nepřepisuje; opakované čekání nezahlcuje log. Obnova po platné odpovědi se zaznamená samostatně. Žádné heslo, token, EAN, ID skupiny, volná zpráva serveru nebo doklad se do tohoto záznamu nepřidává.
- Diagnostika už není prázdné `ready: false` při `setup_retry`: funguje před přiřazením runtime. Správcovský čtecí příkaz `edc_sharing/statistics/health` vrací tuto diagnostiku také pro nepřipravenou instanci, bez nového čtení EDC i při požadavku `fresh`. Export rozlišuje poslední příčinu, lokální ochranu, serverové Retry-After a neznámý původ starých záznamů.
- S existující validní historií umožňuje neúspěšný první refresh pouze diagnostický start: nastavení, archiv a diagnostické entity jsou přístupné. Výpočtové senzory zůstávají `unavailable`, výsledek `failed`, příznaky `cached_startup`/`cached_only` jsou výslovné. Cache není nové úspěšné načtení. Automatické importy, pokračování backfillu a plánované reporty se povolí jednou až po skutečné obnově čtení. Bez validní cache zůstává běžný `setup_retry`; odmítnuté heslo stále vyžaduje reauth.
- Explicitní JSON `null` ve známém vektoru znamená chybějící interval, nikoli automaticky změnu API. Interval se vynechá a neúplná hodina/den se neimportuje ani nevyúčtuje jako kompletní; nula zůstává platné měření. Chybějící `v`, krátký vektor, změněné role/jednotky, neplatné číslo a neznámé rozlišení se dál odmítají. Podzimní opakovaná hodina zachová správný UTC fold i při null v prvním výskytu. Historický blok s null neposune kurzor.
- Lokální chyba validace odpovědi HTTP 200 chrání pouze přesné období patnáct minut; neblokuje jiné období skupiny na šest hodin. Obnova načítá nejnovější blok první a neodhodí jeho platné hodnoty kvůli chybě schématu staršího bloku. HTTP/serverové a autentizační ochrany se tím neobcházejí. Staré záznamy bez původní příčiny se automaticky nemažou ani nezkracují: konkrétní důvod ztracený v0.2.5 nelze zpětně rekonstruovat. Null je otestovaná regrese, nikoli prokázaná příčina původního živého incidentu.
- Aktualizujte přes HACS a restartujte HA; nemažte integraci, `.storage`, statistiky ani vyúčtování. Záznam najdete v **Nastavení → Systém → Protokoly** pod `custom_components.edc_sharing.api_policy`, v diagnostice instance a v atributech **Poslední pokus o načtení dat**. Uložené UTC termíny se zachovají; při starém čekání s neznámým původem nový pokus začne až po původním termínu. Oprava sama neposílá e-mail, nevystavuje doklad ani nepotvrzuje platbu. Podrobný postup a omezení jsou v [návodu](docs-api-resilience.md).
- Ověření kódu: [Validate 38533348619](https://github.com/79thales/edc-sharing-stats/actions/runs/38533348619) úspěšně dokončil všech devět povinných kontrol, veřejný advisory monitor se při push očekávaně nespouští. Po 42 skutečných funkčních testech HA na přesných dvojicích 2026.8.0/0.13.354 a aktuální stabilní 2026.10.1/0.13.372; 193 lokálních unit testů, 22 HA kompatibilitních kontrol v samostatných CI bězích, oba frontendy a lint. Nové testy provádějí skutečný config-entry setup, diagnostiku bez runtime, start s legacy čekáním a obnovu bez duplicitního plánovače. Testovací storage fixture není test fyzického disku; EDC odpovědi jsou syntetické. Živý HA byl pouze čten a tento release ho automaticky neaktualizuje.

### English

- Fix missing first-start error records from v0.2.5. Persist an allowlisted original reason, HTTP status, phase, timestamps, cooldown provenance and known validation codes/calendar context; log the first failure at WARNING and verified recovery separately. Waiting preserves the cause without log spam. No credentials, tokens, EANs, group IDs, server free text or billing documents are logged.
- Export diagnostics before runtime exists; the admin-only health command also returns startup diagnostics without performing EDC reads, even when `fresh` is requested for an unready entry.
- With valid retained history, allow diagnostic-only startup after a failed first refresh. Settings, archives and diagnostics remain accessible; calculated sensors remain unavailable and `cached_startup`/`cached_only` explicitly identify stale data. Automatic imports, resumed backfill and scheduled reports start only after a verified successful read. No cache still means setup retry; rejected credentials still require reauthentication.
- Treat explicit null measurements as missing intervals, not schema changes or zeros. Incomplete hours/days cannot be imported or billed as complete data; malformed fields, vectors, units and unknown resolutions remain rejected. Missing values preserve autumn DST folds and stop historical cursor advancement.
- Local HTTP-200 profile validation failures are scoped to the exact period with a 15-minute guard, rather than blocking all periods for six hours. Read the newest block first and retain valid recent data when an older block has a local schema error. Server and authentication cooldowns are still respected. Legacy cooldowns with unknown provenance are not deleted or shortened, and a cause never recorded by v0.2.5 cannot be reconstructed. Null handling is a tested regression, not a proven explanation of the original live incident.
- Update through HACS and restart HA without deleting integration/storage/statistics/settlements. Look under `custom_components.edc_sharing.api_policy` in HA system logs, the entry diagnostics and last-update-attempt attributes. Old cooldown deadlines remain intact. The update does not send email, issue statements or confirm payments. See the [guide](docs-api-resilience.md).
- Code validation: [Validate 38533348619](https://github.com/79thales/edc-sharing-stats/actions/runs/38533348619) passed all nine required jobs; the public advisory monitor is intentionally not run on push. Each exact HA pair 2026.8.0/0.13.354 and current stable 2026.10.1/0.13.372 passed 42 real functional tests, plus 193 local unit tests, 22 separately executed HA compatibility checks, both frontends and lint. New tests exercise actual entry setup, diagnostics without runtime, retained-cache startup under legacy cooldowns and single scheduler activation after recovery. Storage fixtures do not test physical disk failure; EDC responses are synthetic. The live HA was only read and is not automatically upgraded by this release.

## 0.2.5 – 2026-10-14

### Čeština

- Aktualizace přes HACS a následný restart HA; nemažte integraci ani statistiky. Existující vyúčtování a potvrzené úhrady zůstávají zachované. Nové grafy získáte novým generováním dashboardu nebo úpravou podle příkladu; již uložený dashboard se automaticky nepřepisuje. Zablokovaný neúplný backfill lze obnovit po doplnění/ověření zdrojových dat; chybějící data se nepovažují za nulu.

- Validace požadavků a odpovědí: neplatné skupiny se odmítají před sítí, chybějící/null/nekonečné hodnoty a změny významových polí se nepřevádějí na nulu. Denní součet se nezapisuje jako půlnoční hodina; neúplné hodiny/dny se nezapočítávají jako kompletní data. Neověřený historický blok neposune kurzor backfillu.
- Rozlišení validace, autentizace, oprávnění, dočasné nedostupnosti, omezení frekvence a změny kontraktu. HTTP 400/422 nemá okamžité retry; dočasná chyba čtení má nejvýše dva dodatečné pokusy (5/30 sekund s rozptylem). Serverový Retry-After se respektuje. Čekání se sdílí mezi skupinami, nastavením, reporty i backfillem a ukládá se bez hesel/tokenů. Prošlý API token se obnovuje jednou; odmítnuté heslo se znovu neposílá.
- Administrátorská čtecí kontrola `edc_sharing/statistics/health` vrací počty skutečně uložených bodů. Odděluje chybějící statistiku, prázdné období a existující body od samotného zařazení do fronty. Sdílitelná diagnostika používá whitelist bez osobních údajů a bankovních účtů.
- Generátor zachovává Přehled a Detaily, do detailů přidává skupinové a individuální hodinové průběhy posledních tří dnů. Samostatná podstránka nabízí nativní výběr dne bez ovlivnění výchozího přehledu. Aktualizován distribuovaný příklad; existující dashboard se automaticky nepřepisuje.
- Veřejný monitor rozpoznává nový build portálu jako podnět ke kontrole, nikoli důkaz nekompatibility API. Soukromý průchod kontroluje aktivní prvky a skutečný požadavek po zobrazení tabulky; je vypnutý do spuštění s testovací session. Disabled/inconclusive/unavailable nejsou ověření živého API.
- Nové regresní scénáře a skutečné testy Recorderu, čtení bodů přes frontendové API, opakovaného importu, korekce, restartu a vykreslení nativního grafu. CI zachovává přesné minimum a nejnovější stabilní HA. Konkrétní provedené kontroly jsou v dokumentaci implementace; unit testy samotné nepotvrzují funkčnost živého EDC.
- Doložené hodinové grafy skupiny i cíle pro 23/25hodinové změny času; jednotky kWh/% se ověřují proti skutečnému Recorderu. Ověření MFA/CAPTCHA vyžaduje člověka a nezamění se za špatné heslo; reauth neobchází sdílené čekání. Technické chyby tokenové služby se neopakují odesíláním hesla.
- Výslovný správcovský `fresh` probe odděluje přihlášení, seznam skupin, jednodenní profil a parser od importu a čtení statistik. Výchozí kontrola je pouze cache/Recorder. Probe je čtecí, bez ukládání profilu, odeslání e-mailu či vystavení dokladu.
- Veřejný monitor čte oficiální ICS, rozlišuje EDC-SAKU/SEBI/AFLEX, aktivitu okna a nepodporovaný formát. Volitelný lokální stav deduplikuje změnu/zotavení. Soukromý browser probe má timeout 120 s, zámek a rozpočet nejvýše pěti profilových čtení. Přihlášený živý test bez oddělené testovací session zůstává neprovedený; veřejná dostupnost jej nenahrazuje.
- Ověření kódové změny: [Validate 38522438041](https://github.com/79thales/edc-sharing-stats/actions/runs/38522438041), všech deset kontrol úspěšných; po 38 skutečných HA testech na 2026.8.0/0.13.354 a 2026.10.1/0.13.372, 182 lokálních unit testů a oba frontendové testy. Neúplný backfill nepostoupí přes chybný blok a stav se obnoví v nové HA instanci; Recorder restart je ověřen se skutečnou SQLite. Veřejný build fungoval lokálně, ale GitHub report zaznamenal transportní nedostupnost; ICS fungoval v obou prostředích. Úspěch advisory jobu není tvrzení o dostupnosti API. Živý zákaznický HA ani již vydaná verze se při těchto kontrolách nemění.

### English

- Update through HACS and restart HA without deleting the integration or statistics. Existing settlements and confirmed payments are preserved. Regenerate the dashboard or apply the bundled example for the new charts; saved dashboards are not overwritten automatically. Resume an incomplete backfill after its source data has been completed or verified; missing data is not zero.

- Validate request types and response semantics before publishing data. Missing, null and non-finite values are not zero; daily totals do not become midnight hours, incomplete periods are excluded, and unverified history does not advance the cursor.
- Classify failures, bound read retries, honor Retry-After and share persistent cooldowns across groups and configuration flows. Refresh an expired API token once without repeating rejected credentials.
- Add admin-only read-only Recorder health inspection and an allowlisted diagnostic export. Generated details include group/target hourly charts and a separate selected-period subview.
- Add advisory public build observation and an opt-in private portal workflow probe. Neither a changed build nor disabled/inconclusive checks confirm live API compatibility. Coverage includes actual Recorder reads, correction, restart and native chart rendering on exact supported HA environments.
- Verify group and target native charts on 23/25-hour DST days and actual stored kWh/% units. An explicit admin-only fresh probe reads group membership and one profile day without importing data or sending email. Token service failures do not resend passwords; unsupported MFA/CAPTCHA requires human intervention.
- Read the official maintenance ICS as context, distinguishing EDC-SAKU, SEBI and AFLEX. The private browser probe is bounded to 120 seconds, one concurrent process and five profile requests. Validation passed 38 real HA tests on each exact pair 2026.8.0/0.13.354 and 2026.10.1/0.13.372, plus 182 unit tests. Live authenticated EDC compatibility remains unverified without a dedicated fresh test session. The public portal worked locally but was transport-unavailable from the GitHub runner; ICS worked in both environments. An advisory job passing does not mean the live API is available. No live customer HA installation is upgraded by this release workflow.

## 0.2.4 – 2026-10-13

### Čeština

- Souvisí s [issue #7 – chyba EDC HTTP 400](https://github.com/79thales/edc-sharing-stats/issues/7).
- Opraven požadavek profilových dat pro aktuální portál EDC: `dateFrom`/`dateTo` používají kalendářní data `YYYY-MM-DD` místo UTC okamžiků, konečný den je včetně a nadbytečný `profileType` se neposílá. Interní intervaly a kurzor zůstávají od včetně/do bez koncového dne; převod se provádí pouze v API klientovi. Platí pro první i pravidelné načtení, roční backfill a skupinové i individuální reporty. Bloky obsahují maximálně 31 dnů, bez mezer nebo duplicit, včetně přestupného dne a změn času.
- Chyby API zachovávají stav HTTP a doplňují jen známý endpoint, kalendářní rozsah a bezpečně povolené kódy/pole. Maximálně 16 KiB chybového těla, bez kopírování volných zpráv, EANů, ID skupin, tokenů a hesel. Spojení se uvolní i při chybě. Neplatné/větší rozsahy se odmítnou ještě před HTTP.
- Po instalaci restartujte HA bez mazání integrace; selhaný backfill obnovte jeho tlačítkem. Uložené EDC hodnoty, hodinové UTC značky, statistiky a jejich ID, ceny, reportové rozvrhy, vyúčtování a potvrzené úhrady se nemění. Oprava sama nevystavuje doklady ani neodesílá e-maily.
- Ověření opravy: všech devět Linuxových CI kontrol prošlo, včetně HACS, Hassfest, frontendů, lint a kompatibility HA 2026.8.0, 2026.9.0 i nejnovější stabilní 2026.10.1. Reálné dashboard/billing fixtures používají přesné dvojice 2026.8.0/0.13.354 a 2026.10.1/0.13.372; na každé prošlo 27 testů. Unit sada má 147 úspěšných testů a 22 HA kontrol prováděných samostatně v kompatibilitních bězích. Hassfest nadále upozorňuje na dosavadní registraci CONFIG_SCHEMA, ale nehlásí selhání. Místní Windows kontrola skončila nativní chybou OpenSSL a nebyla započtena jako úspěch; kompatibilita byla ověřena v Linuxu, bez náhrady starší nebo beta verzí.

### English

- Related to [issue #7 – EDC HTTP 400](https://github.com/79thales/edc-sharing-stats/issues/7).
- Fixed profile requests for the current EDC portal: calendar `YYYY-MM-DD` dates replace UTC instants, the end date is inclusive and the redundant `profileType` is omitted. Internal half-open intervals and history cursors are preserved; only the API client converts the end boundary. This applies to initial/regular refresh, history backfill and group/target reports. Blocks cover at most 31 days without gaps or duplication, including leap days and DST changes.
- API errors retain HTTP status and expose only known endpoints, calendar ranges and allowlisted error codes/fields. Error bodies are bounded to 16 KiB; free text, EANs, group IDs, tokens and passwords are not echoed. Connections are released on errors. Invalid/oversized intervals are rejected before HTTP.
- Restart HA after installing without deleting the integration; resume a failed backfill using its button. Retained EDC data, hourly UTC timestamps, statistics/IDs, prices, report schedules, settlements and confirmed receipts are unchanged. The fix does not itself issue documents or send email.
- Validation: all nine Linux CI checks passed, including HACS, Hassfest, frontends, lint and HA 2026.8.0, 2026.9.0 and latest stable 2026.10.1 compatibility. Real dashboard/billing fixtures use exact 2026.8.0/0.13.354 and 2026.10.1/0.13.372 pairs, with 27 tests passing on each. The unit suite has 147 passing tests and 22 HA checks executed separately in compatibility jobs. Hassfest retains a warning about the existing CONFIG_SCHEMA registration, not a failed check. The local Windows HA check ended with a native OpenSSL error and was not counted as successful; compatibility was verified on Linux without an older or beta substitute.

## 0.2.3 – 2026-10-12

### Čeština

- Licence projektu změněna z MIT na GNU GPL v3.0 (GPL-3.0-only). Dříve vydané verze zůstávají dostupné pod licencí, pod kterou byly původně zveřejněny.
- Plný text licence a oznámení jsou také součástí instalačního ZIPu HACS.

### English

- Changed project license from MIT to GNU GPL v3.0 (GPL-3.0-only). Previously released versions remain available under the license under which they were originally published.
- The full license text and notices are also included in the HACS installer ZIP.

## 0.2.2 – 2026-10-08

### Čeština

- Po aktualizaci restartujte HA a znovu vytvořte náhled. Doplněny regresní testy měsíce, přestupného února, roku, vlastního období a přechodu mezi roky, dlouhých názvů, celého EANu a bezpečného HTML zobrazení skutečné QR poznámky. HACS, Hassfest, dostupné testy a kompatibilita API na stabilní HA 2026.10.0 prošly. Úplné dashboard/billing fixtures na 2026.10.0 zůstávají nedostupné kvůli upstream pluginu; CI tuto mezeru stále hlásí jako chybu, bez nahrazení betou nebo starší HA.
- Poznámka platby v QR vyúčtování používá stejné označení měsíce/roku jako automatické reporty a pro vlastní období zachovává oba krajní dny. Stejná poznámka je viditelná v náhledu, na dokladu i v textovém e-mailu. V limitu 60 znaků mají přednost období a celý EAN; dlouhé jméno se zkracuje. Dlouhý název skupiny už nesmí vytlačit období z poznámky. Částky, účet a variabilní symbol se nemění.

### English

- Restart HA after updating and regenerate the preview. Added regressions for months, leap-year February, years, custom and cross-year ranges, long names, full EANs and safe HTML rendering of the actual QR reference. HACS, Hassfest, available tests and API compatibility on stable HA 2026.10.0 passed. Full dashboard/billing fixtures for 2026.10.0 remain unavailable because of the upstream plugin; CI still reports this gap as a failure, without substituting beta or older HA.
- Settlement QR payment references use the same month/year labels as automatic reports and retain both boundaries for custom ranges. The exact reference is also visible in previews, documents and plain-text email. Within the 60-character limit, the period and full EAN take priority over long names. Long group names no longer displace the period. Amounts, accounts and variable symbols are unchanged.

## 0.2.1 – 2026-10-08

### Čeština

- Po aktualizaci restartujte HA. Zaškrtněte souhlas s vyúčtováním pouze dostupných dat, znovu vytvořte náhled a samostatně potvrďte vystavení. Změna skupiny, profilu či období tento souhlas ruší. QR vyžaduje nastavený účet a kladný zůstatek; náhled QR nemá finální variabilní symbol. Stávající doklady, úhrady a statistiky se nemění.
- Doplněny testy částečného období, QR, uchování vynechaných dnů po restartu, neplatných hodnot, skupinových součtů a předání výslovného souhlasu z panelu. Dostupné testy včetně reálných fixtures na HA 2026.8.0, HACS, Hassfest a kompatibility API na stabilní HA 2026.10.0 prošly. Úplné fixtures na 2026.10.0 zůstávají nedostupné kvůli upstream pluginu; CI tuto mezeru dál hlásí jako chybu, bez náhrady betou či starší verzí.
- Volitelný výslovný souhlas s vyúčtováním pouze dostupných dat dovolí vystavení a QR také při chybějících dnech (například při výběru období před zahájením sdílení). Výchozí kontrola zůstává přísná. Vynechané dny jsou trvale uvedeny v náhledu, dokladu i e-mailu; nejsou označovány za nulu ani automaticky za období před zahájením. Úplně prázdné období, neplatné hodnoty, nesouhlasící dostupné skupinové součty a nejednoznačné úhrady nelze touto volbou obejít. Nově dostupná data se nepřidají zpětně do uloženého dokladu; lze je vyúčtovat novým dokladem bez zdvojení již evidovaných dnů.

### English

- Restart HA after updating. Explicitly accept billing only available data, regenerate the preview and separately confirm issue. Changing the group, profile or period clears this consent. QR requires a configured account and a positive balance; preview QR has no final variable symbol. Existing documents, receipts and statistics are unchanged.
- Added tests for partial periods, QR, omitted-date persistence across restart, invalid values, group reconciliation and explicit consent submitted by the panel. Available tests, including real HA 2026.8.0 fixtures, HACS, Hassfest and API compatibility on stable HA 2026.10.0 passed. Full 2026.10.0 fixtures remain unavailable because of the upstream plugin; CI still reports this gap as a failure, without beta or older-version substitution.
- An explicit opt-in to bill only available data permits issue and QR generation when dates are missing, including ranges selected before sharing began. Strict completeness remains the default. Omitted dates remain visible in previews, stored documents and email; they are not treated as zero or automatically classified as pre-sharing dates. The option does not override entirely empty ranges, invalid values, inconsistent available group totals or ambiguous receipts. Later data does not mutate issued documents; it can be billed in a new statement without duplicating existing daily charges.

## 0.2.0 – 2026-10-08

### Čeština

- Přidány hodinové externí statistiky pro každé odběrné místo: nasdílená energie, spotřeba, dokup ze sítě a pokrytí sdílením. ID obsahuje skupinu i EAN, aby stejné místo v různých skupinách nekolidovalo. Atribut `hourly_statistic_id` příslušného senzoru odkazuje na novou statistiku. Starší historii lze doplnit opětovným spuštěním backfillu.
- Hodnoty představují jednotlivé hodiny EDC, nikoli kumulativní čítače nebo živý výkon. Import pracuje s UTC, rozlišuje opakovanou hodinu při změně času a nahrazuje stejné časové body místo jejich přičítání. Stávající Energy statistiky a jejich denní příjmy se nemění.
- Kredit za základ hodinových statistik jednotlivých míst patří [@jirisida](https://github.com/jirisida), fork `feature/target-hourly-history`; doplněno oddělení skupin a ochrana překrývajících se importů.
- Validační omezení při vydání: HACS, Hassfest, unit testy, reálné HA fixtures pro minimum 2026.8.0 a kontrola kompatibility API na stabilní HA 2026.10.0 prošly. Úplné dashboard/billing fixtures na 2026.10.0 nebylo možné spustit, protože upstream testovací plugin pro tuto přesnou stabilní verzi dosud není dostupný. CI tuto mezeru stále hlásí jako chybu; nebyla nahrazena betou ani starší HA a nejde o kompletně zelenou validaci.
- QR platba je nově viditelná také v náhledu vyúčtování, ještě před vystavením. Používá účet skupiny a zbývající částku po odečtení pouze ručně potvrzených úhrad; období a identifikace odběratele/EANu odpovídají zvolenému rozsahu.
- Náhled QR není finální výzva k úhradě: nemá variabilní symbol a u obrázku je výslovné upozornění **Neplaťte podle tohoto náhledu**. Finální QR s variabilním symbolem vzniká až po potvrzení vystavení. Náhled nic neukládá, nerezervuje číslo dokladu a neposílá e-mail.
- Bez nastaveného účtu, při nulovém zůstatku, neúplných datech nebo nejednoznačně přiřazené úhradě se QR v náhledu nevytváří. QR nadále vzniká lokálně v paměti, bez externí služby nebo souboru.
- Doplněny regresní testy částky, částečných/potvrzených úhrad, překryvů a českého/anglického upozornění i reálné HA testy PNG a náhledu bez zápisů. CI instaluje deklarované závislosti integrace; testy minimální HA verze běží nezávisle na dostupnosti fixtures pro nejnovější stabilní HA. Kontrola nejnovější verze zůstává povinná, bez náhrady starší nebo beta verzí.
- Vystavené doklady, jejich QR a variabilní symboly, uložená historie, stávající reporty, statistiky a ID entit zůstávají beze změny.

### English

- Added per-target hourly external statistics for shared electricity, consumption, grid import and sharing coverage. IDs include both the group and EAN to avoid collisions across groups. The corresponding sensor exposes an `hourly_statistic_id` attribute. Run history backfill again to populate older periods.
- Values describe individual EDC hours, not cumulative counters or live power. Imports use UTC, distinguish repeated DST hours and replace matching timestamps instead of adding them again. Existing Energy statistics and daily income booking are unchanged.
- Credit to [@jirisida](https://github.com/jirisida) for the per-target hourly statistics foundation in `feature/target-hourly-history`; this integration adds group-scoped IDs and safeguards for overlapping imports.
- Validation limitation at release: HACS, Hassfest, unit tests, real HA fixtures for the 2026.8.0 minimum and API compatibility checks on stable HA 2026.10.0 passed. Full dashboard/billing fixture tests on 2026.10.0 could not run because the upstream test plugin for that exact stable release is not yet available. CI continues to report this gap as a failure; no beta or older HA was substituted, and validation is not entirely green.
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
