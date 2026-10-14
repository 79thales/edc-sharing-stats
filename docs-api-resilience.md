# Odolnost EDC API – implementace a ověření

Vývojová větev `feature/api-contract-health`, základ v0.2.4. Tento návod popisuje připravovanou změnu, která dosud není vydána. Produkční HA se při vývoji neaktualizuje.

## Ochrana dat a požadavků

`build_profile_request` přijímá kladné celočíselné ID skupiny a místní kalendářní interval `[od, do)`. Odesílá nejvýše 31 dnů s oběma krajními dny včetně. Nepřijímá datetime ani boolean jako číslo skupiny. Všechny obnovy, reporty a backfill používají stejnou konverzi.

Validace odpovědi kontroluje seznamy, sloupce, role, směry, vektory hodnot, čísla a časové rozlišení. Kompatibilní volitelné položky nebrání čtení. Podporována je starší výslovně prázdná odpověď `content=[]` bez sloupců; chybějící content nebo null se za platné prázdno nepovažují. Denní součet není hodinový interval. Samé celé hodiny bez konce jsou nejednoznačné; pro hodinový import musí být rozlišení doložené. Čtvrthodinová data bez end lze rozpoznat podle skutečných nenulových minut, ale úplná hodina vyžaduje všechny čtyři sloty.

Úplnost se počítá odděleně pro obě podzimní UTC hodiny. Úplný den musí pokrýt všechny skutečné hodiny Europe/Prague, tedy 23/24/25 podle databáze pásma. Neúplná hodina se nepřidá do Recorderu a neúplný den není kompletní podklad vyúčtování. Neznámé schéma se nezamění za nulovou energii. Jednostranný profil má rozpoznané role, ale bez dalšího důkazu neprokazuje počátek skupiny: backfill přes neověřený blok neposune kurzor a lze jej později obnovit. Běžná obnova může využít ostatní úplné bloky.

## Obnova po chybě

Čtení používá jeden sdílený zámek a čekání pro účet, včetně nastavovacích průvodců. Validace se omezuje pro skupinu/cestu, 429 a dočasná nedostupnost pro celý účet. 400/422 se neopakuje okamžitě. Dočasná chyba čtecího požadavku má nejvýše dva další pokusy s čekáním přibližně 5 a 30 sekund; čekání je asynchronní. Platný Retry-After má přednost. Bez něj je následná běžná lhůta hodina, u změny kontraktu nebo oprávnění šest hodin. Jde o politiku integrace, nikoli zjištěný limit EDC.

API 401 smí vyvolat jedno obnovení přihlášení a jedno zopakování čtení. Potvrzené odmítnutí hesla se nezopakuje. Přihlašovací cíle jsou omezeny na známý HTTPS origin a callback; cizí formulář/redirect se nepoužije. Přesměrování čtecího API se neprovádí automaticky.

UTC termíny a bezpečné kategorie se ukládají v HA Store. Běžící lhůta používá také monotónní čas, aby posun systémových hodin nepovolil předčasný pokus. Obsah Store neobsahuje tokeny, hesla, EANy nebo osobní jména. Chyba ukládání nesmí zastřít původní HTTP status; paměťové čekání zůstává aktivní. Zrušení úlohy musí uvolnit spojení i zámek. Po prvním neúspěšném setupu může HA opakovat pokusy podle vlastního plánu, ale klient během uložené lhůty neprovádí další HTTP požadavky.

## Skutečné statistiky v HA

Administrátorský WebSocket příkaz `edc_sharing/statistics/health` potřebuje vlastní `entry_id`; volitelné `date_from` a `date_to` určují ISO interval s koncem bez posledního dne, nejvýše 31 dnů. Bez období se zvolí poslední datový den, případně včerejšek. Kontrola používá veřejné rozhraní Recorderu, čte maximálně vlastní skupinu a 100 známých cílů a má timeout 30 sekund. Neposílá požadavky na EDC a nic nemaže ani nevystavuje.

Výsledky: `missing_statistic` = chybí metadata; `empty_period` = statistika existuje, ale ve zvoleném období nemá mean body; `available` = jsou skutečně uložené body. `points`, jednotka a první/poslední UTC čas jsou potvrzeny čtením databáze. `queued_hours` v diagnostice je počet bodů pouze zařazených do fronty a nesmí se zaměňovat s potvrzeným zápisem. Běžná HA entita není pro externí statistiku nutná.

Sdílitelný diagnostický export používá samostatný whitelist a vynechává konfiguraci, EANy, jména, zprávy vzdálených chyb, bankovní účty a doklady. Soukromý administrátorský detail může obsahovat vlastní ID statistik; před jeho veřejným sdílením je anonymizujte.

Generátor zachovává hlavní přehled a původní detaily. Nové hodinové grafy posledních tří dnů nejsou vázány na dnešní výběr data. Samostatná podstránka `hourly-date` používá nativní výběr dne a vlastní collection_key, společný jen pro její grafy. Vyberte minulý den. Pokrytí je procento z energií dané hodiny, nikoli součet procent za období. Distribuovaný příklad je `examples/dashboard-hourly.yaml`; nepřepisuje instalovaný dashboard automaticky.

## Sledování portálu

Z kořene repozitáře spusťte `python scripts/check_edc_portal.py`. Jediný veřejný GET má limit 20 sekund/2 MiB a respektuje ETag/Last-Modified. Referenční veřejný otisk byl zachycen 14. 10. 2026 v `examples/portal-public-baseline.json`. Výsledek `changed` oznamuje jiný build; nepotvrzuje změnu API ani jeho dostupnost po přihlášení. Prázdná/nepoznaná stránka je inconclusive, porucha připojení unavailable. Nový vzdálený build nepřepisuje schválenou referenci automaticky. Existující denní/ruční CI ukládá pouze tento veřejný advisory report.

`python scripts/probe_edc_portal.py` bez parametrů vrací `disabled` a nezahájí síť. Pro soukromý průchod je třeba Playwright 1.64.0 s Chromium, čerstvá testovací browser session, privátní mapa popisků a výslovné `--enabled`. Použití: `python scripts/probe_edc_portal.py --enabled --config edc-probe.private.json --storage-state storage-state.private.json`; volitelný `--baseline` ukazuje na schválený anonymní kontrakt. První průchod bez reference je inconclusive a vrací návrh anonymního kontraktu k přezkoumání.

Privátní mapa obsahuje `group_label`, `group_name`, `sse_id`, `date_from_label`, `date_to_label`, `date_from_display`, `date_to_display`, `date_from`, `date_to` a `show_button`. Je nutné ji ověřit proti aktuálnímu portálu. ISO meze jsou oba krajní dny včetně a mají představovat známý historický den s daty. Skupina se hledá podle role/popisku, pouze jako záloha slouží známé ID `mui-component-select-sseId`. Síťová odpověď se očekává již před kliknutím. Ověří se příslušnost skupině/období a porovná se metoda/cesta a schéma. Surové HAR, cookies, hlavičky, osobní údaje a měřené profily se neexportují. Script nesmí měnit členství, alokace nebo platby a neprovádí automatické opravy produkčního API.

Výsledky `disabled`, `inconclusive` nebo `unavailable` se nikdy nezapočítávají jako živý API test. Bez stabilního ověřeného zdroje kalendáře nelze plánovanou odstávku automaticky prohlásit za příčinu selhání. Oznámení se musí vztahovat ke správnému systému a jeho času; po skončení odstávky je nutné ověřit obnovu.

## Přejímací matice

| Scénáře zadání | Hlavní důkaz |
| --- | --- |
| A01–A04 | Existující kalendářní regrese a generované rozsahy v test_api_resilience. |
| A05–A07 | Skutečný lokální aiohttp server, očekávaný serializovaný JSON a odmítnutý nový kontrakt bez opakování. |
| A08–A11 | Přesná jedna obnova tokenu, bounded retry, sdílený/obnovený termín a zrušení úlohy. |
| A12–A14 | Struktura místo prázdna, ochrana login originu, chybové tělo a kontrola nepřítomnosti soukromých údajů. |
| D01–D05 | Nové strukturální/číselné případy, benigní rozšíření, částečné intervaly a zákaz falešné půlnoční hodiny. |
| D06–D10 | Dosavadní DST/individuální regrese a skutečné čtení Recorderu, korekce, opakování a restart. |
| Nativní graf | Test_hourly_browser: dvě známé hodiny, vykreslené canvas/data a přepnutí z prázdného dne na historický den. |
| Změna portálu | Test_portal_contract: oddělený build a API kontrakt, bez identit a naměřených hodnot. |

Povinné testy se provádějí v přesném minimálním a aktuálním stabilním HA prostředí s odpovídajícím pytest pluginem a frontendem. Chybějící prostředí se nesmí nahradit beta/starší verzí ani tiše přeskočit. Skutečný živý přihlášený EDC průchod je samostatná kontrola; bez testovací session jeho kompatibilita zůstává neověřená. Konkrétní výsledky CI jsou součástí předání změny.
