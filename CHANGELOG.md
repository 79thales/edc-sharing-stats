# Přehled změn

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
