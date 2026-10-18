"""Pure calculation helpers for EDC profile data."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ZERO = Decimal(0)
MAX_PROFILE_DAYS = 31


class IncompleteProfileLayoutError(ValueError):
    """EDC profile data does not contain both sides of electricity sharing."""


class ProfileSchemaError(ValueError):
    """Neplatné vzdálené doménové schéma, nikoli chyba Python typu volajícího."""


@dataclass(frozen=True, slots=True)
class EanInfo:
    """One EAN participating in an EDC sharing group."""

    ean: str
    role: Literal["sharing", "target"]


@dataclass(frozen=True, slots=True)
class DailySharing:
    """Calculated values for one day."""

    day: date
    consumption: Decimal
    grid_purchase: Decimal
    shared: Decimal
    producer_overflow: Decimal
    used_overflow: Decimal
    unused_overflow: Decimal
    coverage: Decimal
    consistency_difference: Decimal
    complete: bool = True


@dataclass(frozen=True, slots=True)
class TargetDailySharing:
    """Calculated consumption values for one target EAN and calendar day."""

    ean: str
    day: date
    consumption: Decimal
    grid_purchase: Decimal
    shared: Decimal
    coverage: Decimal
    complete: bool = True


@dataclass(frozen=True, slots=True)
class TargetHourlySharing:
    """Calculated hourly values for one target EAN."""

    ean: str
    start: datetime
    consumption: Decimal
    grid_purchase: Decimal
    shared: Decimal
    coverage: Decimal
    complete: bool = True


@dataclass(frozen=True, slots=True)
class HourlySharing:
    """Calculated values for one clock hour."""

    start: datetime
    consumption: Decimal
    grid_purchase: Decimal
    shared: Decimal
    producer_overflow: Decimal
    used_overflow: Decimal
    unused_overflow: Decimal
    coverage: Decimal
    consistency_difference: Decimal
    complete: bool = True


@dataclass(frozen=True, slots=True)
class SurplusUtilization:
    """Surplus utilization and the energy values used to calculate it."""

    value: Decimal
    shared: Decimal
    production_surplus: Decimal
    unused_surplus: Decimal
    data_start: date | None
    data_end: date | None
    available_days: int


@dataclass(frozen=True, slots=True)
class SharingStatistics:
    """Statistics exposed by the integration."""

    days: tuple[DailySharing, ...]
    today: DailySharing
    latest: DailySharing
    latest_day: date | None
    month_consumption: Decimal
    month_grid_purchase: Decimal
    month_shared: Decimal
    month_overflow: Decimal
    month_unused: Decimal
    month_coverage: Decimal
    month_revenue: Decimal
    today_revenue: Decimal
    sale_price: Decimal
    surplus_utilization_latest_available_day: SurplusUtilization
    surplus_utilization_this_week: SurplusUtilization
    surplus_utilization_this_month: SurplusUtilization
    surplus_utilization_this_year: SurplusUtilization
    surplus_utilization_total: SurplusUtilization
    target_statistics: tuple[TargetSharingStatistics, ...]


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    """Aggregate sharing values for an arbitrary report period."""

    consumption: Decimal
    grid_purchase: Decimal
    shared: Decimal
    producer_overflow: Decimal
    unused_overflow: Decimal
    coverage: Decimal
    revenue: Decimal


@dataclass(frozen=True, slots=True)
class TargetPeriodSummary:
    """Aggregate values for one target EAN over an available period."""

    consumption: Decimal
    grid_purchase: Decimal
    shared: Decimal
    coverage: Decimal
    revenue: Decimal
    data_start: date | None
    data_end: date | None
    available_days: int


@dataclass(frozen=True, slots=True)
class TargetSharingStatistics:
    """Current and historical summaries for one target EAN."""

    ean: str
    latest_day: date | None
    latest: TargetPeriodSummary
    week: TargetPeriodSummary
    month: TargetPeriodSummary
    year: TargetPeriodSummary
    total: TargetPeriodSummary
    sale_price: Decimal


def _decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("EDC vrátilo neplatnou číselnou hodnotu.") from err
    return parsed if parsed.is_finite() else ZERO


def calculate_surplus_utilization(
    days: tuple[DailySharing, ...],
) -> SurplusUtilization:
    """Calculate how much production surplus was used for sharing."""
    ordered = tuple(sorted(days, key=lambda row: row.day))
    shared = sum((row.shared for row in ordered), ZERO)
    production_surplus = sum((row.producer_overflow for row in ordered), ZERO)
    unused_surplus = sum((row.unused_overflow for row in ordered), ZERO)
    value = (
        shared / production_surplus * Decimal(100)
        if shared > ZERO and production_surplus > ZERO
        else ZERO
    )
    return SurplusUtilization(
        value=value,
        shared=shared,
        production_surplus=production_surplus,
        unused_surplus=unused_surplus,
        data_start=ordered[0].day if ordered else None,
        data_end=ordered[-1].day if ordered else None,
        available_days=len(ordered),
    )


def two_calendar_month_start(today: date) -> date:
    """Return the first day of the previous calendar month."""
    current_month = today.replace(day=1)
    return (current_month - timedelta(days=1)).replace(day=1)


def profile_date_ranges(
    date_from: date, date_to: date
) -> tuple[tuple[date, date], ...]:
    """Rozdělit [od, do) na nejvýše 31 kalendářních dnů bez mezer/překryvu.

    Výstupní koncová mez stále není součástí bloku. Až API klient ji sníží
    o den pro včetně používané portálem; výpočty a uložená historie se nemění.
    Prázdný či obrácený vstup nemá žádný požadavek.
    """
    if date_to <= date_from:
        return ()
    ranges: list[tuple[date, date]] = []
    chunk_from = date_from
    while chunk_from < date_to:
        chunk_to = min(chunk_from + timedelta(days=MAX_PROFILE_DAYS), date_to)
        ranges.append((chunk_from, chunk_to))
        chunk_from = chunk_to
    return tuple(ranges)


def profile_date_ranges_backwards(
    date_from: date, date_to: date
) -> tuple[tuple[date, date], ...]:
    """Rozdělit [od, do) od nejnovějších dnů se stejnou sémantikou hranic.

    Kurzor backfillu je koncová mez bez tohoto dne. Sousední bloky na sebe
    navazují a limit 31 počítá skutečně zahrnuté kalendářní dny, nikoli hodiny.
    """
    if date_to <= date_from:
        return ()
    ranges: list[tuple[date, date]] = []
    chunk_to = date_to
    while chunk_to > date_from:
        chunk_from = max(date_from, chunk_to - timedelta(days=MAX_PROFILE_DAYS))
        ranges.append((chunk_from, chunk_to))
        chunk_to = chunk_from
    return tuple(ranges)


def one_calendar_year_ago(today: date) -> date:
    """Return the same calendar date one year earlier."""
    try:
        return today.replace(year=today.year - 1)
    except ValueError:
        return today.replace(year=today.year - 1, day=28)


def report_date_range(
    period: str, today: date
) -> tuple[date, date]:
    """Return the half-open range requested by an email report."""
    if period == "weekly":
        end = today - timedelta(days=today.weekday())
        return end - timedelta(days=7), end
    if period == "monthly":
        end = today.replace(day=1)
        return (end - timedelta(days=1)).replace(day=1), end
    if period == "yearly":
        return date(today.year, 1, 1), today + timedelta(days=1)
    raise ValueError(f"Unsupported report period: {period}")


def validate_profile_response(response: Any) -> None:
    """Ověřit významové schéma před změnou cache; nové volitelné klíče tolerovat.

    Nula je platná kWh. Null a nekonečné/NaN číselné značky znamenají
    nepoužitelné měření, nikoli důvod zahodit celý profil. Parser vynechá
    pouze dotčený interval a úplnost ověří bez něj; žádnou hodnotu nenuluje.
    Chybějící pole v, krátký vektor, bool a prázdný text jsou nadále chyby.
    Úmyslně nepoužívat
    hodnoty EANů ani chybného JSONu v textu výjimky. Platné prázdno má obě
    seznamová pole; neznámé role/směry a krátké vektory znamenají změnu dat.
    Jednostranný, ale jinak správný profil může předcházet vzniku sdílení.
    """
    if not isinstance(response, dict) or not isinstance(response.get("content"), list):
        raise ProfileSchemaError("EDC změnilo strukturu profilových seznamů.")
    # Kompatibilní starší prázdná odpověď content=[] bez valueColumns.
    # Chybějící content nebo null sem úmyslně nepatří.
    if response["content"] == [] and "valueColumns" not in response:
        return
    if not isinstance(response.get("valueColumns"), list):
        raise ProfileSchemaError("EDC změnilo strukturu profilových seznamů.")
    columns, content = response["valueColumns"], response["content"]
    seen = set()
    for column in columns:
        if not isinstance(column, dict):
            raise ProfileSchemaError("EDC vrátilo neplatný popis sloupce.")
        ean, role, direction = column.get("ean"), column.get("type"), column.get("dir")
        # Dosavadní kontrakt používá kWh bez explicitního unit. Novou jednotku
        # neodhadovat ani automaticky převádět bez prověřeného významu hodnot.
        if "unit" in column and column["unit"] != "kWh":
            raise ProfileSchemaError("EDC změnilo jednotku profilových hodnot.")
        if (not isinstance(ean, str) or not ean.strip()
                or role not in ("D", "O") or direction not in ("IN", "OUT")):
            raise ValueError("EDC změnilo identifikaci nebo role sloupců.")
        identity = (ean, role, direction)
        if identity in seen:
            raise ValueError("EDC vrátilo duplicitní sloupec.")
        seen.add(identity)
    roles = {role for _ean, role, _direction in seen}
    for ean, role, _direction in seen:
        if {direction for item_ean, item_role, direction in seen
                if item_ean == ean and item_role == role} != {"IN", "OUT"} and roles == {"D", "O"}:
            raise ValueError("EDC vrátilo neúplné směry měření.")
    if content and not columns:
        raise ValueError("EDC nevrátilo popis profilových dat.")
    for row in content:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str):
            raise ProfileSchemaError("EDC změnilo strukturu časových řádků.")
        try:
            if len(row["date"]) == 10:
                date.fromisoformat(row["date"])
            else:
                datetime.fromisoformat(row["date"])
        except ValueError:
            raise ValueError("EDC vrátilo neplatný den profilu.") from None
        values = row.get("values")
        if not isinstance(values, list) or len(values) != len(columns):
            raise ValueError("EDC vrátilo neúplný vektor hodnot.")
        for value in values:
            if isinstance(value, dict) and "v" not in value:
                raise ProfileSchemaError("EDC změnilo strukturu časových řádků.")
            value = value.get("v") if isinstance(value, dict) else value
            if _missing_measurement(value):
                continue
            if isinstance(value, bool) or value == "":
                raise ValueError("EDC vrátilo chybějící měřenou hodnotu.")
            parsed = _decimal(value)
            if not math.isfinite(float(parsed)):
                raise ValueError("EDC vrátilo nekonečnou měřenou hodnotu.")


def _profile_clock_minutes(value: Any, *, end: bool = False) -> int:
    """Převést místní čas EDC na minuty od půlnoci, bez změny rozlišení.

    Minutový zápis HH:mm používá tabulka referenčního WebDownloaderu.
    HH:mm:ss a jeho nulová desetinná část představují stejnou hranici;
    nenulové sekundy nikdy nezaokrouhlujeme. Vstup musí být časový řetězec,
    nikoli datum, UTC okamžik či libovolné číslo. Výstup 0–1439 slouží
    rozlišení a agregaci; 1440 je dovoleno jen pro konec 24:00. Chybný
    zápis vyvolá ValueError bez zveřejnění obsahu odpovědi. DST řeší až
    převod místního dne a času na UTC, nikoli tato syntaktická kontrola.
    """
    match = (
        re.fullmatch(r"([0-9]{2}):([0-9]{2})(?::00(?:\.0{1,9})?)?", value)
        if isinstance(value, str) else None
    )
    if match is None:
        raise ValueError("EDC vrátilo neplatnou časovou hranici profilu.")
    hour, minute = map(int, match.groups())
    if not (0 <= minute < 60 and (0 <= hour < 24 or (end and hour == 24 and minute == 0))):
        raise ValueError("EDC vrátilo neplatnou časovou hranici profilu.")
    return hour * 60 + minute


def profile_resolution(response: dict[str, Any]) -> str:
    """Rozpoznat délku intervalů bez domýšlení denního součtu jako hodiny.

    Bez času jde o denní řádky. End 24:00 je konec dne; zápisy s nulovými
    sekundami mají stejný význam. Pro
    intervaly přijímat 15/60 minut. Starší odpověď bez end lze rozpoznat jako
    čtvrthodinovou jen podle skutečných nenulových minut. Samé celé hodiny
    bez konce jsou nejednoznačné a do hodinových statistik se nezapisují.
    """
    content = response["content"]
    if not content:
        return "empty"
    durations: set[int] = set()
    missing_end = False
    starts: list[int] = []
    for row in content:
        if not row.get("start"):
            durations.add(1440)
            continue
        try:
            start = _profile_clock_minutes(row["start"])
            starts.append(start)
            if not row.get("end"):
                missing_end = True
                continue
            end = _profile_clock_minutes(row["end"], end=True)
            duration = (end - start) % 1440 or 1440
            if duration not in (15, 60, 1440) or (start == end and start != 0):
                # Přechod DST může na hodinách přeskočit/vrátit 60 minut.
                # Přijmout jen jednoznačně doložitelnou UTC délku, ne odhad.
                local_tz = ZoneInfo("Europe/Prague")
                day = date.fromisoformat(row["date"][:10])
                local_start = datetime.combine(day, datetime.min.time()) + timedelta(minutes=start)
                local_end = datetime.combine(day, datetime.min.time()) + timedelta(minutes=end)
                possible = set()
                for start_fold in (0, 1):
                    for end_fold in (0, 1):
                        left = local_start.replace(tzinfo=local_tz, fold=start_fold)
                        right = local_end.replace(tzinfo=local_tz, fold=end_fold)
                        if (left.astimezone(UTC).astimezone(local_tz).replace(tzinfo=None) == local_start
                                and right.astimezone(UTC).astimezone(local_tz).replace(tzinfo=None) == local_end):
                            minutes = (right.astimezone(UTC) - left.astimezone(UTC)).total_seconds() / 60
                            if minutes in (15, 60):
                                possible.add(int(minutes))
                if len(possible) != 1:
                    return "unknown"
                duration = possible.pop()
            durations.add(duration)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            return "unknown"
    if missing_end:
        if any(start % 60 for start in starts) and all(start % 15 == 0 for start in starts):
            durations.add(15)
        else:
            return "unknown"
    return {frozenset({15}): "quarter_hour", frozenset({60}): "hour",
            frozenset({1440}): "daily"}.get(frozenset(durations), "unknown")


def _hour_completeness(response: dict[str, Any]) -> dict[tuple[date, int], bool]:
    """Označit hodiny s celými sloty; chybějící čtvrthodina není nulová kWh.

    Opakování DST řeší parser pomocí UTC; mapa ověřuje přítomnost minut.
    Denní a nerozpoznané rozlišení nikdy neposkytuje úplnou hodinu.
    """
    resolution = profile_resolution(response)
    slots: dict[tuple[date, int], set[int]] = {}
    if resolution not in ("quarter_hour", "hour"):
        return slots
    for row in response["content"]:
        hour, minute = divmod(_profile_clock_minutes(row["start"]), 60)
        key = (date.fromisoformat(row["date"][:10]), hour)
        slots.setdefault(key, set()).add(minute)
    expected = {0, 15, 30, 45} if resolution == "quarter_hour" else {0}
    return {key: minutes == expected for key, minutes in slots.items()}


def _day_completeness(response: dict[str, Any], day: date,
                      hours: tuple[HourlySharing, ...] = ()) -> bool:
    """Ověřit všechny sloty místního dne pomocí databáze pásma Europe/Prague.

    Nezakódovat pravidla DST: rozdíl UTC půlnocí dává 23/24/25 hodin.
    Chybějící tzdata je neověřená úplnost, nikoli domnělých 24 hodin.
    """
    resolution = profile_resolution(response)
    rows = [row for row in response["content"] if row["date"][:10] == day.isoformat()]
    if resolution == "daily":
        return len(rows) == 1
    try:
        local_tz = ZoneInfo("Europe/Prague")
    except ZoneInfoNotFoundError:
        return False
    start = datetime.combine(day, datetime.min.time(), tzinfo=local_tz).astimezone(UTC)
    stop = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=local_tz).astimezone(UTC)
    expected = (stop - start).total_seconds() / 3600
    expected_hours = {start + timedelta(hours=index) for index in range(int(expected))}
    actual_hours = {row.start for row in hours if start <= row.start < stop and row.complete}
    return resolution in ("quarter_hour", "hour") and actual_hours == expected_hours


def _profile_complete_hours(response: dict[str, Any]) -> tuple[HourlySharing, ...]:
    """Jednou na celý blok ověřit UTC hodiny, včetně oddělených DST foldů."""
    if profile_resolution(response) not in ("quarter_hour", "hour"):
        return ()
    try:
        local_tz = ZoneInfo("Europe/Prague")
    except ZoneInfoNotFoundError:
        return ()
    return parse_hourly_profile(response, local_tz=local_tz)


def _profile_layout(
    response: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, int]],
    dict[str, dict[str, int]],
]:
    """Return content and the producer/consumer column mappings."""
    validate_profile_response(response)
    columns = response.get("valueColumns", [])
    # Neúplný interval vynechat jako celek: nulová náhrada by mohla vytvořit
    # falešné sdílení nebo vyúčtovat neexistující spotřebu. Zbytek původního
    # profilu zachovat; hodinová/denní úplnost kontroluje chybějící sloty.
    content = [row for row in response["content"] if not _row_missing_measurement(row)]
    if not content:
        return columns, content, {}, {}
    if not columns:
        raise ValueError("EDC nevrátilo popis profilových dat.")

    producers: dict[str, dict[str, int]] = {}
    consumers: dict[str, dict[str, int]] = {}
    for index, column in enumerate(columns):
        ean = str(column.get("ean", ""))
        direction = str(column.get("dir", "")).upper()
        role = str(column.get("type", "")).upper()
        target = producers if role == "D" else consumers if role == "O" else None
        if target is not None and direction in ("IN", "OUT"):
            target.setdefault(ean, {})[direction] = index
    if not producers or not consumers:
        raise IncompleteProfileLayoutError(
            "V odpovědi EDC nebyl rozpoznán výrobní a odběrný EAN."
        )
    return columns, content, producers, consumers


def _missing_measurement(value: Any) -> bool:
    """Rozlišit null/NaN/Infinity od konečné hodnoty a porušeného kontraktu.

    Vstup je jedna rozbalená hodnota v kWh. Nekonečné číselné značky znala
    již v0.2.4, která je nulovala; zde se jen označí nepoužitelný interval.
    Náhodný text, bool, kontejner a konečné číslo přetékající float nejsou
    mezery: nadále je musí odmítnout validátor. Funkce nemění surový profil.
    """
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return False
    try:
        return not Decimal(str(value)).is_finite()
    except InvalidOperation:
        return False


def _row_missing_measurement(row: dict[str, Any]) -> bool:
    """Vynechat celý dotčený interval, nikdy nevymýšlet nulu za jeden EAN."""
    return any(_missing_measurement(value.get("v") if isinstance(value, dict) else value)
               for value in row["values"])


def missing_measurement_counts(response: dict[str, Any]) -> tuple[int, int]:
    """Počty dnů/intervalů s null/NaN/Infinity, bez EANů či hodnot.

    Volat až po validaci schématu. Žádnou mezeru nevyplňuje a neodvozuje
    platnost EANu; neznámá časová struktura se nadále odmítá samostatně.
    """
    rows = [row for row in response["content"] if _row_missing_measurement(row)]
    return len({row["date"][:10] for row in rows}), len(rows)


def history_profile_gaps(
    response: dict[str, Any], date_from: date, date_to: date,
    days: tuple[DailySharing, ...],
) -> dict[date, str]:
    """Klasifikovat neověřené kalendářní dny historického bloku [od, do).

    Vstup již prošel validátorem a denním parserem; úplnost tedy respektuje
    kWh, null i 23/25hodinové dny Europe/Prague. Výstup obsahuje jen datum
    a pevný důvod, nikdy měření ani identity. Kontrolujeme každý požadovaný
    den: zcela chybějící/null den parser nemusí vrátit. Prázdná odpověď ani
    nejstarší uložený den nedokazují platnost skupiny; žádnou mezeru nenulovat.
    """
    complete = {row.day for row in days if row.complete}
    present = {date.fromisoformat(row["date"][:10]) for row in response["content"]}
    missing = {
        date.fromisoformat(row["date"][:10])
        for row in response["content"] if _row_missing_measurement(row)
    }
    result = {}
    day = date_from
    while day < date_to:
        if day in missing:
            result[day] = "missing_measurements"
        elif day not in present:
            result[day] = "missing_day"
        elif day not in complete:
            result[day] = "incomplete_day"
        day += timedelta(days=1)
    return result


def extract_eans(response: dict[str, Any]) -> tuple[EanInfo, ...]:
    """Return every distinct sharing and target EAN in an EDC profile."""
    found: set[EanInfo] = set()
    for column in response.get("valueColumns") or []:
        ean = str(column.get("ean") or "").strip()
        role = str(column.get("type") or "").upper()
        if not ean:
            continue
        if role == "D":
            found.add(EanInfo(ean, "sharing"))
        elif role == "O":
            found.add(EanInfo(ean, "target"))
    return tuple(sorted(found, key=lambda item: (item.role, item.ean)))


def _add_values(
    target: list[Decimal], values: list[Any], column_count: int
) -> None:
    """Add one EDC interval to an aggregate value vector."""
    for index, raw in enumerate(values[:column_count]):
        target[index] += _decimal(raw.get("v") if isinstance(raw, dict) else raw)


def _sharing_values(
    values: list[Decimal],
    producers: dict[str, dict[str, int]],
    consumers: dict[str, dict[str, int]],
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Calculate sharing values from aggregated EDC value columns."""
    def value(index: int | None) -> Decimal:
        if index is None or index >= len(values):
            return ZERO
        return values[index]

    producer_in = sum((value(pair.get("IN")) for pair in producers.values()), ZERO)
    producer_out = sum((value(pair.get("OUT")) for pair in producers.values()), ZERO)
    consumer_in = sum((abs(value(pair.get("IN"))) for pair in consumers.values()), ZERO)
    consumer_out = sum((abs(value(pair.get("OUT"))) for pair in consumers.values()), ZERO)
    shared_consumer = consumer_in - consumer_out
    shared_producer = producer_in - producer_out
    coverage = shared_consumer / consumer_in * Decimal(100) if consumer_in else ZERO
    return (
        consumer_in,
        consumer_out,
        shared_consumer,
        producer_in,
        shared_producer,
        producer_out,
        coverage,
        abs(shared_consumer - shared_producer),
    )


def _target_values(
    values: list[Decimal], pair: dict[str, int]
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Calculate consumption and sharing values for one target EAN."""

    def value(index: int | None) -> Decimal:
        if index is None or index >= len(values):
            return ZERO
        return values[index]

    consumption = abs(value(pair.get("IN")))
    grid_purchase = abs(value(pair.get("OUT")))
    shared = consumption - grid_purchase
    coverage = shared / consumption * Decimal(100) if consumption else ZERO
    return consumption, grid_purchase, shared, coverage


def _daily_value_totals(
    columns: list[dict[str, Any]], content: list[dict[str, Any]]
) -> dict[date, list[Decimal]]:
    """Aggregate every EDC interval into its local calendar day."""
    values_by_day: dict[date, list[Decimal]] = {}
    for item in content:
        item_date = date.fromisoformat(str(item["date"])[:10])
        values = item.get("values") or []
        totals = values_by_day.setdefault(item_date, [ZERO] * len(columns))
        _add_values(totals, values, len(columns))
    return values_by_day


def parse_daily_profile(response: dict[str, Any]) -> tuple[DailySharing, ...]:
    """Aggregate standard profile rows into calendar days."""
    columns, content, producers, consumers = _profile_layout(response)
    if not content:
        return ()

    # CURRENT vybírá revizi výpočtu, nikoli rozlišení. Endpoint může vrátit
    # čtvrthodinové řádky. Nejprve sečíst každý sloupec za kalendářní den,
    # potom odvodit sdílení; jinak by koordinátor uchoval jen poslední interval.
    values_by_day = _daily_value_totals(columns, content)
    complete_profile = {**response, "content": content}
    complete_hours = _profile_complete_hours(response)

    daily: list[DailySharing] = []
    for item_date in sorted(values_by_day):
        values = _sharing_values(values_by_day[item_date], producers, consumers)
        daily.append(
            DailySharing(
                day=item_date,
                consumption=values[0],
                grid_purchase=values[1],
                shared=values[2],
                producer_overflow=values[3],
                used_overflow=values[4],
                unused_overflow=values[5],
                coverage=values[6],
                consistency_difference=values[7],
                complete=_day_completeness(complete_profile, item_date, complete_hours),
            )
        )

    return tuple(daily)


def parse_daily_target_profiles(
    response: dict[str, Any],
) -> tuple[TargetDailySharing, ...]:
    """Return daily values for every target EAN in an EDC profile response."""
    columns, content, _producers, consumers = _profile_layout(response)
    if not content:
        return ()

    values_by_day = _daily_value_totals(columns, content)
    complete_profile = {**response, "content": content}
    complete_hours = _profile_complete_hours(response)
    daily: list[TargetDailySharing] = []
    for item_date in sorted(values_by_day):
        values = values_by_day[item_date]
        for ean, pair in sorted(consumers.items()):
            consumption, grid_purchase, shared, coverage = _target_values(values, pair)
            daily.append(
                TargetDailySharing(
                    ean=ean,
                    day=item_date,
                    consumption=consumption,
                    grid_purchase=grid_purchase,
                    shared=shared,
                    coverage=coverage,
                    complete=_day_completeness(complete_profile, item_date, complete_hours),
                )
            )
    return tuple(daily)


def _local_hour_as_utc(
    local_hour: datetime,
    local_tz: tzinfo,
    occurrence: int,
) -> datetime:
    """Resolve one EDC wall-clock hour, including DST folds, to UTC."""
    first = local_hour.replace(tzinfo=local_tz, fold=0)
    second = local_hour.replace(tzinfo=local_tz, fold=1)
    first_exists = (
        first.astimezone(UTC).astimezone(local_tz).replace(tzinfo=None)
        == local_hour
    )
    second_exists = (
        second.astimezone(UTC).astimezone(local_tz).replace(tzinfo=None)
        == local_hour
    )
    if not first_exists and not second_exists:
        raise ValueError(
            f"EDC vrátilo neexistující lokální čas {local_hour.isoformat()}."
        )
    ambiguous = (
        first_exists
        and second_exists
        and first.utcoffset() != second.utcoffset()
    )
    if occurrence > 1 or (occurrence and not ambiguous):
        raise ValueError("EDC vrátilo nerozlišitelné duplicitní časové intervaly.")
    resolved = second if ambiguous and occurrence else first
    return resolved.astimezone(UTC)


def parse_hourly_profile(
    response: dict[str, Any], *, local_tz: tzinfo | None = None
) -> tuple[HourlySharing, ...]:
    """Aggregate quarter-hour standard profile rows into clock hours."""
    columns, content, producers, consumers = _profile_layout(response)
    if not content:
        return ()

    completeness = _hour_completeness(response)
    if not completeness:
        return ()
    expected_slots = {0, 15, 30, 45} if profile_resolution(response) == "quarter_hour" else {0}

    values_by_hour: dict[datetime, list[Decimal]] = {}
    hour_slots: dict[datetime, set[int]] = {}
    interval_occurrences: dict[tuple[date, int], int] = {}
    for item in response["content"]:
        start_minutes = _profile_clock_minutes(item["start"])
        hour, minute = divmod(start_minutes, 60)
        item_date = date.fromisoformat(str(item["date"])[:10])
        # Stejný čas HH:mm a HH:mm:00 je tentýž slot. Odlišný zápis nesmí
        # obejít kontrolu duplicity ani spojit dva podzimní DST foldy.
        interval_key = (item_date, start_minutes)
        occurrence = interval_occurrences.get(interval_key, 0)
        if occurrence and local_tz is None:
            raise ValueError("Duplicitní interval vyžaduje ověření časového pásma.")
        interval_occurrences[interval_key] = occurrence + 1
        # Výskyt počítat i pro null: jinak by se při podzimním DST druhá
        # 02:xx chybně přesunula do prvního UTC foldu a spojila cizí sloty.
        if _row_missing_measurement(item):
            continue
        local_hour = datetime.combine(item_date, datetime.min.time()).replace(hour=hour)
        hour_start = (
            _local_hour_as_utc(local_hour, local_tz, occurrence)
            if local_tz is not None
            else local_hour
        )
        totals = values_by_hour.setdefault(hour_start, [ZERO] * len(columns))
        hour_slots.setdefault(hour_start, set()).add(minute)
        _add_values(totals, item.get("values") or [], len(columns))

    hourly: list[HourlySharing] = []
    for hour_start in sorted(values_by_hour):
        values = _sharing_values(values_by_hour[hour_start], producers, consumers)
        hourly.append(
            HourlySharing(
                start=hour_start,
                consumption=values[0],
                grid_purchase=values[1],
                shared=values[2],
                producer_overflow=values[3],
                used_overflow=values[4],
                unused_overflow=values[5],
                coverage=values[6],
                consistency_difference=values[7],
                complete=hour_slots[hour_start] == expected_slots,
            )
        )
    return tuple(hourly)


def parse_hourly_target_profiles(
    response: dict[str, Any], *, local_tz: tzinfo | None = None
) -> tuple[TargetHourlySharing, ...]:
    """Aggregate quarter-hour standard profile rows into clock hours for each target."""
    columns, content, _producers, consumers = _profile_layout(response)
    if not content:
        return ()

    completeness = _hour_completeness(response)
    if not completeness:
        return ()
    expected_slots = {0, 15, 30, 45} if profile_resolution(response) == "quarter_hour" else {0}

    values_by_hour: dict[datetime, list[Decimal]] = {}
    hour_slots: dict[datetime, set[int]] = {}
    interval_occurrences: dict[tuple[date, int], int] = {}
    for item in response["content"]:
        start_minutes = _profile_clock_minutes(item["start"])
        hour, minute = divmod(start_minutes, 60)
        item_date = date.fromisoformat(str(item["date"])[:10])
        # Cílové statistiky používají stejné časové identity jako skupina.
        interval_key = (item_date, start_minutes)
        occurrence = interval_occurrences.get(interval_key, 0)
        if occurrence and local_tz is None:
            raise ValueError("Duplicitní interval vyžaduje ověření časového pásma.")
        interval_occurrences[interval_key] = occurrence + 1
        if _row_missing_measurement(item):
            continue
        local_hour = datetime.combine(item_date, datetime.min.time()).replace(hour=hour)
        hour_start = (
            _local_hour_as_utc(local_hour, local_tz, occurrence)
            if local_tz is not None
            else local_hour
        )
        totals = values_by_hour.setdefault(hour_start, [ZERO] * len(columns))
        hour_slots.setdefault(hour_start, set()).add(minute)
        _add_values(totals, item.get("values") or [], len(columns))

    hourly: list[TargetHourlySharing] = []
    for hour_start in sorted(values_by_hour):
        values = values_by_hour[hour_start]
        for ean, pair in sorted(consumers.items()):
            consumption, grid_purchase, shared, coverage = _target_values(values, pair)
            hourly.append(
                TargetHourlySharing(
                    ean=ean,
                    start=hour_start,
                    consumption=consumption,
                    grid_purchase=grid_purchase,
                    shared=shared,
                    coverage=coverage,
                    complete=hour_slots[hour_start] == expected_slots,
                )
            )
    return tuple(hourly)


def calculate_target_period_summary(
    days: tuple[TargetDailySharing, ...], sale_price: Decimal
) -> TargetPeriodSummary:
    """Sum available rows for one target EAN without rounding inputs."""
    ordered = tuple(sorted((row for row in days if row.complete), key=lambda row: row.day))
    consumption = sum((row.consumption for row in ordered), ZERO)
    shared = sum((row.shared for row in ordered), ZERO)
    return TargetPeriodSummary(
        consumption=consumption,
        grid_purchase=sum((row.grid_purchase for row in ordered), ZERO),
        shared=shared,
        coverage=shared / consumption * Decimal(100) if consumption else ZERO,
        revenue=shared * sale_price,
        data_start=ordered[0].day if ordered else None,
        data_end=ordered[-1].day if ordered else None,
        available_days=len(ordered),
    )


def calculate_target_statistics(
    ean: str,
    days: tuple[TargetDailySharing, ...],
    sale_price: Decimal,
    today: date,
) -> TargetSharingStatistics:
    """Calculate latest and calendar summaries for one target EAN."""
    available = tuple(sorted((row for row in days if row.complete and row.day <= today), key=lambda row: row.day))
    latest = calculate_target_period_summary(
        (available[-1],) if available else (), sale_price
    )
    week_start = today - timedelta(days=today.weekday())
    return TargetSharingStatistics(
        ean=ean,
        latest_day=latest.data_end,
        latest=latest,
        week=calculate_target_period_summary(
            tuple(row for row in available if row.day >= week_start), sale_price
        ),
        month=calculate_target_period_summary(
            tuple(
                row
                for row in available
                if row.day.year == today.year and row.day.month == today.month
            ),
            sale_price,
        ),
        year=calculate_target_period_summary(
            tuple(row for row in available if row.day.year == today.year), sale_price
        ),
        total=calculate_target_period_summary(available, sale_price),
        sale_price=sale_price,
    )


def calculate_statistics(
    days: tuple[DailySharing, ...],
    sale_price: Decimal,
    today: date,
    *,
    target_days: Mapping[str, tuple[TargetDailySharing, ...]] | None = None,
    target_prices: Mapping[str, Decimal] | None = None,
) -> SharingStatistics:
    """Calculate current values from already parsed daily rows."""
    daily = sorted((row for row in days if row.complete), key=lambda row: row.day)
    empty_today = DailySharing(today, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO)
    today_row = next((row for row in daily if row.day == today), empty_today)
    available_rows = [row for row in daily if row.day <= today]
    latest_row = available_rows[-1] if available_rows else empty_today
    latest_day = latest_row.day if available_rows else None
    week_start = today - timedelta(days=today.weekday())
    week_rows = [row for row in available_rows if row.day >= week_start]
    month_rows = [
        row
        for row in available_rows
        if row.day.year == today.year and row.day.month == today.month
    ]
    year_rows = [row for row in available_rows if row.day.year == today.year]
    month_consumption = sum((row.consumption for row in month_rows), ZERO)
    month_shared = sum((row.shared for row in month_rows), ZERO)
    month_coverage = month_shared / month_consumption * Decimal(100) if month_consumption else ZERO
    targets = tuple(
        calculate_target_statistics(
            ean,
            rows,
            (target_prices or {}).get(ean, sale_price),
            today,
        )
        for ean, rows in sorted((target_days or {}).items())
    )
    return SharingStatistics(
        days=tuple(daily),
        today=today_row,
        latest=latest_row,
        latest_day=latest_day,
        month_consumption=month_consumption,
        month_grid_purchase=sum((row.grid_purchase for row in month_rows), ZERO),
        month_shared=month_shared,
        month_overflow=sum((row.producer_overflow for row in month_rows), ZERO),
        month_unused=sum((row.unused_overflow for row in month_rows), ZERO),
        month_coverage=month_coverage,
        month_revenue=month_shared * sale_price,
        today_revenue=today_row.shared * sale_price,
        sale_price=sale_price,
        surplus_utilization_latest_available_day=calculate_surplus_utilization(
            (latest_row,) if latest_day is not None else ()
        ),
        surplus_utilization_this_week=calculate_surplus_utilization(
            tuple(week_rows)
        ),
        surplus_utilization_this_month=calculate_surplus_utilization(
            tuple(month_rows)
        ),
        surplus_utilization_this_year=calculate_surplus_utilization(
            tuple(year_rows)
        ),
        surplus_utilization_total=calculate_surplus_utilization(
            tuple(available_rows)
        ),
        target_statistics=targets,
    )


def calculate_period_summary(
    days: tuple[DailySharing, ...], sale_price: Decimal
) -> PeriodSummary:
    """Sum daily rows for an arbitrary report period."""
    days = tuple(row for row in days if row.complete)
    consumption = sum((row.consumption for row in days), ZERO)
    shared = sum((row.shared for row in days), ZERO)
    return PeriodSummary(
        consumption=consumption,
        grid_purchase=sum((row.grid_purchase for row in days), ZERO),
        shared=shared,
        producer_overflow=sum((row.producer_overflow for row in days), ZERO),
        unused_overflow=sum((row.unused_overflow for row in days), ZERO),
        coverage=shared / consumption * Decimal(100) if consumption else ZERO,
        revenue=shared * sale_price,
    )


def calculate_profile(response: dict[str, Any], sale_price: Decimal, today: date) -> SharingStatistics:
    """Calculate sharing from one standard profile overview response."""
    return calculate_statistics(parse_daily_profile(response), sale_price, today)
