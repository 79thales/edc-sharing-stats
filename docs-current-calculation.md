# Aktuální výpočet EDC a oprava historie (#10)

## Prokázaná příčina a hranice ověření

Do v0.2.11 builder požadoval `calculationType: DAILY` pro všechny dny. Měření
v issue #10 porovnalo září 2026: DAILY 102,38 kWh, portál CURRENT a MONTHLY
91,84 kWh. Tyto hodnoty jsou podkladem od oznamovatele, nikoli nově provedeným
měřením testů. Oprava nemění řízení spotřebičů ani ceny elektřiny.

Veřejný portál byl ověřen 18. 10. 2026, build `po846PJHBbVlHAyiuyQaw`,
chunk `35d5b5bf44469d37.js`: režim CURRENT vynechává calculationType a
serializuje currentEnteredDateTime pomocí Date.toISOString(). Měsíční a denní
režimy posílají explicitní enum a čas výběru vynechávají. Oprava používá
první variantu, bez automatického návratu k DAILY při chybě nebo prázdnu.

## API, čas a kvalita

Vnitřní kalendářní meze zůstávají místní `[od, do)`; API převádí konec na
včetně pouze jednou. UTC se používá pro čas výběru revize a hodinové klíče,
nikoli k posouvání dne. Jedna aktualizace/backfill nebo sestavení reportu
sdílí snímek v rámci stejné async úlohy. Nová background task má vlastní
snímek i při zdědění kontextu. Chyba/zrušení kontext spolehlivě obnoví.

CURRENT je požadovaná volba, ne důkaz skutečného MONTHLY ani nezměnitelnosti.
Odpověď nám zatím nedává ověřené pole skutečného typu kalkulace, proto jej
uvádíme `unknown`. Diagnostika počítá values[].q jako buňky všech EANů a
směrů, odděleně Z46/Z66/Z99/unknown. Podíl Z66+Z99 používá tento výslovně
uvedený jmenovatel; nejde o procento časových intervalů ani certifikát finality.

## Přenačtení a souběh

Legacy cache zůstává při startu dostupná. Chybějící provenience CURRENT
znamená potřebu nového čtení také pro kompletní dny, nezávisle na mezerách
backfillu #8. Po úspěšném běžném připojení a povolení importů startuje jedna
background fronta uzavřených uložených měsíců od nejnovějšího. Každý požadavek
má nejvýše 31 dní; účetní HTTP politika, Retry-After a prodleva mezi bloky
zůstávají platné. Dokončený měsíc se kontroluje znovu po sedmi dnech kvůli
pozdějším opravám. Sedm dní je naše plánování, nikoli tvrzená lhůta EDC.

Běžná hodinová aktualizace frontu spouští; další časovač nevzniká. Aktuální a
předchozí měsíc se dále obnovují původním rozvrhem. Měsíc se zkouší nejvýše
jednou za místní den. Neúplné/prázdné odpovědi uchovají původní data a čekají
na další den. Chyba transportu/účtu zastaví zbývající frontu. Zrušení odstraní
značku rozpracovaného pokusu, takže restart může pokračovat. HA spravuje
zrušení background task při unloadu. Jediný coordinator lock serializuje
běžnou obnovu, backfill a měsíční zápis; mezi měsíci jej fronta uvolňuje.

Úspěšně se nahrazují úplné dny skupiny a všech příslušných cílových EANů se
shodou sdílené energie. Denní odpověď bez hodinového profilu nestačí k opravě
starých hodin. Neúplný den ani chybějící EAN se nevydávají za nulu. Metadata
provenience a průběh se ukládají společně s denní cache ve stávajícím Store.

Denní a hodinové statistiky používají stejná ID a původní datové časy;
opakování nahrazuje body. Kumulativní Energy se znovu sestaví z celé cache,
včetně součtů navazujících na opravené datum. Zařazení zápisu do Recorderu
není potvrzení fyzického uložení: diagnostika jej výslovně označuje jako frontu.
Funkční testy čtou skutečný Recorder a ověřují hodnoty i počty po opakování.

## Vystavené doklady

Vystavené kWh, původní ceny, čísla a potvrzené úhrady se nikdy automaticky
nepřepíší. Při otevření, novém náhledu a odeslání manager porovná dostupné
aktuální kWh s uloženými položkami. Ukáže datum/EAN, původní a nové kWh i
rozdíl. Pouhá změna ceny není změna měření. Nepřítomná historie není nula.
Dny dosud neověřené migrace se samostatně označují jako čekající na kontrolu.

Při změně nebo neověřených podkladech se nevytvoří QR, nový překrývající se
doklad ani SMTP výzva. Archiv, stažení dokladu a ruční evidence skutečně
přijatých plateb zůstávají dostupné. Toto upozornění nemění zůstatek evidence
na opravenou částku a nevytváří finanční pohyb. Automatický opravný doklad,
dobropis ani finanční dorovnání tato oprava nezavádí; původní případ se musí
samostatně zkontrolovat a vypořádat před novou výzvou k úhradě.

## Testy

Unit testy kontrolují přesný UTC payload, kontexty souběžných úloh, kvalitu,
kontrakt portálu a zachování dokladů/úhrad. Funkční testy se skutečným HA
Store/Recorderem pokrývají úplné legacy dny, dva cílové EANy, náhradu starých
hodin, denní hodnoty a navazující kumulativní Energy, idempotenci, restart,
zrušení, souběžný start, prázdný/null/jednostranný/denní profil a chybu API.
Čtvrthodinové profily jsou výslovně syntetické, bez identit živého účtu.

### Výsledky místního ověření 18. 10. 2026

- 249 unit testů: OK, v prostředí s HA bez přeskočených kompatibilitních testů.
- HA 2026.8.0 + plugin 0.13.354 + frontend 20260729.5: 78 funkčních testů OK.
- HA 2026.10.1 + plugin 0.13.372 + odpovídající nainstalovaný frontend: 78 funkčních testů OK.
- Ruff změněných kontrolovaných modulů, syntaxe JavaScriptu a oba jazykové
  běhy frontendových regresí vyúčtování: OK.

Místní běhy používají oficiální CPython 3.14.8 ve Windows. Externí testovací
launcher pouze umožňuje import nepoužívaných POSIX modulů fcntl/resource;
jakékoli skutečné zavolání jejich funkcí výslovně shodí test. Windows event
loop má povolený pouze místní loopback socketpair. Store, SQLite Recorder,
HTTP testovací server, HA logika a kód integrace zůstávají skutečné. Launcher
ani stažené runtime/balíčky nejsou součástí integrace nebo tohoto commitu.

Samostatný browserový test hodinových dashboardů nebyl v těchto místních
bězích spuštěn; dashboardy se touto změnou neupravují. Plná standardní Linux
matice včetně browserových testů zůstává předepsaná workflow repozitáře.
Živý portál byl ověřen jen čtením veřejného kódu; měření skutečného účtu ani
produkční Home Assistant nebyly během implementace měněny.
