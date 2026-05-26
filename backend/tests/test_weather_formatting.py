from __future__ import annotations

from datetime import date, timedelta

import pytest


def _build_fake_forecast(start: date, days: int = 10) -> dict:
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    return {
        "current": {
            "temperature_2m": 20.0,
            "relative_humidity_2m": 56,
            "apparent_temperature": 19.0,
            "weather_code": 1,
            "wind_speed_10m": 9.5,
            "wind_direction_10m": 45.0,
        },
        "daily": {
            "time": dates,
            "weather_code": [1, 2, 0, 3, 2, 1, 1, 2, 1, 0][:days],
            "temperature_2m_max": [20.0, 22.0, 24.0, 23.0, 21.0, 20.0, 19.0, 22.0, 23.0, 24.0][:days],
            "apparent_temperature_max": [19.0, 21.0, 23.0, 22.0, 20.0, 19.0, 18.0, 21.0, 22.0, 23.0][:days],
            "wind_speed_10m_max": [9.5, 6.0, 4.0, 5.0, 4.0, 3.0, 3.0, 6.0, 5.0, 4.0][:days],
            "wind_direction_10m_dominant": [45.0, 90.0, 100.0, 180.0, 200.0, 250.0, 270.0, 80.0, 60.0, 30.0][:days],
            "precipitation_probability_max": [20, 35, 10, 40, 15, 15, 20, 10, 5, 5][:days],
        },
    }


@pytest.fixture
def weather_mocks(monkeypatch):
    from app.services import weather_service

    async def _fake_geocode(city_name: str):
        return {
            "name": city_name,
            "country": "Турция",
            "latitude": 41.0,
            "longitude": 29.0,
            "timezone": "Europe/Istanbul",
        }

    async def _fake_fetch_forecast(*, latitude, longitude, timezone, forecast_days):
        return _build_fake_forecast(date.today(), max(10, forecast_days))

    monkeypatch.setattr(weather_service, "geocode", _fake_geocode)
    monkeypatch.setattr(weather_service, "_fetch_forecast", _fake_fetch_forecast)
    return weather_service


def test_extract_weather_location_surface_and_query():
    from app.bot.intent_router import _extract_weather_location

    q, s = _extract_weather_location("Трейв, погода в Стамбуле на 2 дня")
    assert q == "Стамбул"
    assert s == "в Стамбуле"

    q1, s1 = _extract_weather_location("Трейв, погода в Дубае завтра")
    assert q1 in {"Дубае", "Дубай"}
    assert s1 == "в Дубае"

    q2, s2 = _extract_weather_location("Трейв, погода на Бали на неделю")
    assert q2 == "Бали"
    assert s2 == "на Бали"

    q3, s3 = _extract_weather_location("Трейв, погода Стамбул на 2 дня")
    assert q3 == "Стамбул"
    assert s3 is None


def test_extract_weather_days_and_date_are_not_confused():
    from app.bot.intent_router import _extract_weather_days, _extract_weather_target_date

    assert _extract_weather_days("Трейв, погода в Стамбуле на 4 дня") == 4
    dt, _ = _extract_weather_target_date("Трейв, погода в Стамбуле на 4 июня")
    assert dt is not None and dt.day == 4 and dt.month == 6


def test_extract_weather_week_and_weekend():
    from app.bot.intent_router import _extract_weather_days, _is_weekend_request

    assert _extract_weather_days("Трейв, погода в Стамбуле на неделю") == 7
    assert _extract_weather_days("Трейв, погода в Стамбуле на выходные") == 2
    assert _is_weekend_request("Трейв, погода в Стамбуле на выходные") is True


@pytest.mark.asyncio
async def test_surface_format_for_2_days(weather_mocks):
    text = await weather_mocks.get_weather(
        "Стамбуле",
        days=2,
        location_surface="в Стамбуле",
    )
    assert text.startswith("Погода в Стамбуле на ближайшие 2 дня:")


@pytest.mark.asyncio
async def test_surface_format_for_week(weather_mocks):
    text = await weather_mocks.get_weather(
        "Бали",
        days=7,
        location_surface="на Бали",
    )
    assert text.startswith("Погода на Бали на неделю:")


@pytest.mark.asyncio
async def test_neutral_format_without_surface(weather_mocks):
    text = await weather_mocks.get_weather(
        "Стамбул",
        days=2,
        location_surface=None,
    )
    assert text.startswith("Погода: Стамбул, Турция")
    assert "На ближайшие 2 дня:" in text


@pytest.mark.asyncio
async def test_weekend_is_not_nearest_two_days(weather_mocks):
    text = await weather_mocks.get_weather(
        "Стамбуле",
        location_surface="в Стамбуле",
        weekend_requested=True,
    )
    assert text.startswith("Погода в Стамбуле на выходные:")
    assert "Сегодня:" not in text


@pytest.mark.asyncio
async def test_out_of_range_forecast_does_not_fabricate_result(monkeypatch):
    from app.services import weather_service

    async def _fake_geocode(city_name: str):
        return {
            "name": city_name,
            "country": "Турция",
            "latitude": 41.0,
            "longitude": 29.0,
            "timezone": "Europe/Istanbul",
        }

    async def _fake_fetch_forecast(*, latitude, longitude, timezone, forecast_days):
        return _build_fake_forecast(date.today(), 3)

    monkeypatch.setattr(weather_service, "geocode", _fake_geocode)
    monkeypatch.setattr(weather_service, "_fetch_forecast", _fake_fetch_forecast)
    target = date.today() + timedelta(days=10)
    text = await weather_service.get_weather("Стамбул", target_date=target)
    assert "Точный прогноз на эту дату пока недоступен." in text


@pytest.mark.asyncio
async def test_weather_response_has_no_raw_markdown_markers(weather_mocks):
    text = await weather_mocks.get_weather("Стамбул", days=4)
    assert "**" not in text
    assert "__" not in text
    assert "###" not in text


@pytest.mark.asyncio
async def test_weather_response_contains_practical_advice(weather_mocks):
    text = await weather_mocks.get_weather("Стамбул", target_date=date.today() + timedelta(days=1))
    assert "По ощущениям:" in text or "В целом:" in text


@pytest.mark.asyncio
async def test_get_weather_retries_with_case_normalization(monkeypatch):
    from app.services import weather_service

    attempts: list[str] = []

    async def _fake_geocode(city_name: str):
        attempts.append(city_name)
        if city_name == "Стамбул":
            return {
                "name": "Стамбул",
                "country": "Турция",
                "latitude": 41.0,
                "longitude": 29.0,
                "timezone": "Europe/Istanbul",
            }
        return None

    async def _fake_fetch_forecast(*, latitude, longitude, timezone, forecast_days):
        return _build_fake_forecast(date.today(), max(10, forecast_days))

    monkeypatch.setattr(weather_service, "geocode", _fake_geocode)
    monkeypatch.setattr(weather_service, "_fetch_forecast", _fake_fetch_forecast)

    text = await weather_service.get_weather(
        "Стамбуле",
        days=2,
        location_surface="в Стамбуле",
    )
    assert attempts[:2] == ["Стамбуле", "Стамбул"]
    assert text.startswith("Погода в Стамбуле на ближайшие 2 дня:")


@pytest.mark.asyncio
async def test_unknown_city_returns_clear_hint(monkeypatch):
    from app.services import weather_service

    async def _fake_geocode(_city_name: str):
        return None

    monkeypatch.setattr(weather_service, "geocode", _fake_geocode)
    text = await weather_service.get_weather("Несуществоград")
    assert "Не нашёл город." in text
    assert "Стамбул, Париж, Дубай" in text


@pytest.mark.asyncio
async def test_get_weather_retries_with_dubai_variant(monkeypatch):
    from app.services import weather_service

    attempts: list[str] = []

    async def _fake_geocode(city_name: str):
        attempts.append(city_name)
        if city_name == "Дубай":
            return {
                "name": "Дубай",
                "country": "ОАЭ",
                "latitude": 25.2,
                "longitude": 55.3,
                "timezone": "Asia/Dubai",
            }
        return None

    async def _fake_fetch_forecast(*, latitude, longitude, timezone, forecast_days):
        return _build_fake_forecast(date.today(), max(10, forecast_days))

    monkeypatch.setattr(weather_service, "geocode", _fake_geocode)
    monkeypatch.setattr(weather_service, "_fetch_forecast", _fake_fetch_forecast)

    text = await weather_service.get_weather(
        "Дубае",
        target_date=date.today() + timedelta(days=1),
        location_surface="в Дубае",
    )
    assert attempts[:2] == ["Дубае", "Дубай"]
    assert text.startswith("Погода в Дубае на ")
