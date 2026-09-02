# EDC Sharing Stats

[![Otevřít repozitář v HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=79thales&repository=edc-sharing-stats&category=integration)

Vlastní integrace pro Home Assistant, která načítá vyhodnocení skupiny sdílení elektřiny z českého portálu EDC.

## Funkce

- přihlášení k EDC přes uživatelské rozhraní Home Assistantu,
- automatické načtení a výběr skupiny sdílení,
- denní a měsíční hodnoty sdílení, spotřeby, dokupu a přetoků,
- procentuální pokrytí spotřeby sdílenou elektřinou,
- nastavitelná prodejní cena v Kč/kWh,
- výpočet tržby/zisku z výroby jako `nasdílené kWh × prodejní cena`,
- automatické stažení denní historie za předchozí a aktuální kalendářní měsíc,
- hodinová aktualizace a podpora dlouhodobých statistik Home Assistantu,
- opětovné zadání hesla, pokud EDC uložené údaje odmítne.

> [!IMPORTANT]
> Výpočet označený jako zisk neodečítá investiční ani provozní náklady. Jde o hodnotu skutečně nasdílené energie při nastavené ceně.

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

Skupinu a cenu lze později změnit přes **Nastavení → Zařízení a služby → EDC Sharing Stats → Nastavit**. Přístupový token zůstává pouze v paměti; po restartu se integrace přihlásí znovu uloženými přístupovými údaji.

## Vytvářené senzory

- nasdíleno, spotřeba, dokup, nevyužitý přetok, pokrytí a tržba za dnešek,
- nasdíleno, spotřeba, dokup, přetok výrobny, nevyužitý přetok, pokrytí a hodnota výroby za aktuální měsíc,
- nastavená prodejní cena.

Integrace vytváří celkem 14 senzorů. Nejde o duplicity: šest patří dnešku, sedm aktuálnímu měsíci a jeden představuje nastavenou prodejní cenu. Každý senzor má vlastní jedinečný identifikátor a lokalizovaný název.

## Historie a dlouhodobé statistiky

Při načtení integrace se automaticky stáhnou uzavřené dny od prvního dne předchozího kalendářního měsíce do včerejška. EDC povoluje v přehledu nejvýše 31 dní, proto integrace delší období sama rozdělí na několik požadavků a výsledky sloučí bez duplicit. Jednou denně historii znovu načte, takže doplní nově uzavřený den i případné opravy na straně EDC.

Starší denní hodnoty se zapisují podporovaným API jako externí dlouhodobé statistiky. Nevytvářejí falešné zpětně datované změny stavů v databázi Recorderu. Statistiky mají identifikátory ve tvaru `edc_sharing:<ID skupiny>_shared_daily`, `consumption_daily`, `grid_daily`, `unused_daily`, `coverage_daily` a `revenue_daily`. Lze je vybrat v panelu Historie nebo v kartě **Graf statistik**; zobrazovaným typem je `mean` (každý den obsahuje jedinou denní hodnotu).

Běžné senzory se nadále obnovují jednou za hodinu a Home Assistant jejich stavy ukládá od okamžiku instalace. Energetické senzory mají třídu stavu `total` a podporují také standardní dlouhodobé statistiky.

Aktuální verze používá denní vyhodnocení EDC. Čtvrthodinové a skutečné hodinové profily zatím nejsou vystavené jako samostatné senzory.

## Omezení a bezpečnost

- Integrace používá webové API portálu EDC, které není veřejně garantované a může se změnit.
- Účty vyžadující další interaktivní krok nebo vícefaktorové ověření zatím nejsou podporované.
- Heslo je uloženo v konfigurační položce Home Assistantu. Chraňte přístup k adresáři konfigurace a zálohám.

## Podpora

Chyby a návrhy hlaste v [GitHub Issues](https://github.com/79thales/edc-sharing-stats/issues).

Tento projekt není oficiálním produktem ani podporovanou integrací Elektroenergetického datového centra, a. s.
