"""Weather service using free Open-Meteo API (no API key required)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MAX_FORECAST_DAYS = 16

MONTHS_RU: dict[int, str] = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

WMO_CODES: dict[int, str] = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь",
    51: "лёгкая морось",
    53: "морось",
    55: "сильная морось",
    56: "лёгкая ледяная морось",
    57: "сильная ледяная морось",
    61: "небольшой дождь",
    63: "дождь",
    65: "сильный дождь",
    66: "лёдяной дождь",
    67: "сильный ледяной дождь",
    71: "небольшой снег",
    73: "снег",
    75: "сильный снег",
    77: "снежная крупа",
    80: "ливень",
    81: "сильный ливень",
    82: "очень сильный ливень",
    85: "небольшой снегопад",
    86: "сильный снегопад",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}

WIND_DIRECTIONS: dict[int, str] = {
    0: "северный",
    1: "северо-восточный",
    2: "восточный",
    3: "юго-восточный",
    4: "южный",
    5: "юго-западный",
    6: "западный",
    7: "северо-западный",
}


@dataclass
class WeatherDay:
    dt: date
    temp_max: float | None
    feels_max: float | None
    weather_code: int
    wind_speed_max: float | None
    wind_direction_deg: float | None
    rain_probability_max: int | None


def _fmt_day_ru(d: date) -> str:
    return f"{d.day} {MONTHS_RU[d.month]}"


def _plural_days_ru(value: int) -> str:
    value_abs = abs(value) % 100
    if 11 <= value_abs <= 14:
        return "дней"
    last = value_abs % 10
    if last == 1:
        return "день"
    if 2 <= last <= 4:
        return "дня"
    return "дней"


def _wind_dir(degrees: float) -> str:
    idx = round(degrees / 45) % 8
    return WIND_DIRECTIONS.get(idx, "")


def _is_windy(speed: float | None) -> bool:
    return speed is not None and speed >= 8.0


def _format_location(display_name: str, country: str) -> str:
    if country:
        return f"{display_name}, {country}"
    return display_name


def _single_day_advice(
    *,
    temp_max: float | None,
    wind_speed: float | None,
    rain_probability: int | None,
    weather_code: int,
) -> str:
    if rain_probability is not None and rain_probability >= 60:
        return "По ощущениям: вероятен дождь. Возьмите зонт или непромокаемую куртку."
    if _is_windy(wind_speed):
        return "По ощущениям: прохладно и ветрено. Для прогулки лучше взять лёгкую куртку или худи."
    if temp_max is not None and temp_max >= 30:
        return "По ощущениям: будет жарко. Возьмите воду, головной убор и лёгкую одежду."
    if temp_max is not None and temp_max <= 12:
        return "По ощущениям: прохладно. На вечер пригодится кофта или лёгкая куртка."
    if weather_code in {45, 48}:
        return "По ощущениям: возможен туман, закладывайте запас по времени в поездках."
    return "По ощущениям: погода комфортная для прогулок. На вечер лучше взять лёгкую кофту."


def _multi_day_advice(days: list[WeatherDay]) -> str:
    if not days:
        return "В целом: прогноз ограничен, лучше проверить погоду ещё раз ближе к дате."
    rainy = sum(1 for d in days if (d.rain_probability_max or 0) >= 60)
    windy = sum(1 for d in days if _is_windy(d.wind_speed_max))
    hot = any((d.temp_max or -100) >= 30 for d in days)
    cool = any((d.temp_max or 100) <= 12 for d in days)

    if rainy >= max(1, len(days) // 2):
        return "В целом: в прогнозе много дождя. Возьмите зонт и непромокаемую обувь."
    if windy >= max(1, len(days) // 2):
        return "В целом: ожидается ветреная погода. На вечер лучше иметь лёгкую ветровку."
    if hot:
        return "В целом: тепло или жарко. Прогулки лучше планировать утром и вечером."
    if cool:
        return "В целом: местами прохладно. Лёгкая кофта или худи пригодится."
    return "В целом: погода подходит для прогулок. На вечер лучше взять лёгкую кофту."


def _scope_header(
    *,
    location_name: str,
    location_surface: str | None,
    mode: str,
    days_count: int | None = None,
    target_date: date | None = None,
) -> list[str]:
    if location_surface:
        if mode == "today":
            return [f"Вот погода {location_surface} на сегодня."]
        if mode == "weekend":
            return [f"Погода {location_surface} на выходные:"]
        if mode == "week":
            return [f"Погода {location_surface} на неделю:"]
        if mode == "days":
            return [f"Погода {location_surface} на ближайшие {days_count} {_plural_days_ru(days_count or 0)}:"]
        if mode == "date" and target_date is not None:
            return [f"Погода {location_surface} на {_fmt_day_ru(target_date)}"]
        return [f"Погода {location_surface}"]

    # neutral fallback when no surface phrase was found
    lines = [f"Погода: {location_name}", ""]
    if mode == "today":
        lines.append("На сегодня:")
    elif mode == "weekend":
        lines.append("На выходные:")
    elif mode == "week":
        lines.append("На неделю:")
    elif mode == "days":
        lines.append(f"На ближайшие {days_count} {_plural_days_ru(days_count or 0)}:")
    elif mode == "date" and target_date is not None:
        lines.append(f"На {_fmt_day_ru(target_date)}:")
    else:
        lines.append("Прогноз:")
    return lines


def _compact_day_line(day: WeatherDay, *, today: date) -> str:
    if day.dt == today:
        label = "Сегодня"
    elif day.dt == today + timedelta(days=1):
        label = "Завтра"
    else:
        label = _fmt_day_ru(day.dt)

    temp = f"{round(day.temp_max)}°C" if day.temp_max is not None else "н/д"
    parts = [temp, WMO_CODES.get(day.weather_code, "без уточнения")]
    if _is_windy(day.wind_speed_max):
        parts.append("ветрено")
    if day.rain_probability_max is not None and day.rain_probability_max >= 40:
        parts.append(f"осадки {day.rain_probability_max}%")
    return f"{label}: {', '.join(parts)}"


def _build_single_day_text(
    *,
    location_name: str,
    location_surface: str | None,
    day: WeatherDay,
    is_today: bool,
    current: dict[str, Any],
    requested_date: date | None,
) -> str:
    mode = "today" if is_today else "date"
    lines = _scope_header(
        location_name=location_name,
        location_surface=location_surface,
        mode=mode,
        target_date=requested_date or day.dt,
    )
    lines.append("")

    if day.temp_max is not None:
        lines.append(f"Днём: около {round(day.temp_max)}°C")

    feels = day.feels_max
    if is_today and current.get("apparent_temperature") is not None:
        feels = current.get("apparent_temperature")
    if feels is not None:
        lines.append(f"Ощущается как: {round(feels)}°C")

    lines.append(WMO_CODES.get(day.weather_code, "Погодные условия без уточнения").capitalize())

    wind_speed = day.wind_speed_max if day.wind_speed_max is not None else current.get("wind_speed_10m")
    wind_dir_deg = (
        day.wind_direction_deg
        if day.wind_direction_deg is not None
        else current.get("wind_direction_10m")
    )
    if wind_speed is not None:
        wind_dir = _wind_dir(float(wind_dir_deg)) if wind_dir_deg is not None else ""
        if wind_dir:
            lines.append(f"Ветер: {wind_dir}, {wind_speed:.1f} м/с")
        else:
            lines.append(f"Ветер: {wind_speed:.1f} м/с")

    humidity = current.get("relative_humidity_2m")
    if humidity is not None:
        lines.append(f"Влажность: {int(humidity)}%")

    if day.rain_probability_max is not None:
        lines.append(f"Вероятность осадков: {int(day.rain_probability_max)}%")

    lines.append("")
    lines.append(
        _single_day_advice(
            temp_max=day.temp_max,
            wind_speed=wind_speed,
            rain_probability=day.rain_probability_max,
            weather_code=day.weather_code,
        )
    )
    return "\n".join(lines)


def _build_multi_day_text(
    *,
    location_name: str,
    location_surface: str | None,
    days: list[WeatherDay],
    today: date,
    mode: str,
    requested_days: int,
) -> str:
    lines = _scope_header(
        location_name=location_name,
        location_surface=location_surface,
        mode=mode,
        days_count=requested_days,
    )
    lines.append("")

    if mode == "weekend":
        preview_days = days[:2]
    elif requested_days <= 5:
        preview_days = days[:requested_days]
    else:
        preview_days = days[: min(requested_days, 7)]

    for day in preview_days:
        lines.append(_compact_day_line(day, today=today))

    lines.append("")
    lines.append(_multi_day_advice(preview_days))
    return "\n".join(lines)


def _weekend_dates(today: date) -> tuple[date, date]:
    days_until_saturday = (5 - today.weekday()) % 7
    saturday = today + timedelta(days=days_until_saturday)
    sunday = saturday + timedelta(days=1)
    return saturday, sunday


def _strip_location_period_suffix(value: str) -> str:
    """Remove trailing date/range phrases from location query."""
    text = (value or "").strip().rstrip("?!,.")
    patterns = [
        r"\s+(?:на|за)\s*\d{1,2}\s*(?:дн(?:я|ей|и)?|day|days)\s*$",
        r"\s+(?:на|за)\s+недел[юи]\s*$",
        r"\s+(?:на|за)\s+выходн(?:ые|ых)\s*$",
        r"\s+(?:на|за)\s*\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+\d{4})?\s*$",
        r"\s+(?:сегодня|завтра)\s*$",
    ]
    prev = None
    while text and text != prev:
        prev = text
        for pat in patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE).strip().rstrip("?!,.")
    return text


def _normalize_geocode_base_query(value: str) -> str:
    """Prepare location query for geocoder, keeping it dictionary-free."""
    text = (value or "").strip()
    text = re.sub(r"^\s*трейв[\s,.:-]*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:в|во|на)\s+", "", text, flags=re.IGNORECASE)
    text = _strip_location_period_suffix(text)
    text = re.sub(r"\s+", " ", text).strip(" ,.")
    return text


def _fallback_nominative_candidates(value: str) -> list[str]:
    """Fallback candidates from common Russian case endings."""
    token = (value or "").strip()
    if not token or " " in token or not re.search(r"[А-Яа-яЁё]", token):
        return []
    lower = token.lower()
    if len(token) < 4:
        return []

    candidates: list[str] = []

    # Дубае -> Дубай
    if lower.endswith("ае"):
        candidates.append(token[:-1] + "й")

    # Париже -> Париж, Стамбуле -> Стамбул, Москве -> Москв
    if lower.endswith("е"):
        candidates.append(token[:-1])

        # Москве -> Москва, Праге -> Прага, Риге -> Рига, Барселоне -> Барселона
        candidates.append(token[:-1] + "а")

    # Generic extra fallback
    if lower[-1] in "аоуыэюяиё" and len(token) >= 5:
        candidates.append(token[:-1])

    deduped: list[str] = []
    for candidate in candidates:
        clean = candidate.strip()
        if clean and clean != token and clean not in deduped:
            deduped.append(clean)
    return deduped


def _build_geocode_candidates(value: str) -> list[str]:
    """Try raw-normalized query first, then safe case-based fallback."""
    base = _normalize_geocode_base_query(value)
    candidates: list[str] = []
    if base:
        candidates.append(base)

    for fallback in _fallback_nominative_candidates(base):
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates


async def geocode(city_name: str) -> dict[str, Any] | None:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                GEOCODING_URL,
                params={
                    "name": city_name,
                    "count": 1,
                    "language": "ru",
                    "format": "json",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Geocoding failed for %s: %s", city_name, exc)
            return None

    results = data.get("results")
    if not results:
        return None

    r = results[0]
    return {
        "name": r.get("name", city_name),
        "country": r.get("country", ""),
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "timezone": r.get("timezone", "auto"),
    }


async def _fetch_forecast(
    *,
    latitude: float,
    longitude: float,
    timezone: str,
    forecast_days: int,
) -> dict[str, Any] | None:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                WEATHER_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": (
                        "temperature_2m,relative_humidity_2m,apparent_temperature,"
                        "weather_code,wind_speed_10m,wind_direction_10m"
                    ),
                    "daily": (
                        "weather_code,temperature_2m_max,apparent_temperature_max,"
                        "wind_speed_10m_max,wind_direction_10m_dominant,"
                        "precipitation_probability_max"
                    ),
                    "timezone": timezone,
                    "forecast_days": forecast_days,
                    "windspeed_unit": "ms",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Weather fetch failed lat=%s lon=%s tz=%s days=%s: %s",
                latitude,
                longitude,
                timezone,
                forecast_days,
                exc,
            )
            return None


def _extract_daily_rows(raw: dict[str, Any]) -> list[WeatherDay]:
    daily = raw.get("daily") or {}
    times = daily.get("time") or []
    temp_max = daily.get("temperature_2m_max") or []
    feels_max = daily.get("apparent_temperature_max") or []
    weather_codes = daily.get("weather_code") or []
    wind_max = daily.get("wind_speed_10m_max") or []
    wind_dir = daily.get("wind_direction_10m_dominant") or []
    rain_prob = daily.get("precipitation_probability_max") or []

    required_len = len(times)
    if weather_codes:
        required_len = min(required_len, len(weather_codes))
    if temp_max:
        required_len = min(required_len, len(temp_max))

    rows: list[WeatherDay] = []
    for idx in range(required_len):
        dt_raw = times[idx]
        try:
            dt = datetime.fromisoformat(dt_raw).date()
        except Exception:  # noqa: BLE001
            continue
        rows.append(
            WeatherDay(
                dt=dt,
                temp_max=temp_max[idx] if idx < len(temp_max) else None,
                feels_max=feels_max[idx] if idx < len(feels_max) else None,
                weather_code=int(weather_codes[idx]) if idx < len(weather_codes) else 0,
                wind_speed_max=wind_max[idx] if idx < len(wind_max) else None,
                wind_direction_deg=wind_dir[idx] if idx < len(wind_dir) else None,
                rain_probability_max=(
                    int(rain_prob[idx]) if idx < len(rain_prob) and rain_prob[idx] is not None else None
                ),
            )
        )
    return rows


def _pick_target_date_day(rows: list[WeatherDay], target_date: date) -> WeatherDay | None:
    for row in rows:
        if row.dt == target_date:
            return row
    return None


async def get_weather(
    city_name: str,
    *,
    target_date: date | None = None,
    days: int | None = None,
    today_requested: bool = False,
    location_surface: str | None = None,
    weekend_requested: bool = False,
) -> str:
    location = None
    used_query = city_name
    candidates = _build_geocode_candidates(city_name)
    for candidate in candidates:
        location = await geocode(candidate)
        if location is not None:
            used_query = candidate
            break

    if location is None and city_name not in candidates:
        location = await geocode(city_name)
        if location is not None:
            used_query = city_name

    if location is None:
        return "Не нашёл город. Попробуй написать название в именительном падеже: Стамбул, Париж, Дубай."

    logger.info("weather location query resolved: source=%s resolved=%s", city_name, used_query)

    location_name = _format_location(location["name"], location["country"])
    today = date.today()

    mode = "today"
    requested_days = max(1, min(days or 1, MAX_FORECAST_DAYS))
    weekend_dates: tuple[date, date] | None = None

    if weekend_requested:
        mode = "weekend"
        saturday, sunday = _weekend_dates(today)
        weekend_dates = (saturday, sunday)
        requested_days = max(1, min((sunday - today).days + 1, MAX_FORECAST_DAYS))
        target_date = None
    elif target_date is not None:
        mode = "today" if today_requested or target_date == today else "date"
        delta = (target_date - today).days
        if delta < 0:
            target_date = today
            today_requested = True
            mode = "today"
            requested_days = 1
        else:
            requested_days = max(1, min(delta + 1, MAX_FORECAST_DAYS))
    elif days and days > 1:
        mode = "week" if days == 7 else "days"
    else:
        mode = "today"

    raw = await _fetch_forecast(
        latitude=location["latitude"],
        longitude=location["longitude"],
        timezone=location["timezone"],
        forecast_days=requested_days,
    )
    if raw is None:
        return f"Не смог получить погоду для «{location_name}». Попробуйте позже."

    rows = _extract_daily_rows(raw)
    if not rows:
        return f"Пока не удалось получить прогноз для «{location_name}». Попробуйте позже."

    if mode in {"weekend", "week", "days"}:
        preview = rows
        if weekend_dates:
            sat, sun = weekend_dates
            preview = [d for d in rows if d.dt in {sat, sun}]
            if len(preview) < 2:
                header_lines = _scope_header(
                    location_name=location_name,
                    location_surface=location_surface,
                    mode="weekend",
                )
                header_lines.extend(
                    [
                        "",
                        "Точный прогноз на эти выходные пока недоступен. Обычно прогноз точнее за несколько дней до поездки.",
                    ]
                )
                return "\n".join(header_lines)

        return _build_multi_day_text(
            location_name=location_name,
            location_surface=location_surface,
            days=preview,
            today=today,
            mode=mode,
            requested_days=min(days or len(preview), len(preview)),
        )

    if target_date is not None:
        target_day = _pick_target_date_day(rows, target_date)
        if target_day is None:
            return (
                f"Погода в {location_name} на {_fmt_day_ru(target_date)}\n\n"
                "Точный прогноз на эту дату пока недоступен. Обычно прогноз точнее за несколько дней до поездки."
            )
        return _build_single_day_text(
            location_name=location_name,
            location_surface=location_surface,
            day=target_day,
            is_today=today_requested or target_day.dt == today,
            current=raw.get("current") or {},
            requested_date=target_date,
        )

    # default: today's detailed response
    today_day = rows[0]
    return _build_single_day_text(
        location_name=location_name,
        location_surface=location_surface,
        day=today_day,
        is_today=True,
        current=raw.get("current") or {},
        requested_date=today,
    )
