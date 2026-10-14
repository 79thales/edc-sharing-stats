# Odolnost EDC API – implementace a ověření

Zavedeno ve v0.2.5, původně na větvi `feature/api-contract-health` nad v0.2.4. Tento návod popisuje chování vydání a skutečné výsledky ověření. Příprava ani publikování release neaktualizuje produkční HA; instalaci přes HACS a restart provádí správce.

## Ochrana dat a požadavků

`build_profile_request` přijímá kladné celočíselné ID skupiny a místní kalendářní interval `[od, do)`. Odesílá nejvýše 31 dnů s oběma krajními dny včetně. Nepřijímá datetime ani boolean jako číslo skupiny. Všechny obnovy, reporty a backfill používají stejnou konverzi.

Validace odpovědi kontroluje seznamy, sloupce, role, směry, vektory hodnot, čísla a časové rozlišení. Kompatibilní volitelné položky nebrání čtení. Podporována je starší výslovně prázdná odpověď `content=[]` bez sloupců; chybějící content nebo null se za platné prázdno nepovažují. Denní součet není hodinový interval. Samé celé hodiny bez konce jsou nejednoznačné; pro hodinový import musí být rozlišení doložené. Čtvrthodinová data bez end lze rozpoznat podle skutečných nenulových minut, ale úplná hodina vyžaduje všechny čtyři sloty.

Úplnost se počítá odděleně pro obě podzimní UTC hodiny. Úplný den musí pokrýt všechny skutečné hodiny Europe/Prague, tedy 23/24/25 podle databáze pásma. Neúplná hodina se nepřidá do Recorderu a neúplný den není kompletní podklad vyúčtování. Neznámé schéma se nezamění za nulovou energii. Jednostranný profil má rozpoznané role, ale bez dalšího důkazu neprokazuje počátek skupiny: backfill přes neověřený blok neposune kurzor a lze jej později obnovit. Běžná obnova může využít ostatní úplné bloky.

## Obnova po chybě

Čtení používá jeden sdílený zámek a čekání pro účet, včetně nastavovacích průvodců. Validace se omezuje pro skupinu/cestu, 429 a dočasná nedostupnost pro celý účet. 400/422 se neopakuje okamžitě. Dočasná chyba čtecího požadavku má nejvýše dva další pokusy s čekáním přibližně 5 a 30 sekund; čekání je asynchronní. Platný Retry-After má přednost. Bez něj je následná běžná lhůta hodina, u změny kontraktu nebo oprávnění šest hodin. Jde o politiku integrace, nikoli zjištěný limit EDC.

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

## Důkazy a známé meze – 14. 10. 2026

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
