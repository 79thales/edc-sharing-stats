"""Generate native Lovelace cards in the EDC Share2 sections style.

Pure presentation code: the caller supplies registry-resolved entity IDs and
existing external statistic IDs. No EDC requests or storage writes; only clearly
labelled presentation arithmetic for the current-price period estimate.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

PANEL_PATH = "edc-sharing-dashboard"
GROUP_KEYS = (
    "shared_today",
    "consumption_today",
    "grid_today",
    "unused_today",
    "coverage_today",
    "revenue_today",
    "shared_month",
    "consumption_month",
    "grid_month",
    "overflow_month",
    "unused_month",
    "coverage_month",
    "production_profit_month",
    "sale_price",
    "surplus_utilization_latest_available_day",
    "surplus_utilization_this_week",
    "surplus_utilization_this_month",
    "surplus_utilization_this_year",
    "surplus_utilization_total",
    "last_update_attempt",
    "history_backfill_status",
    "history_earliest_date",
)
TARGET_KEYS = (
    "shared_latest_available_day",
    "consumption_latest_available_day",
    "grid_purchase_latest_available_day",
    "sharing_coverage_latest_available_day",
    "revenue_latest_available_day",
    "shared_this_month",
    "consumption_this_month",
    "grid_purchase_this_month",
    "sharing_coverage_this_month",
    "revenue_this_month",
    "sale_price",
)
# Klíče náhledu jsou prezentační názvy. Registr senzoru používá skutečné
# description.key; peníze a cenu proto překládáme výslovně, podle unique_id.
# Překlad nemění ID ani stav senzoru a funguje i po přejmenování entity.
TARGET_SOURCE_KEYS = {key: key for key in TARGET_KEYS} | {
    "sharing_value_latest_available_day": "revenue_latest_available_day",
    "sharing_value_this_month": "revenue_this_month",
    "electricity_sale_price": "sale_price",
}


@dataclass(frozen=True)
class DashboardTarget:
    """One target's existing sensors, never the group's price or totals."""

    name: str
    entities: Mapping[str, str]
    statistics: Mapping[str, str] = field(default_factory=dict)


def validate_dashboard_name(title: str, url_path: str) -> None:
    """Keep paths compatible with HA and away from the generator itself."""
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        raise ValueError("invalid_title")
    if (
        not isinstance(url_path, str)
        or len(url_path) > 80
        or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", url_path) is None
        or url_path == PANEL_PATH
    ):
        raise ValueError("invalid_path")


def target_details_card(targets: Sequence[DashboardTarget], language: str = "cs") -> dict[str, Any]:
    """Zobrazit existující cílové senzory bez odhadování podle friendly_name.

    Vstupem jsou registry-resolved ID a jména; čísla se čtou až v HA.
    Samostatná vazba kWh, %, CZK a CZK/kWh zabraňuje záměně peněz za
    nasdílenou energii. Chybějící/neplatný stav nebo jiná jednotka je —,
    nikoli nula. Cenu ani částku nepočítáme znovu; použijeme původní
    hodnotový senzor konkrétního místa. Výstup je nativní markdown karta,
    která nic nezapisuje, nemění entity a neprovádí žádný HTTP požadavek.
    """
    points = [{"name": target.name, **dict(target.entities)} for target in targets]
    cs = language == "cs"
    fields = [
        ("shared", "Nasdíleno" if cs else "Shared", "kWh"),
        ("consumption", "Spotřeba" if cs else "Consumption", "kWh"),
        ("grid_purchase", "Ze sítě" if cs else "Grid import", "kWh"),
        ("sharing_coverage", "Pokrytí" if cs else "Coverage", "%"),
        ("revenue", "Hodnota sdílení" if cs else "Sharing value", "CZK"),
    ]
    content = "{% set points = " + json.dumps(points, ensure_ascii=False) + " %}\n"
    content += "{% set fields = " + json.dumps(fields, ensure_ascii=False) + " %}\n"
    # Název a lokalita mohou být uživatelsky změněné. Existující device_id
    # čteme pouze pro popisek, nikdy pro volbu energetického/cenového senzoru.
    content += "{% for point in points %}\n{% set source = point.get('shared_latest_available_day', '') %}\n"
    content += "{% set device = device_id(source) if source else none %}\n"
    content += "## 🏠 {{ (device_attr(device, 'name') if device else none) or point.name }}\n"
    content += "{% set location = state_attr(source, 'location') if source else none %}\n{% if location %}\n📍 **{{ location }}**\n{% endif %}\n"
    content += ("\n**Poslední data:** " if cs else "\n**Latest data:** ")
    content += "{{ state_attr(point.get('shared_latest_available_day', ''), 'data_date') or '—' }}\n"
    for suffix, title in (("latest_available_day", "Poslední dostupný den" if cs else "Latest available day"),
                          ("this_month", "Tento měsíc" if cs else "This month")):
        content += "\n### " + title + "\n{% for key, label, unit in fields %}\n"
        content += "{% set entity = point.get(key ~ '_" + suffix + "', '') %}\n"
        content += "{% set raw = states(entity) if entity else '' %}\n"
        content += "{% set value = raw | float(none) if is_number(raw) else none %}\n"
        content += "{% set actual_unit = state_attr(entity, 'unit_of_measurement') if entity else none %}\n"
        content += "- **{{ label }}:** {{ ('%.2f' | format(value)) ~ ' ' ~ unit if value is not none and actual_unit == unit else '—' }}\n{% endfor %}\n"
    content += "{% set price_entity = point.get('sale_price', '') %}\n"
    content += "{% set raw_price = states(price_entity) if price_entity else '' %}\n"
    content += "{% set price = raw_price | float(none) if is_number(raw_price) else none %}\n"
    content += ("\n**Cena odběrného místa:** " if cs else "\n**Supply-point price:** ")
    content += "{{ ('%.2f' | format(price)) ~ ' CZK/kWh' if price is not none and state_attr(price_entity, 'unit_of_measurement') == 'CZK/kWh' else '—' }}\n{% if not loop.last %}\n---\n{% endif %}\n{% endfor %}"
    return {"type": "markdown", "content": content}


def period_value_card(entities: Mapping[str, str], language: str = "cs") -> dict[str, Any] | None:
    """Orientační hodnota období: skutečné kWh × aktuální cena skupiny.

    Vstup jsou existující senzory využití přetoku se shared_kwh a pokrytím
    dostupných dnů, plus skupinová cena CZK/kWh. Prázdné období, cena nebo
    chybná jednotka zobrazí —. Výpočet není potvrzení platby, nový doklad
    ani přepočet vystaveného vyúčtování; neodhaduje historickou cenu a
    nepoužívá skupinovou cenu pro samostatné částky jednotlivých míst.
    """
    cs = language == "cs"
    periods = [("Den" if cs else "Day", "latest_available_day"),
               ("Týden" if cs else "Week", "this_week"),
               ("Měsíc" if cs else "Month", "this_month"),
               ("Rok" if cs else "Year", "this_year")]
    bindings = [[label, entities[f"surplus_utilization_{key}"]]
                for label, key in periods if entities.get(f"surplus_utilization_{key}")]
    price_entity = entities.get("sale_price")
    if not price_entity or not bindings:
        return None
    content = "{% set periods = " + json.dumps(bindings, ensure_ascii=False) + " %}\n"
    content += "{% set price_entity = " + json.dumps(price_entity) + " %}\n"
    content += "{% set raw_price = states(price_entity) %}\n"
    content += "{% set price = raw_price | float(none) if is_number(raw_price) else none %}\n"
    content += "{% for label, entity in periods %}\n"
    content += "{% set raw_shared = state_attr(entity, 'shared_kwh') %}\n"
    content += "{% set shared = raw_shared | float(none) if is_number(raw_shared) else none %}\n"
    content += "{% set days = state_attr(entity, 'available_days') | int(0) %}\n"
    content += "{% set raw_coverage = states(entity) %}\n"
    content += "\n### {{ label }} – {{ ('%.1f' | format(raw_coverage | float)) ~ ' %' if is_number(raw_coverage) and days > 0 else '—' }}\n"
    for attribute, label_cs, label_en in (
        ("shared_kwh", "Nasdíleno", "Shared"),
        ("production_surplus_kwh", "Přetok výrobny", "Production surplus"),
        ("unused_surplus_kwh", "Nevyužito", "Unused surplus"),
    ):
        content += "{% set raw_value = state_attr(entity, '" + attribute + "') %}\n"
        content += "- " + (label_cs if cs else label_en) + ": **{{ ('%.2f' | format(raw_value | float)) ~ ' kWh' if is_number(raw_value) and days > 0 else '—' }}**\n"
    content += ("- Hodnota při aktuální ceně skupiny: **" if cs else "- Value at the current group price: **")
    content += "{{ ('%.2f' | format(shared * price)) ~ ' CZK' if shared is not none and price is not none and days > 0 and state_attr(price_entity, 'unit_of_measurement') == 'CZK/kWh' else '—' }}**\n"
    content += "- Data: **"
    content += "{{ state_attr(entity, 'data_start') or '—' }} → {{ state_attr(entity, 'data_end') or '—' }}**, " + ("dnů" if cs else "days") + " **{{ days }}**\n{% endfor %}\n"
    content += ("\nOrientační hodnota při aktuální ceně skupiny; vystavená vyúčtování se nemění."
                if cs else "\nEstimated value at the current group price; issued statements remain unchanged.")
    return {"type": "markdown", "content": content}


def build_dashboard(
    *,
    title: str,
    url_path: str,
    entities: Mapping[str, str],
    statistics: Mapping[str, str],
    targets: Sequence[DashboardTarget] = (),
    buttons: Mapping[str, str] | None = None,
    language: str = "cs",
    include_details: bool = True,
    include_energy: bool = False,
) -> dict[str, Any]:
    """Return a complete dashboard, not a view to overwrite an existing one."""
    validate_dashboard_name(title, url_path)
    czech = language == "cs"

    def text(cs: str, en: str) -> str:
        return cs if czech else en

    def heading(cs: str, en: str, icon: str) -> dict:
        return {"type": "heading", "heading": text(cs, en), "icon": icon}

    def section(cards: list[dict], span: int = 2) -> dict:
        return {"type": "grid", "column_span": span, "cards": cards}

    def grid(cards: list[dict]) -> list[dict]:
        return (
            [{"type": "grid", "columns": 2, "square": False, "cards": cards}]
            if cards
            else []
        )

    def tiles(source: Mapping[str, str], specs: Sequence[tuple]) -> list[dict]:
        return [
            {
                "type": "tile",
                "entity": source[key],
                "name": text(cs, en),
                "icon": icon,
                "color": color,
            }
            for key, cs, en, icon, color in specs
            if source.get(key)
        ]

    def gauges(keys: Sequence[str]) -> list[dict]:
        return [
            {
                "type": "gauge",
                "entity": entities[key],
                "name": text("Pokrytí spotřeby", "Consumption coverage")
                if key.startswith("coverage")
                else text("Využití přetoku", "Surplus utilization"),
                "min": 0,
                "max": 100,
                "needle": True,
                "severity": {"red": 0, "yellow": 30, "green": 60},
            }
            for key in keys
            if entities.get(key)
        ]

    def graph(
        period: str,
        days: int,
        cs: str,
        en: str,
        metrics: tuple[str, ...],
        source: Mapping[str, str] | None = None,
    ) -> list[dict]:
        source = statistics if source is None else source
        series = [
            {"entity": source[f"{metric}_{period}"], "name": text(*labels[metric])}
            for metric in metrics
            if source.get(f"{metric}_{period}")
        ]
        return (
            [
                {
                    "type": "statistics-graph",
                    "title": text(cs, en),
                    "chart_type": "line",
                    "days_to_show": days,
                    "period": "hour" if period == "hourly" else "day",
                    "stat_types": ["mean"],
                    "entities": series,
                }
            ]
            if series
            else []
        )

    labels = {
        "shared": ("Nasdíleno", "Shared"),
        "consumption": ("Spotřeba", "Consumption"),
        "grid": ("Ze sítě", "Grid import"),
        "unused": ("Nevyužitý přetok", "Unused surplus"),
        "coverage": ("Pokrytí spotřeby", "Consumption coverage"),
        "revenue": ("Hodnota sdílení", "Sharing value"),
    }
    latest = (
        (
            "shared_today",
            "Nasdíleno",
            "Shared",
            "mdi:transmission-tower-export",
            "green",
        ),
        (
            "consumption_today",
            "Spotřeba příjemce",
            "Consumption",
            "mdi:home-lightning-bolt",
            "blue",
        ),
        (
            "grid_today",
            "Ze sítě",
            "Grid import",
            "mdi:transmission-tower-import",
            "orange",
        ),
        (
            "unused_today",
            "Nevyužitý přetok",
            "Unused surplus",
            "mdi:transmission-tower-off",
            "red",
        ),
        (
            "coverage_today",
            "Pokrytí spotřeby",
            "Consumption coverage",
            "mdi:home-percent-outline",
            "green",
        ),
        (
            "surplus_utilization_latest_available_day",
            "Využití přetoku",
            "Surplus utilization",
            "mdi:solar-power-variant",
            "green",
        ),
        ("revenue_today", "Hodnota sdílení", "Sharing value", "mdi:cash", "green"),
    )
    monthly = (
        (
            "shared_month",
            "Nasdíleno",
            "Shared",
            "mdi:transmission-tower-export",
            "green",
        ),
        (
            "consumption_month",
            "Spotřeba",
            "Consumption",
            "mdi:home-lightning-bolt",
            "blue",
        ),
        (
            "grid_month",
            "Ze sítě",
            "Grid import",
            "mdi:transmission-tower-import",
            "orange",
        ),
        (
            "overflow_month",
            "Přetok výrobny",
            "Production surplus",
            "mdi:solar-power",
            "amber",
        ),
        (
            "unused_month",
            "Nevyužitý přetok",
            "Unused surplus",
            "mdi:transmission-tower-off",
            "red",
        ),
        (
            "production_profit_month",
            "Hodnota sdílení",
            "Sharing value",
            "mdi:cash-multiple",
            "green",
        ),
    )
    first = heading(
        "Poslední dostupný den", "Latest available day", "mdi:calendar-clock"
    )
    if include_details:
        first["badges"] = [
            {
                "type": "button",
                "text": text("Detaily", "Details"),
                "icon": "mdi:chart-line",
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": f"/{url_path}/details",
                },
            }
        ]
    date_cards = []
    if entity := entities.get("shared_today"):
        date_cards.append(
            {
                "type": "markdown",
                "content": (
                    "{% set d = state_attr("
                    + json.dumps(entity)
                    + ", 'data_date') %}\n"
                    + text("### 📅 Data EDC k ", "### 📅 EDC data for ")
                    + "{{ d if d else '—' }}\n\n"
                    + text(
                        "EDC dodává výsledky se zpožděním, obvykle přibližně jeden den.",
                        "EDC results are delayed, typically by about one day.",
                    )
                ),
            }
        )
    sections = [
        section(
            [
                first,
                *date_cards,
                *grid(tiles(entities, latest)),
                *grid(
                    gauges(
                        ("coverage_today", "surplus_utilization_latest_available_day")
                    )
                ),
            ]
        ),
        section(
            [
                heading("Tento měsíc", "This month", "mdi:calendar-month"),
                *grid(tiles(entities, monthly)),
                *grid(gauges(("coverage_month", "surplus_utilization_this_month"))),
            ]
        ),
    ]
    year_cards = [heading("Tento rok", "This year", "mdi:calendar-range")]
    if entity := entities.get("surplus_utilization_this_year"):
        year_cards.append(
            {
                "type": "markdown",
                "content": (
                    "{% set e = " + json.dumps(entity) + " %}\n"
                    "{% set shared = state_attr(e, 'shared_kwh') %}\n"
                    "{% set start = state_attr(e, 'data_start') %}\n"
                    "{% set end = state_attr(e, 'data_end') %}\n"
                    + text("## ⚡ Nasdíleno tento rok\n", "## ⚡ Shared this year\n")
                    + "# {{ shared | round(2) if shared is number else '—' }} kWh\n\n"
                    + text("**Rozsah dat:** ", "**Data range:** ")
                    + "{{ start or '—' }} → {{ end or '—' }}\n\n"
                    + "{% if start and start[5:10] != '01-01' %}"
                    + text(
                        "⚠️ Dostupná historie zatím nepokrývá celý rok od 1. ledna.",
                        "⚠️ Available history does not yet cover the year from January 1.",
                    )
                    + "{% endif %}"
                ),
            }
        )
    year_cards += grid(gauges(("surplus_utilization_this_year",)))
    sections.append(section(year_cards))
    utilization = [
        (f"surplus_utilization_{period}", cs, en, icon, "green")
        for period, cs, en, icon in (
            (
                "latest_available_day",
                "Poslední den",
                "Latest day",
                "mdi:calendar-today",
            ),
            ("this_week", "Tento týden", "This week", "mdi:calendar-week"),
            ("this_month", "Tento měsíc", "This month", "mdi:calendar-month"),
            ("this_year", "Tento rok", "This year", "mdi:calendar-range"),
            ("total", "Celkem", "Total", "mdi:all-inclusive"),
        )
    ]
    sections.append(
        section(
            [
                heading(
                    "Využití přetoku", "Surplus utilization", "mdi:solar-power-variant"
                ),
                {
                    "type": "markdown",
                    "content": text(
                        "**Využití přetoku** = nasdíleno / přetok výrobny × 100.\n\n"
                        "**Pokrytí spotřeby** = nasdíleno / spotřeba příjemce × 100. Nejde o stejnou metriku.",
                        "**Surplus utilization** = shared / production surplus × 100.\n\n"
                        "**Consumption coverage** = shared / recipient consumption × 100. These are different metrics.",
                    ),
                },
                *grid(tiles(entities, utilization)),
            ]
        )
    )
    for period, days, cs, en, icon in (
        ("hourly", 3, "Grafy – hodiny", "Hourly history", "mdi:chart-line"),
        ("daily", 31, "Grafy – měsíc", "Monthly history", "mdi:chart-areaspline"),
        ("daily", 366, "Grafy – rok", "Yearly history", "mdi:chart-timeline-variant"),
    ):
        graphs = graph(
            period, days, cs, en, ("shared", "consumption", "grid", "unused")
        )
        if graphs:
            sections.append(
                section([heading(cs, en, icon), *graphs], 4 if days == 366 else 2)
            )
    sections.append(
        section(
            [
                heading(
                    "Finance – celá skupina", "Group finances", "mdi:cash-multiple"
                ),
                *grid(
                    tiles(
                        entities,
                        (
                            (
                                "sale_price",
                                "Cena skupiny",
                                "Group price",
                                "mdi:cash",
                                "green",
                            ),
                            (
                                "revenue_today",
                                "Poslední den",
                                "Latest day",
                                "mdi:cash-plus",
                                "green",
                            ),
                            (
                                "production_profit_month",
                                "Tento měsíc",
                                "This month",
                                "mdi:cash-multiple",
                                "green",
                            ),
                        ),
                    )
                ),
            ]
        )
    )
    if include_energy:
        collection_key = "energy_edc_" + url_path.replace("-", "_")
        sections.append(
            section(
                [
                    heading(
                        "Nákup a prodej – Energy",
                        "Purchase and sale – Energy",
                        "mdi:cash-multiple",
                    ),
                    {"type": "energy-date-selection", "collection_key": collection_key},
                    {
                        "type": "energy-sources-table",
                        "collection_key": collection_key,
                        "types": ["grid"],
                        "show_only_totals": False,
                    },
                    {
                        "type": "markdown",
                        "content": text(
                            "Tabulka používá **stávající celkovou konfiguraci Energy**, nikoli jen tuto skupinu EDC. "
                            "Generátor ji nemění. Vyberte placená místa v EDC a odpovídající statistiku v Energy. "
                            "EDC příjem je přiřazen skutečnému dni sdílení, nikoli dni stažení.",
                            "This table uses your **existing overall Energy configuration**, not just this EDC group. "
                            "The generator does not change it. Select paid targets in EDC and their statistic in Energy. "
                            "EDC income belongs to the actual sharing day, not the download date.",
                        ),
                    },
                ]
            )
        )
    diagnostic_keys = (
        "history_earliest_date",
        "history_backfill_status",
        "last_update_attempt",
    )
    diagnostic = [entities[key] for key in diagnostic_keys if entities.get(key)]
    if diagnostic:
        sections.append(
            section(
                [
                    heading(
                        "Historie a aktualizace",
                        "History and updates",
                        "mdi:database-clock-outline",
                    ),
                    {
                        "type": "entities",
                        "show_header_toggle": False,
                        "entities": diagnostic,
                    },
                ]
            )
        )
    for target in targets:
        specs = [
            (key, cs, en, icon, color)
            for key, cs, en, icon, color in (
                (
                    "shared_latest_available_day",
                    "Nasdíleno – poslední den",
                    "Shared – latest day",
                    "mdi:transmission-tower-export",
                    "green",
                ),
                (
                    "consumption_latest_available_day",
                    "Spotřeba – poslední den",
                    "Consumption – latest day",
                    "mdi:home-lightning-bolt",
                    "blue",
                ),
                (
                    "grid_purchase_latest_available_day",
                    "Ze sítě – poslední den",
                    "Grid import – latest day",
                    "mdi:transmission-tower-import",
                    "orange",
                ),
                (
                    "revenue_latest_available_day",
                    "Hodnota sdílení – poslední den",
                    "Sharing value – latest day",
                    "mdi:cash",
                    "green",
                ),
                (
                    "shared_this_month",
                    "Nasdíleno – měsíc",
                    "Shared – month",
                    "mdi:transmission-tower-export",
                    "green",
                ),
                (
                    "consumption_this_month",
                    "Spotřeba – měsíc",
                    "Consumption – month",
                    "mdi:home-lightning-bolt",
                    "blue",
                ),
                (
                    "grid_purchase_this_month",
                    "Ze sítě – měsíc",
                    "Grid import – month",
                    "mdi:transmission-tower-import",
                    "orange",
                ),
                (
                    "sharing_coverage_this_month",
                    "Pokrytí spotřeby",
                    "Consumption coverage",
                    "mdi:home-percent-outline",
                    "green",
                ),
                (
                    "revenue_this_month",
                    "Hodnota sdílení – měsíc",
                    "Sharing value – month",
                    "mdi:cash-multiple",
                    "green",
                ),
                (
                    "sale_price",
                    "Cena odběrného místa",
                    "Supply-point price",
                    "mdi:cash",
                    "green",
                ),
            )
        ]
        cards = tiles(target.entities, specs)
        if cards:
            sections.append(
                section(
                    [
                        {
                            "type": "heading",
                            "heading": target.name,
                            "icon": "mdi:home-import-outline",
                        },
                        *grid(cards),
                    ]
                )
            )
    tools = [
        {
            "type": "button",
            "name": text("EAN a reporty", "EANs and reports"),
            "icon": "mdi:tune-variant",
            "tap_action": {
                "action": "navigate",
                "navigation_path": "/config/integrations/integration/edc_sharing",
            },
        },
        {
            "type": "button",
            "name": text("Portál EDC", "EDC portal"),
            "icon": "mdi:open-in-new",
            "tap_action": {
                "action": "url",
                "url_path": "https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat",
            },
        },
    ]
    for entity in (buttons or {}).values():
        tools.append(
            {"type": "button", "entity": entity, "tap_action": {"action": "more-info"}}
        )
    sections.append(
        section([heading("EDC nástroje", "EDC tools", "mdi:cog-outline"), *grid(tools)])
    )
    overview = {
        "title": title.strip(),
        "path": "overview",
        "icon": "mdi:transmission-tower-export",
        "type": "sections",
        "max_columns": 4,
        "dense_section_placement": True,
        "badges": [],
        "sections": sections,
    }
    views = [overview]
    money_summary = period_value_card(entities, language)
    if money_summary:
        overview["sections"].append(section([heading("Hodnota sdílení podle období", "Sharing value by period", "mdi:cash"), money_summary]))
    if include_details:
        detail_cards = [
            {
                "type": "heading",
                "heading": text("EDC – data a stav", "EDC data and status"),
                "icon": "mdi:database-search-outline",
            }
        ]
        if entities:
            detail_cards.append(
                {
                    "type": "entities",
                    "show_header_toggle": False,
                    "entities": list(entities.values()),
                }
            )
        if money_summary:
            detail_cards.extend([heading("Hodnota sdílení podle období", "Sharing value by period", "mdi:cash"), money_summary])
        if targets:
            detail_cards.extend([heading("Cílová odběrná místa", "Target supply points", "mdi:home-group"), target_details_card(targets, language)])
        detail_cards.append(
            {
                "type": "markdown",
                "content": text(
                    "Historické grafy používají importované statistiky EDC s původními daty. "
                    "Nezaměňujte čas aktualizace senzoru za den fyzického sdílení. "
                    "Nedostupné údaje nejsou nulová spotřeba. Rozsah ročních dat zkontrolujte v atributech senzoru.",
                    "History charts use imported EDC statistics with their original dates. "
                    "A sensor update time is not the physical sharing day. Missing data is not zero consumption. "
                    "Check the annual sensor attributes for the available data range.",
                ),
            }
        )
        views.append(
            {
                "title": text("Detaily", "Details"),
                "path": "details",
                "subview": True,
                "type": "sections",
                "max_columns": 4,
                "sections": [
                    section(detail_cards),
                    section(
                        [
                            *graph(
                                "daily",
                                31,
                                "Pokrytí spotřeby – historie",
                                "Consumption coverage history",
                                ("coverage",),
                            ),
                            *graph(
                                "daily",
                                31,
                                "Hodnota sdílení – historie",
                                "Sharing value history",
                                ("revenue",),
                            ),
                        ]
                    ),
                ],
            }
        )
    if include_details:
        # Výchozí detaily mají poslední tři dny, tedy i zpožděná data EDC.
        # Nativní volba dne je samostatná podstránka: její dnešní výchozí
        # období nesmí potlačit tento základní přehled.
        groups = [(text("Celá skupina", "Whole group"), statistics)] + [
            (target.name, target.statistics) for target in targets
        ]
        selected_sections = []
        hourly_intro_added = False
        collection = "energy_edc_" + url_path.replace("-", "_") + "_hours"
        for name, source in groups:
            cards = graph(
                "hourly",
                3,
                f"Sdílení, spotřeba a síť – {name}",
                f"Sharing, consumption and grid – {name}",
                ("shared", "consumption", "grid"),
                source,
            )
            cards += graph(
                "hourly",
                3,
                f"Pokrytí sdílením – {name}",
                f"Sharing coverage – {name}",
                ("coverage",),
                source,
            )
            if not cards:
                continue
            if not hourly_intro_added:
                # Výběr aktuálního dne nativně přebíjí days_to_show.
                # Výchozí detaily proto vysvětlují třídenní rozsah bez
                # vazby na Energy kolekci; výběr zůstává v hourly-date.
                views[1]["sections"].append(section([
                    heading("Hodinové průběhy – poslední 3 dny", "Hourly history – last 3 days", "mdi:chart-line"),
                    {"type": "markdown", "content": text(
                        "Výchozí grafy zobrazují poslední tři dny, aby zahrnuly zpožděná data EDC. "
                        "Pro konkrétní den použijte samostatnou volbu období. "
                        "Jeden bod je energie jedné hodiny v kWh; pokrytí je procento. Chybějící hodina není nula.",
                        "Default charts show the last three days to include delayed EDC data. "
                        "Use the separate period selector for a specific day. "
                        "Each point is one hour of energy in kWh; coverage is percent. Missing hours are not zero.",
                    )},
                ]))
                hourly_intro_added = True
            for card in cards:
                card["min_y_axis"] = 0
                if len(card["entities"]) == 1 and card["entities"][0][
                    "entity"
                ].endswith("_coverage_hourly"):
                    card["max_y_axis"] = 100
            views[1]["sections"].append(section(cards))
            selected = json.loads(json.dumps(cards))
            for card in selected:
                card.update(energy_date_selection=True, collection_key=collection)
            selected_sections.append(section(selected))
        if selected_sections:
            views[1]["sections"].append(
                section(
                    [
                        {
                            "type": "button",
                            "name": text(
                                "Vybrat den hodinových grafů", "Select hourly chart day"
                            ),
                            "icon": "mdi:calendar-search",
                            "tap_action": {
                                "action": "navigate",
                                "navigation_path": f"/{url_path}/hourly-date",
                            },
                        }
                    ]
                )
            )
            views.append(
                {
                    "title": text("Hodiny – vybrané období", "Hours – selected period"),
                    "path": "hourly-date",
                    "subview": True,
                    "back_path": f"/{url_path}/details",
                    "type": "sections",
                    "max_columns": 4,
                    "sections": [
                        section(
                            [
                                {
                                    "type": "energy-date-selection",
                                    "collection_key": collection,
                                },
                                {
                                    "type": "markdown",
                                    "content": text(
                                        "Vyberte minulý den: EDC zveřejňuje data se zpožděním. Každý bod je energie za hodinu (kWh); pokrytí je procento. Prázdné období není nula. Výchozí detaily zobrazují poslední tři dny.",
                                        "Select a past day: EDC publishes delayed data. Points are hourly energy (kWh); coverage is percent. An empty period is not zero. Default details display the last three days.",
                                    ),
                                },
                            ]
                        ),
                        *selected_sections,
                    ],
                }
            )
    return {"title": title.strip(), "views": views}
