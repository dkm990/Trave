"""AeroDataBox provider via RapidAPI."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from app.services.aviation.base import (
    BaseFlightProvider,
    FlightLookupResult,
    ProviderConfigurationError,
    ProviderRateLimitError,
)
from app.services.aviation.utils import normalize_flight_number

logger = logging.getLogger(__name__)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _status(value: Any) -> str:
    raw = str(value or "scheduled").lower()
    if "cancel" in raw:
        return "cancelled"
    if "arriv" in raw or "land" in raw:
        return "arrived"
    if "depart" in raw or "airborne" in raw:
        return "departed"
    if "delay" in raw:
        return "delayed"
    if "board" in raw:
        return "boarding"
    return "scheduled"


def _time(section: dict[str, Any], *keys: str) -> Optional[datetime]:
    for key in keys:
        value = section.get(key)
        if isinstance(value, dict):
            parsed = _parse_dt(value.get("local") or value.get("utc"))
            if parsed:
                return parsed
        parsed = _parse_dt(value)
        if parsed:
            return parsed
    return None


class AeroDataBoxProvider(BaseFlightProvider):
    """Flight lookup provider backed by AeroDataBox on RapidAPI."""

    def __init__(
        self,
        api_key: str,
        api_host: str = "aerodatabox.p.rapidapi.com",
        *,
        timeout_seconds: float = 10,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._api_key = api_key.strip()
        self._api_host = api_host.strip() or "aerodatabox.p.rapidapi.com"
        self._timeout_seconds = timeout_seconds
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: dict[tuple[str, str], tuple[datetime, Optional[FlightLookupResult]]] = {}

    async def lookup(self, flight_number: str, date: datetime) -> Optional[FlightLookupResult]:
        if not self._api_key:
            logger.error("AeroDataBox provider selected but AERODATABOX_API_KEY is not configured")
            raise ProviderConfigurationError("AeroDataBox API key is not configured")

        normalized = normalize_flight_number(flight_number)
        date_local = date.date().isoformat()
        cache_key = (normalized, date_local)
        now = datetime.utcnow()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        url = f"https://{self._api_host}/flights/number/{normalized}/{date_local}"
        headers = {
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": self._api_host,
        }
        params = {
            "dateLocalRole": "Departure",
            "withAircraftImage": "false",
            "withLocation": "false",
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(url, headers=headers, params=params)

        if response.status_code == 429:
            logger.warning("AeroDataBox rate limited flight=%s date=%s", normalized, date_local)
            raise ProviderRateLimitError("AeroDataBox rate limit reached")
        if response.status_code == 404:
            self._cache[cache_key] = (now, None)
            return None
        response.raise_for_status()
        raw = response.json()
        logger.info("AeroDataBox raw response flight=%s date=%s raw=%r", normalized, date_local, raw)
        result = self._map_response(normalized, raw)
        self._cache[cache_key] = (now, result)
        return result

    async def get_status(self, flight_number: str, date: datetime) -> Optional[FlightLookupResult]:
        return await self.lookup(flight_number, date)

    @property
    def provider_name(self) -> str:
        return "aerodatabox"

    def _map_response(self, normalized: str, raw: Any) -> Optional[FlightLookupResult]:
        rows = raw
        if isinstance(raw, dict):
            rows = raw.get("items") or raw.get("flights") or raw.get("data") or []
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            return None

        departure = row.get("departure") if isinstance(row.get("departure"), dict) else {}
        arrival = row.get("arrival") if isinstance(row.get("arrival"), dict) else {}
        dep_airport = departure.get("airport") if isinstance(departure.get("airport"), dict) else {}
        arr_airport = arrival.get("airport") if isinstance(arrival.get("airport"), dict) else {}
        airline = row.get("airline") if isinstance(row.get("airline"), dict) else {}
        number = _first_str(row.get("number"), row.get("flightNumber"), normalized)
        airline_code = _first_str(airline.get("iata"), airline.get("icao"), "".join(ch for ch in normalized if ch.isalpha())[:3], "??")

        scheduled_departure = _time(departure, "scheduledTime", "scheduledTimeLocal", "scheduled")
        scheduled_arrival = _time(arrival, "scheduledTime", "scheduledTimeLocal", "scheduled")
        actual_departure = _time(departure, "actualTime", "actualTimeLocal", "actual")
        actual_arrival = _time(arrival, "actualTime", "actualTimeLocal", "actual")
        estimated_departure = _time(departure, "revisedTime", "estimatedTime", "estimatedTimeLocal")
        estimated_arrival = _time(arrival, "revisedTime", "estimatedTime", "estimatedTimeLocal")

        return FlightLookupResult(
            flight_number=normalize_flight_number(number) or normalized,
            airline_code=airline_code,
            airline_name=_first_str(airline.get("name")),
            departure_city=_first_str(dep_airport.get("municipalityName"), dep_airport.get("shortName"), dep_airport.get("name")),
            arrival_city=_first_str(arr_airport.get("municipalityName"), arr_airport.get("shortName"), arr_airport.get("name")),
            departure_airport=_first_str(dep_airport.get("iata"), dep_airport.get("icao")),
            arrival_airport=_first_str(arr_airport.get("iata"), arr_airport.get("icao")),
            departure_terminal=_first_str(departure.get("terminal")) or None,
            arrival_terminal=_first_str(arrival.get("terminal")) or None,
            scheduled_departure_at=scheduled_departure,
            actual_departure_at=actual_departure,
            estimated_departure_at=estimated_departure,
            scheduled_arrival_at=scheduled_arrival,
            actual_arrival_at=actual_arrival,
            estimated_arrival_at=estimated_arrival,
            status=_status(row.get("status")),
            check_in_counter=_first_str(departure.get("checkInDesk"), departure.get("checkInCounter")) or None,
            gate=_first_str(departure.get("gate")) or None,
            baggage_belt=_first_str(arrival.get("baggageBelt")) or None,
            raw=row,
        )
