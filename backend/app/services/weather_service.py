"""Weather service using free Open-Meteo API (no API key required).

Uses:
- Geocoding API: https://geocoding-api.open-meteo.com/
- Weather API: https://open-meteo.com/
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather interpretation codes → Russian descriptions
# https://open-meteo.com/en/docs
WMO_CODES: dict[int, str] = {
    0: "Ясно ☀️",
    1: "Преимущественно ясно 🌤",
    2: "Переменная облачность ⛅",
    3: "Пасмурно ☁️",
    45: "Туман 🌫",
    48: "Изморозь 🌫",
    51: "Лёгкая морось 🌧",
    53: "Морось 🌧",
    55: "Сильная морось 🌧",
    56: "Лёгкая ледяная морось 🌧",
    57: "Сильная ледяная морось 🌧",
    61: "Небольшой дождь 🌦",
    63: "Дождь 🌧",
    65: "Сильный дождь 🌧",
    66: "Лёгкий ледяной дождь 🌧",
    67: "Сильный ледяной дождь 🌧",
    71: "Небольшой снег 🌨",
    73: "Снег 🌨",
    75: "Сильный снегопад 🌨",
    77: "Снежные зёрна ❄️",
    80: "Ливень 🌦",
    81: "Сильный ливень 🌧",
    82: "Очень сильный ливень 🌧",
    85: "Небольшой снегопад 🌨",
    86: "Сильный снегопад 🌨",
    95: "Гроза ⛈",
    96: "Гроза с градом ⛈",
    99: "Сильная гроза с градом ⛈",
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


def _wind_dir(degrees: float) -> str:
    """Convert wind direction degrees to Russian compass label."""
    idx = round(degrees / 45) % 8
    return WIND_DIRECTIONS.get(idx, "")


async def geocode(city_name: str) -> dict[str, Any] | None:
    """Resolve city name to coordinates using Open-Meteo Geocoding API.

    Returns dict with keys: name, country, latitude, longitude, timezone
    or None if not found.
    """
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
        except Exception as exc:
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


async def get_weather(city_name: str) -> str:
    """Get current weather for a city, returning formatted Russian text.

    Uses Open-Meteo free API — no API key needed.
    """
    location = await geocode(city_name)
    if location is None:
        return f"Не нашёл город «{city_name}» 😕\nПопробуй уточнить название (например, «Москва» или «Санкт-Петербург»)."

    lat = location["latitude"]
    lon = location["longitude"]
    tz = location["timezone"]
    display_name = location["name"]
    country = location["country"]

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                WEATHER_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": (
                        "temperature_2m,relative_humidity_2m,"
                        "apparent_temperature,weather_code,"
                        "wind_speed_10m,wind_direction_10m"
                    ),
                    "timezone": tz,
                    "forecast_days": 1,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Weather fetch failed for %s: %s", city_name, exc)
            return f"Не смог получить погоду для «{city_name}» 🌧\nПопробуй позже."

    current = data.get("current", {})
    temp = current.get("temperature_2m")
    feels = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    code = current.get("weather_code", 0)
    wind_speed = current.get("wind_speed_10m")
    wind_dir_deg = current.get("wind_direction_10m")

    condition = WMO_CODES.get(code, "Неизвестно")

    lines = [f"🌍 **Погода в {display_name}**"]
    if country:
        lines[0] += f", {country}"

    lines.append("")
    if temp is not None:
        lines.append(f"🌡 Температура: **{temp:.0f}°C**")
    if feels is not None:
        lines.append(f"🤔 Ощущается как: **{feels:.0f}°C**")
    lines.append(f"☁️ {condition}")
    if humidity is not None:
        lines.append(f"💧 Влажность: **{humidity}%**")
    if wind_speed is not None:
        wdir = _wind_dir(wind_dir_deg) if wind_dir_deg is not None else ""
        wdir_str = f", {wdir}" if wdir else ""
        lines.append(f"💨 Ветер: **{wind_speed:.1f} м/с**{wdir_str}")

    return "\n".join(lines)
