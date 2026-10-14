# Diagnostika skutečných časových hranic

V0.2.9 je podle načteného manifestu i souborů skutečně nainstalovaná v HA. Klient nadále odmítá profil HTTP 200 jako `profile_resolution`. Samostatný čtecí pokus po vypršení uvedené lhůty skončil v `credentials_post` s HTTP 403. Není to důkaz chyby profilu ani úspěšného odchycení odpovědi. Funkční WPF reference je na `H:\01.programovani\webdownloader\src\OrlenPriceDownloader\MainWindow.xaml.cs` a čte vykreslenou tabulku; neznáme ještě surové hranice, které nyní odmítá integrace.

Změna přidává jediný log `EDC časový kontrakt` přímo do existujícího klienta při odmítnutí právě přijaté odpovědi. Kontrola schématu předchází výpisu. Výstup obsahuje počet řádků, rozlišení jednotlivých řádků a nejvýše šest vzorků start/end včetně prvního a posledního řádku. Přesné řetězce se povolují pouze pro časové literály, případně ISO datum s časem a offsetem. Jiná data se nahradí pevnou značkou typu. Pořadí není EAN ani identita skupiny. Hodnoty měření, sloupce, příjemci a přihlašovací údaje se nevypisují.

Diagnostika nemění parser, validaci, počet HTTP požadavků, limity, časování, entity, statistiky, historii ani vyúčtování. Platný profil žádný nový chybový log nezaloží. Smyšlený konec `12:14:59` v testu pouze ověřuje zachycení nenulových sekund; není tvrzením o živém formátu EDC.

Lokálně prošlo 51 cílených kontrol včetně pěti nových testů redakce, omezení výpisu, zachování odmítnutí a zákazu opakování HTTP. Přidání logu není oprava významu skutečné odpovědi; tu lze napsat až podle zachycených hranic. Produkční nasazení vyžaduje souhlas s výměnou jediného `api.py` a restartem HA, potom se použije nejbližší normálně povolené načtení.
