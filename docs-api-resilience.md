# Odolnost EDC API – implementace a ověření

## Minutové časové hranice profilů (vývojová oprava)

Funkční reference je `H:\01.programovani\webdownloader\src\OrlenPriceDownloader\MainWindow.xaml.cs`: `ParseEdcRows` ponechává text intervalu a `ParseIntervalStartHour` čte hodinu. V tabulkovém exportu je doložen minutový zápis `HH:mm`. Kontrola přidaná po v0.2.4 požadovala tři celočíselné složky času, takže odpovídající minutový zápis odmítla jako `profile_resolution`. Nový společný parser přijímá `HH:mm`, `HH:mm:00` a nulovou desetinnou část sekund; nenulové sekundy ani jiné rozlišení nezaokrouhluje. Konec `24:00` označuje půlnoc následujícího dne a není povolen jako začátek intervalu.

Rozlišení, úplnost a oba hodinové parsery používají stejnou časovou interpretaci. Identita slotu je místní den a počet minut od půlnoci, takže různý text téhož času neobchází kontrolu duplicit. Pořadí obou podzimních výskytů řeší dosavadní UTC převod v Europe/Prague. Denní součet se nemění v hodinový bod; mezery/null se nedoplňují nulou. Kontroly struktury, jednotek, délky intervalů a rozsahu požadavku zůstávají aktivní. API vrací původní odpověď beze změny a místní převod nijak nepřepisuje entity, statistiky, cache ani vyúčtování.

`tests/fixtures/profile-clock-minutes.json` je syntetický regresní vzorek, nikoli zachycená živá JSON odpověď. Jeho čtyři čtvrthodiny představují spotřebu 10 kWh, síť 6 kWh, sdílení 4 kWh a pokrytí 40 %. Testy ověřují také úplné 23/24/25hodinové dny, denní/hodinové rozlišení, nulovou přesnost sekund, chybějící slot, neplatný čas, duplicity a přijetí/odmítnutí v API klientu bez opakování požadavku.

Živá diagnostika 14. 10. 2026 stále doložila HTTP 200 a následné `profile_resolution` za uložený rozsah 1. 9.–1. 10. Jediný samostatný pokus o čtení 13. 10. skončil přihlašovacím HTTP 403, takže pole `start`/`end` nebyla získána. Nebyl opakován. Doložena je oprava syntaktické nekompatibility minutového času; není dosud prokázáno, že právě tento zápis způsobil poslední živé odmítnutí. Změna nebyla nasazena do produkčního HA ani vydána jako release.

Lokálně prošlo 78 cílených testů a celá sada 234 nalezených testů (212 úspěšných, 22 HA kontrol vyžadujících samostatné prostředí). Resolver z PyPI při této opravě ověřil minimum HA 2026.8.0/plugin 0.13.354 a aktuální stabilní HA 2026.10.1/plugin 0.13.372. Linuxové CI navíc obsahuje skutečný HTTP průchod minutového profilu a parametrizovaný HA setup se třemi časovými zápisy: import nového dne, zachování historie a původního entity ID, osm statistik po 24 bodech a opakovaný import bez duplicity. Tyto HA testy se do výsledku lokální unit sady nezapočítávají.

Zavedeno ve v0.2.5, zachování příčiny ve v0.2.6 a nezávislá dostupnost historie ve v0.2.7. Výsledky starších verzí níže jsou historický záznam, nikoli důkaz správnosti nového kódu. Příprava/publikování release automaticky neaktualizuje produkční HA; instalace a restart se provádějí samostatně.

## NaN/Infinity nesmí zastavit nové platné dny (v0.2.8)

V0.2.5 zpřísnila validaci a proti v0.2.4 začala kvůli jedné NaN/Infinity
hodnotě odmítat celý profil HTTP 200. To je chyba rozsahu odmítnutí, nikoli
důkaz, že chybí celá historie. Kalendářní formát požadavku se nemění.
V0.2.8 vynechá jen dotčený interval. Zbývající kompletní hodiny a dny lze
načíst, zatímco starý uložený platný den nepřepíše neúplný nový výsledek.
NaN/Infinity se **nepřevádí na nulu**; v0.2.4 je takto nulovala, což mohlo
zkreslit sdílení. `missing_measurement_days`/`missing_measurement_intervals`
počítají i tyto značky, bez EANů nebo naměřených hodnot. Známý chybný interval
brání potvrzení úplnosti dané hodiny/dne a posunu historického kurzoru, ale
nezahazuje ostatní dny. Zcela nepoužitelná odpověď není úspěšné měření.

Příklad: uložený 12. říjen, v odpovědi neplatná hodnota pro 12. říjen,
platných 96 čtvrthodin 13. října a nezveřejněný 14. říjen. Výsledek zachová
uložený 12. říjen, přidá 13. říjen i jeho 24 hodin a nevytvoří nulu pro
14. říjen. ID, data dřívějších dokladů a dashboard se nemění. Chybný text,
bool, struktura, jednotka, role nebo konečné číslo přetékající float se
nadále odmítají. Již uložené čekání i serverový Retry-After platí až do
svého termínu; aktualizace je nemaže. Po HACS aktualizaci a restartu proto
ověřte `result`, `last_success`, `latest_data_day` a body Recorderu, ne jen
HTTP 200 nebo přítomnost entity.

## Přesný krok přihlášení (diagnostická oprava)

`original_failure.authentication_step` a položka `krok` v prvním varování
rozlišují původní autorizační GET (`authorization_get`), jeho následný GET
(`authorization_redirect_get`), POST přihlašovacího formuláře
(`credentials_post`), jeho následný GET (`credentials_redirect_get`), výměnu
kódu za token (`code_exchange_post`) a obnovu tokenu (`refresh_token_post`).
Autorizační callback obsahující kód se nestahuje: následuje výměna tokenu,
nikoli redirect GET. Krok odpovídá poslední prováděné HTTP operaci; při
timeoutu či kontrole cíle zůstává zachován bez dalšího pokusu. Samostatná
fáze `authentication` dál označuje celý přihlašovací tok.

Do Store, logu, entity i exportu se propustí pouze tyto pevné názvy a známý
bezpečný důvod. Neznámý serverový text, HTML, URL, query parametry, cookies,
hesla ani tokeny se neukládají. Staré záznamy mají krok `null`; aktualizace
jej zpětně nevymýšlí. Po restartu a během čekání nový zaznamenaný krok zůstává
stejný. Potvrzené neplatné jméno/heslo si zachová vlastní důvod `credentials`;
samotné HTTP 403 zůstává `http`/`permission` a neurčuje příčinu odmítnutí.

Tato změna opravuje ztrátu diagnostického kroku, **neprokazuje odstranění
živé HTTP 403**. Parametry OIDC, formulář, práce s cookies, počty požadavků,
statistická ID, historie, dashboardy a doklady se tím nemění.

### Zrušení místní šestihodinové blokace login HTTP 403

Po výslovném požadavku uživatele nemá přihlašovací HTTP 403 kategorie
`permission` bez platného serverového `Retry-After` vlastní šestihodinový
blok. Chyba a její přesný krok se uloží; jeden neúspěšný požadavek se uvnitř
operace neopakuje. Další pokus řídí běžný plánovač HA (výchozí obnova hodinu),
stejně jako před přidáním této blokace ve v0.2.5. Aktualizace s restartem
umožní běžný nový pokus a sama nepotvrzuje obnovení přístupu.

Při načtení Store se zruší i již uložený blok `account`, ale pouze pokud
výslovně nese `local_policy`, fázi `authentication`, kategorii `permission`
a HTTP 403. Původní důvod se zachová bez falešného `recovered_at`.
Serverový `Retry-After`, staré neznámé blokace, MFA/CAPTCHA a omezení
čtecího API zůstávají platné. Opětovné odmítnutí kvůli souběžnému sezení
se touto změnou neřeší ani neobchází.

## Kde najít původní chybu (v0.2.6)

1. **Nastavení → Systém → Protokoly**, logger `custom_components.edc_sharing.api_policy`: první chyba je WARNING i před dokončením setupu. Záznam obsahuje pevný bezpečný důvod, HTTP status (také 200 při chybě validace odpovědi), fázi, známý endpoint/kalendářní rozsah, povolené validační kódy/pole, původ čekání a další UTC termín. Volné texty serveru, hodnoty polí, EANy a přihlašovací údaje se nelogují.
2. **Stáhnout diagnostiku instance**: `original_failure` existuje také při `setup_retry`, kdy `entry.runtime_data` dosud nevznikl. `ready` znamená existenci runtime, nikoli ověřenou funkčnost API. Když ještě probíhá čtení místní politiky, export ukáže fázi `loading_local_policy`; nevymýšlí HTTP příčinu.
3. Diagnostická entita **Poslední pokus o načtení dat** nabízí `original_failure`, `cached_startup`, výsledek a termín dalšího pokusu. Admin-only `edc_sharing/statistics/health` vrací startup diagnostiku i bez runtime; v tomto stavu je `connection_probe: not_probed`, také s `fresh: true`. Bez připravené instance se žádný nový request nespustí.

Uložení používá dosavadní HA Store `.storage/edc_sharing.api_wait.<hash účtu>` včetně `last_failure`; soubor neobsahuje hesla/tokeny nebo nezahashovaný účet. Volný uložený text se při obnově znovu odmítá: důvod vzniká z whitelist kódu. Příčina zůstává i po vypršení čekání; ověřená obnova má samostatný čas `recovered_at`. Stejné čekání samo původní příčinu nepřepisuje, neprodlužuje lhůtu a nezapisuje další WARNING při každém pokusu HA. Chyba ukládání má vlastní varování a příznak `wait_persistence_failed`; paměťové omezení zůstane platné.

`wait_source` je `local_policy`, `server_retry_after`, `not_scheduled` (například odmítnuté heslo přechází na reauth) nebo `legacy_unknown`. Starý v0.2.5 soubor měl pouze kategorii a termín. Z něj **nelze** zjistit původní HTTP status, detail parseru ani prokázat, zda šlo o Retry-After. Proto se starý termín nemění automaticky a původ se poctivě označuje jako neznámý. To, že v0.2.6 opravuje null/regresní scénář, není důkaz, že právě null způsobilo původní živou chybu.

## Dostupná historie při neúspěšném stahování (v0.2.7)

Platné uložené kWh, souhrny a data jejich měření jsou dostupné ve stejných entitách i při chybě nového čtení. Čekání na poslední den nesmí znepřístupnit předchozí dny. V0.2.6 nesprávně používala dostupnost posledního HTTP jako dostupnost celé historie; HA potom schoval i `data_date`, `available_days`, `shared_kwh` a rozsahy, takže markdown karty ukazovaly prázdno/náhradní nuly. V0.2.7 odděluje tyto podmínky: `has_available_history` ověřuje existenci skutečného datového dne; `last_update_success` zůstává false při chybě sítě. `cached_startup`/`cached_only` a `data_source: retained_history` označují původ, nikoli neplatnost nebo „zastaralost“ historie. ID, jednotky, vlastní názvy, datum posledního dne a externí body se zachovají; dashboard se nepřepisuje a generátor nepotřebuje měnit své odkazy.

Výrobní/cílové identity se obnoví z metadat historie nebo z registru pouze stejné config entry a přesně známých unique ID. Registr se nemění ani se EAN neodvozuje z cizí instance. Tyto identity nejsou potvrzení aktuální alokace; platné historické hodnoty cíle nezmizí jen proto, že cíl není v posledním profilu. Bez validní cache se energie nevymyslí jako nula a zůstává standardní setup_retry. Odmítnuté heslo spustí reauth; s historií je přehled dál dostupný, timer se vypne a další pokusy koordinátoru nepřepošlou heslo před opravou přihlášení.

Do skutečné obnovy čtení jsou automatické importy do Recorderu/Energy, pokračování backfillu a plánované reporty vypnuté. Aktivační listener je spustí jednou po úspěchu; při dalších aktualizacích nevytváří další plánovače. První další pokus je naplánován až po uloženém termínu, potom se obnoví běžný hodinový interval. Unload/restart používá standardní rušení listenerů a časovačů HA. Obnova sama neodesílá okamžitý e-mail, nevystavuje doklad ani nepotvrzuje úhradu. Ruční již existující funkce mají své původní kontroly a potvrzení.

## Ochrana dat a požadavků

Oprava v0.2.6 je ověřena [Linuxovým během 38533348619](https://github.com/79thales/edc-sharing-stats/actions/runs/38533348619): devět povinných kontrol úspěšných, 42 skutečných funkčních HA testů na každé přesné dvojici 2026.8.0/0.13.354 a aktuální stabilní 2026.10.1/0.13.372. Lokálně prošlo 193 unit testů a oba frontendy; 22 kontrol vyžadujících HA proběhlo samostatně v CI. Nové `test_startup_diagnostics.py` ověřují skutečný config-entry setup, diagnostiku bez runtime, existující cache/legacy deadline, dostupnou diagnostickou entitu, zákaz automatických importů/reportů při startu a jejich jednorázové zapnutí po obnově. Syntetické API odpovědi se nepovažují za živý EDC canary a HA storage fixture neprokazuje fyzickou diskovou persistenci. Současný produkční API incident má ze starého záznamu prokazatelnou jen kategorii a termín; konkrétní stará příčina není doložená.

`build_profile_request` přijímá kladné celočíselné ID skupiny a místní kalendářní interval `[od, do)`. Odesílá nejvýše 31 dnů s oběma krajními dny včetně. Nepřijímá datetime ani boolean jako číslo skupiny. Všechny obnovy, reporty a backfill používají stejnou konverzi.

Validace odpovědi kontroluje seznamy, sloupce, role, směry, vektory hodnot, čísla a časové rozlišení. Kompatibilní volitelné položky nebrání čtení. Podporována je starší výslovně prázdná odpověď `content=[]` bez sloupců; chybějící content nebo null se za platné prázdno nepovažují. Denní součet není hodinový interval. Samé celé hodiny bez konce jsou nejednoznačné; pro hodinový import musí být rozlišení doložené. Čtvrthodinová data bez end lze rozpoznat podle skutečných nenulových minut, ale úplná hodina vyžaduje všechny čtyři sloty.

Úplnost se počítá odděleně pro obě podzimní UTC hodiny. Úplný den musí pokrýt všechny skutečné hodiny Europe/Prague, tedy 23/24/25 podle databáze pásma. Neúplná hodina se nepřidá do Recorderu a neúplný den není kompletní podklad vyúčtování. Neznámé schéma se nezamění za nulovou energii. Jednostranný profil má rozpoznané role, ale bez dalšího důkazu neprokazuje počátek skupiny: backfill přes neověřený blok neposune kurzor a lze jej později obnovit. Běžná obnova může využít ostatní úplné bloky.

## Obnova po chybě

Čtení používá jeden sdílený zámek a čekání pro účet, včetně nastavovacích průvodců. HTTP odmítnutí se omezuje pro skupinu/cestu, 429 a dočasná nedostupnost pro celý účet. 400/422 se neopakuje okamžitě. Dočasná chyba čtecího požadavku má nejvýše dva další pokusy s čekáním přibližně 5 a 30 sekund; čekání je asynchronní. Platný Retry-After má přednost. Bez něj je následná běžná lhůta hodina, u HTTP změny kontraktu nebo oprávnění šest hodin. Od v0.2.6 lokální validace již přijatého profilu chrání pouze přesné období patnáct minut; nejnovější blok se načítá první a platná data nezahodí chyba schématu starého bloku. Jde o politiku integrace, nikoli zjištěný limit EDC; serverové ani staré neznámé ochrany se nezkracují.

Explicitní null ve známém vektoru je nedostupné měření. Parser vynechá celý interval bez nulové náhrady, úplnost hodin/dnů ověří ze zbylých skutečných slotů. `missing_measurement_days`/`missing_measurement_intervals` ukazují rozsah mezer, ne období před vznikem EANu. Nula je stále validní měření. Chybějící `v`, bool, prázdný text, krátký vektor a změněné významové schéma nejsou tímto povolené. Zcela null uzavřený den nesmí posunout backfill kurzor ani tehdy, když parser nemá žádný denní řádek. Při podzimním opakování hodiny se výskyt slotu počítá i pro null, aby druhý UTC fold zůstal správný.

API 401 smí vyvolat jedno obnovení přihlášení a jedno zopakování čtení. Potvrzené odmítnutí hesla se nezopakuje. Přihlašovací cíle jsou omezeny na známý HTTPS origin a callback; cizí formulář/redirect se nepoužije. Přesměrování čtecího API se neprovádí automaticky.

Technická chyba tokenové služby se neopakuje jako čtení profilu a nezpůsobí další odeslání hesla. Odmítnutý refresh s doloženým `invalid_grant` dovoluje jediný nový login; neznámá HTTP 400 nikoli. MFA/CAPTCHA vyžaduje ruční zásah (`user_action`), chybný OIDC state je změna kontraktu, ne neplatné heslo. Nastavovací a reauth průvodce používají stejný účetní zámek. Změna deklarované energetické jednotky z kWh se zastaví; integrace neodhaduje převod Wh/MWh podle velikosti čísla.

UTC termíny a bezpečné kategorie se ukládají v HA Store. Běžící lhůta používá také monotónní čas, aby posun systémových hodin nepovolil předčasný pokus. Obsah Store neobsahuje tokeny, hesla, EANy nebo osobní jména. Chyba ukládání nesmí zastřít původní HTTP status; paměťové čekání zůstává aktivní. Zrušení úlohy musí uvolnit spojení i zámek. Po prvním neúspěšném setupu může HA opakovat pokusy podle vlastního plánu, ale klient během uložené lhůty neprovádí další HTTP požadavky.

## Skutečné statistiky v HA

Administrátorský WebSocket příkaz `edc_sharing/statistics/health` potřebuje vlastní `entry_id`; volitelné `date_from` a `date_to` určují ISO interval s koncem bez posledního dne, nejvýše 31 dnů. Bez období se zvolí poslední datový den, případně včerejšek. Kontrola používá veřejné rozhraní Recorderu, čte maximálně vlastní skupinu a 100 známých cílů a má timeout 30 sekund. Neposílá požadavky na EDC a nic nemaže ani nevystavuje.

Výchozí kontrola vrací v `checks` výslovně `not_probed` pro přihlášení/skupiny a `cached_only` pro profil: cache není živý test připojení. Volitelný parametr `fresh: true` provede oddělený `connection_probe`: čtení seznamu skupin, ověření přítomnosti vlastní skupiny, čtení jednoho dne od `date_from` a parser. Má celkový timeout 120 sekund a podléhá společnému retry/čekání API. Neimportuje data, nemění finanční evidenci ani uložený dashboard. Počet bodů Recorderu se vyhodnocuje nezávisle; úspěšná HTTP odpověď není důkaz importu.

Příklad administrátorského požadavku (ID nahradit vlastní hodnotou):

```json
{"id": 1, "type": "edc_sharing/statistics/health", "entry_id": "VLASTNI_ENTRY_ID", "date_from": "2026-10-12", "date_to": "2026-10-13", "fresh": false}
```

Jde o diagnostické WebSocket rozhraní, nikoli novou běžnou energetickou entitu nebo automaticky spouštěné tlačítko. Neoprávněný uživatel jej nemůže spustit ani pomocí `fresh`. Chybějící Recorder vrací bezpečnou chybu, ne zelený stav.

Výsledky: `missing_statistic` = chybí metadata; `empty_period` = statistika existuje, ale ve zvoleném období nemá mean body; `available` = jsou skutečně uložené body. `points`, jednotka a první/poslední UTC čas jsou potvrzeny čtením databáze. `queued_hours` v diagnostice je počet bodů pouze zařazených do fronty a nesmí se zaměňovat s potvrzeným zápisem. Běžná HA entita není pro externí statistiku nutná.

Sdílitelný diagnostický export používá samostatný whitelist a vynechává konfiguraci, EANy, jména, zprávy vzdálených chyb, bankovní účty a doklady. Soukromý administrátorský detail může obsahovat vlastní ID statistik; před jeho veřejným sdílením je anonymizujte.

Generátor zachovává hlavní přehled a původní detaily. Nové hodinové grafy posledních tří dnů nejsou vázány na dnešní výběr data. Samostatná podstránka `hourly-date` používá nativní výběr dne a vlastní collection_key, společný jen pro její grafy. Vyberte minulý den. Pokrytí je procento z energií dané hodiny, nikoli součet procent za období. Distribuovaný příklad je `examples/dashboard-hourly.yaml`; nepřepisuje instalovaný dashboard automaticky.

## Sledování portálu

Z kořene repozitáře spusťte `python scripts/check_edc_portal.py`. Jediný veřejný GET má limit 20 sekund/2 MiB a respektuje ETag/Last-Modified. Referenční veřejný otisk byl zachycen 14. 10. 2026 v `examples/portal-public-baseline.json`. Výsledek `changed` oznamuje jiný build; nepotvrzuje změnu API ani jeho dostupnost po přihlášení. Prázdná/nepoznaná stránka je inconclusive, porucha připojení unavailable. Nový vzdálený build nepřepisuje schválenou referenci automaticky. Existující denní/ruční CI ukládá pouze tento veřejný advisory report.

`--calendar` přidá jeden GET oficiálního [ICS kalendáře EDC](https://www.edc-cr.cz/kalendar-edc.ics), který je odkazován z [kalendáře EDC](https://www.edc-cr.cz/kalendar-edc.html). Čte UTC, TZID i celé dny s výchozím pásmem Europe/Prague; koncová mez je výlučná. Nejednoznačný/neexistující lokální čas, neznámý formát nebo nepodporované opakování znamená `inconclusive`. Výstup obsahuje pouze druh události, systém, UTC okno a příznak aktivity, nikoli UID/popis. EDC-SAKU, SEBI a AFLEX se vyhodnocují odděleně. Skončená odstávka ani oznámení jiného systému neskrývá trvající chybu připojení.

Pro opakované lokální použití lze přidat `--state cesta-ke-stavu.json`: nástroj uloží jen anonymní signaturu. Stejný výsledek má `event: null`, změna `observation_changed`, obnovení dostupnosti `recovered`. Tento parametr nezakládá plán ani notifikace. CI používá již existující denní/ruční plán, nevytváří nový, neotvírá issues a neposílá e-mail.

`python scripts/probe_edc_portal.py` bez parametrů vrací `disabled` a nezahájí síť. Pro soukromý průchod je třeba Playwright 1.64.0 s Chromium, čerstvá testovací browser session, privátní mapa popisků a výslovné `--enabled`. Použití: `python scripts/probe_edc_portal.py --enabled --config edc-probe.private.json --storage-state storage-state.private.json`; volitelný `--baseline` ukazuje na schválený anonymní kontrakt. První průchod bez reference je inconclusive a vrací návrh anonymního kontraktu k přezkoumání.

Privátní mapa obsahuje `group_label`, `group_name`, `sse_id`, `date_from_label`, `date_to_label`, `date_from_display`, `date_to_display`, `date_from`, `date_to` a `show_button`. Je nutné ji ověřit proti aktuálnímu portálu. ISO meze jsou oba krajní dny včetně a mají představovat známý historický den s daty. Skupina se hledá podle role/popisku, pouze jako záloha slouží známé ID `mui-component-select-sseId`. Síťová odpověď se očekává již před kliknutím. Ověří se příslušnost skupině/období a porovná se metoda/cesta a schéma. Surové HAR, cookies, hlavičky, osobní údaje a měřené profily se neexportují. Script nesmí měnit členství, alokace nebo platby a neprovádí automatické opravy produkčního API.

Volitelný objekt `current` používá stejné čtyři datové položky pro druhý, čerstvý den. Prázdný aktuální den se popíše jako možný skluz zveřejnění; prázdný známý historický referenční den je `inconclusive`. Každé období musí být jediný den. Maximum je pět skutečně povolených profilových POSTů, dva OIDC tokenové POSTy a 80 požadavků celkem; souhrnný timeout 120 sekund. Password grant, neznámé API cesty, cizí originy a všechny mutace jsou zakázány. Chybějící/změněná legitimní cesta vyžaduje prověření allowlistu, ne automatické povolení.

Zámek `<storage-state>.probe.lock` zajišťuje jeden souběžný proces na privátní profil. Běžné ukončení/zrušení jej odstraní. Po pádu může zůstat; neodstraňujte jej, dokud neověříte, že původní proces neběží. Vypršelou session obnovte ručně v odděleném testovacím profilu. Nástroj nevyhledává ani nepřebírá cookies běžného prohlížeče uživatele a není obcházením omezení asistentského browser nástroje.

Výsledky `disabled`, `inconclusive` nebo `unavailable` se nikdy nezapočítávají jako živý API test. Ani potvrzený oficiální kalendář neprokazuje příčinu chyby HTTP 400. Oznámení se musí vztahovat ke správnému systému a jeho času; po skončení odstávky je nutné ověřit obnovu.

## Přejímací matice

| Scénáře zadání | Hlavní důkaz |
| --- | --- |
| A01–A04 | Existující kalendářní regrese a generované rozsahy v test_api_resilience. |
| A05–A07 | Skutečný lokální aiohttp server, očekávaný serializovaný JSON a odmítnutý nový kontrakt bez opakování. |
| A08–A11 | Přesná jedna obnova tokenu, bounded retry, sdílený/obnovený termín a zrušení úlohy. |
| A12–A14 | Struktura místo prázdna, ochrana login originu, chybové tělo a kontrola nepřítomnosti soukromých údajů. |
| D01–D05 | Nové strukturální/číselné případy, benigní rozšíření, částečné intervaly a zákaz falešné půlnoční hodiny. |
| D06–D10 | Dosavadní DST/individuální regrese a skutečné čtení Recorderu, korekce, opakování a restart. |
| Nativní graf | Test_hourly_browser: dvě známé hodiny a úplné 23/25hodinové DST dny; skupina i cíl, skutečné canvas/data a přepnutí z prázdného dne na historický den. |
| Změna portálu | Test_portal_contract: oddělený build a API kontrakt, bez identit a naměřených hodnot. |

Povinné testy se provádějí v přesném minimálním a aktuálním stabilním HA prostředí s odpovídajícím pytest pluginem a frontendem. Chybějící prostředí se nesmí nahradit beta/starší verzí ani tiše přeskočit. Skutečný živý přihlášený EDC průchod je samostatná kontrola; bez testovací session jeho kompatibilita zůstává neověřená. Konkrétní výsledky CI jsou součástí předání změny.

## Důkazy a známé meze v0.2.5 – 14. 10. 2026

Na finálním kódovém commitu `608fce64a04782859b2c830f08e8f68eefe1c17e` proběhl [Linuxový Validate běh 38522438041](https://github.com/79thales/edc-sharing-stats/actions/runs/38522438041): všech deset kontrol úspěšných, včetně spuštění veřejného monitoru při ručním běhu. Obě skutečná HA prostředí měla po 38 úspěšných testech, včetně 23/25hodinových vykreslených grafů, jednotek kWh/%, odděleného fresh probe, oprávnění a diagnostické redakce. Test neúplného backfillu zachoval kurzor i dobrou historii a obnovil je v nové HA instanci přes standardní JSON storage fixture. Samostatný restart Recorderu používá skutečnou SQLite databázi. Tyto dvě persistence kontroly nejsou zaměňovány.

Lokální jednotková sada: 204 nalezených testů, 182 úspěšných a 22 HA-specifických kontrol provedených samostatně v Linuxových kompatibilitních bězích. Oba JavaScriptové frontendové testy prošly. Nativní Windows HA test není započítán jako úspěch: runtime dříve narazil na OpenSSL Applink, proto skutečné HA testy proběhly v přesných Linuxových prostředích. Screenshoty v CI artefaktech jsou pouze syntetické grafy, bez reálných účtů či session; podzimní graf byl rovněž vizuálně zkontrolován.

| Kontrola | Verze / výsledek / omezení |
| --- | --- |
| Minimum HA | 2026.8.0 + pytest-homeassistant-custom-component 0.13.354, přesný frontend dle manifestu HA. |
| Nejnovější stabilní HA | Resolver při ověření vybral 2026.10.1 + plugin 0.13.372, bez beta nebo náhrady starší verzí. |
| Doplňková kompatibilita | HA 2026.9.0 a importy všech nových modulů. |
| Veřejný portál, živě | `ok`, 13 build assetů, otisk shodný s referencí; nejde o test přihlášeného API. |
| Veřejný portál z GitHub runneru | Report `unavailable/transport`; úspěch CI jobu znamená korektní provedení monitoru, nikoli dostupnost webu. Lokální výsledek výše a tento vzdálený výsledek nejsou zaměňovány. |
| Oficiální ICS, živě | `ok`; potvrzeno okno EDC-SAKU 13. 10. 2026 14–15 UTC = 16–17 Europe/Prague; 14. 10. již neaktivní. |
| Oficiální ICS z GitHub runneru | `ok`; samostatná kontrola strojového zdroje, nikoli přihlášení EDC. |
| Přihlášený EDC, živě | Neprovedeno: není předána čerstvá oddělená testovací session. Bez ní není potvrzena aktuální produkční kompatibilita. |
| Živý HA / zákaznický dashboard | Nezměněn, neupgradován; průchod grafem je izolovaný syntetický Linux test. |

Minimální reprodukce chráněné regrese: server vyžaduje nové pole a vrátí HTTP 400. Klient udělá jediný čtecí požadavek, nevynutí další heslo, vrátí `validation` a uloží nejbližší další pokus. Druhý okamžitý pokus síť nepoužije. Současná skupina po 429 respektuje již uložený společný termín. Jiný případ: odpověď 200 bez `content` je `contract`, nikoli úspěch s nulovými statistikami.

Sanitizovaný příklad exportu (nikoli reálné osobní údaje):

```json
{"ready": true, "http_status": 400, "failure_category": "validation", "data_quality": {"resolution": "quarter_hour", "queued_hours": 24, "incomplete_hours": 0}}
```

`queued_hours: 24` znamená frontu, nikoli 24 ověřených bodů. Potvrzení je až čtení `statistics/health`. Existující vyúčtování, potvrzené úhrady a identifikátory statistik se nemigrují ani nemažou. Selhání backfill bloku se uloží jako obnovitelné; kurzor zůstane před neověřeným blokem. Vývoj zde neopravuje neznámý kontrakt z jedné vzdálené odpovědi automaticky.

## Ověření dostupnosti historie v0.2.7 – 14. 10. 2026

[Validate 38541682766](https://github.com/79thales/edc-sharing-stats/actions/runs/38541682766) úspěšně dokončil všech devět povinných kontrol na kódovém commitu `7671b7d8fa0e5951e24eb709986fd4cd69531c6e`. Každá přesná dvojice HA/plugin 2026.8.0/0.13.354 a aktuální stabilní 2026.10.1/0.13.372 provedla 47 skutečných funkčních testů. Vedle toho prošlo 193 unit testů, samostatné kompatibilitní kontroly HA 2026.8.0/2026.9.0/latest, oba JavaScriptové frontendy, HACS, Hassfest a lint. Veřejný advisory monitor se při push očekávaně nespouští; není součástí tvrzení o dostupnosti přihlášeného EDC.

Nové testy používají skutečný setup HA, registr s vlastními původními názvy a ID, Store fixture, entity, koordinátor a Recorder. Ověřují dostupnost posledních 10 kWh s původním datem a souhrnovými atributy po selhání, obnovení výrobního EANu, zachování skutečně uloženého hodinového bodu a zákaz importu/reportu během čekání. Dále ověřují všechny skupinové i cílové senzory při chybějícím/null posledním dni, žádný falešný nulový den, opakované selhání, jeden návrat plánovače po obnově a reauth bez opakovaného odeslání odmítnutého hesla. Hodnoty a identity v testech jsou syntetické, nikoli zákaznické údaje.

Tyto výsledky dokládají opravu dostupnosti uložené historie a kompatibilitu kódu, nikoli původní příčinu živé chyby API. Starší verze její konkrétní důvod neuložila; nový release jej zpětně nemůže rekonstruovat. Nasazení vyžaduje aktualizaci a restart vlastního HA. Po něm zkontrolujte stejná entity ID/názvy, skutečný poslední datový den, počty pokrytých dnů a čtené body Recorderu; žádné z těchto ověření nenahrazujte pouhou existencí integrace nebo zeleným výsledkem CI.
