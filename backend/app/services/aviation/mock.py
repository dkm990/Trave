"""Mock flight provider for development and demo purposes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.services.aviation.base import BaseFlightProvider, FlightLookupResult


# Demo flights for testing various states
_MOCK_FLIGHTS: dict[str, FlightLookupResult] = {
    "TK1723": FlightLookupResult(
        flight_number="TK1723",
        airline_code="TK",
        airline_name="Turkish Airlines",
        departure_city="Москва",
        arrival_city="Стамбул",
        departure_airport="VKO",
        arrival_airport="IST",
        departure_terminal="A",
        arrival_terminal="1",
        scheduled_departure_at=datetime(2026, 6, 1, 8, 30),
        actual_departure_at=datetime(2026, 6, 1, 8, 45),
        estimated_departure_at=None,
        scheduled_arrival_at=datetime(2026, 6, 1, 12, 15),
        actual_arrival_at=None,
        estimated_arrival_at=datetime(2026, 6, 1, 12, 30),
        status="departed",
        check_in_counter="42-45",
        gate="B7",
        baggage_belt=None,
    ),
    "SU1234": FlightLookupResult(
        flight_number="SU1234",
        airline_code="SU",
        airline_name="Аэрофлот",
        departure_city="Москва",
        arrival_city="Стамбул",
        departure_airport="SVO",
        arrival_airport="IST",
        departure_terminal="D",
        arrival_terminal="1",
        scheduled_departure_at=datetime(2026, 6, 1, 14, 0),
        actual_departure_at=None,
        estimated_departure_at=datetime(2026, 6, 1, 14, 55),
        scheduled_arrival_at=datetime(2026, 6, 1, 17, 45),
        actual_arrival_at=None,
        estimated_arrival_at=datetime(2026, 6, 1, 18, 40),
        status="delayed",
        check_in_counter="120-124",
        gate="D22",
        baggage_belt=None,
    ),
    "PC1200": FlightLookupResult(
        flight_number="PC1200",
        airline_code="PC",
        airline_name="Pegasus Airlines",
        departure_city="Стамбул",
        arrival_city="Москва",
        departure_airport="SAW",
        arrival_airport="VKO",
        departure_terminal=None,
        arrival_terminal="A",
        scheduled_departure_at=datetime(2026, 6, 8, 19, 30),
        actual_departure_at=datetime(2026, 6, 8, 19, 30),
        estimated_departure_at=None,
        scheduled_arrival_at=datetime(2026, 6, 8, 23, 45),
        actual_arrival_at=datetime(2026, 6, 8, 23, 38),
        estimated_arrival_at=None,
        status="arrived",
        check_in_counter=None,
        gate="14",
        baggage_belt="3",
    ),
    "TK0050": FlightLookupResult(
        flight_number="TK0050",
        airline_code="TK",
        airline_name="Turkish Airlines",
        departure_city="Стамбул",
        arrival_city="Москва",
        departure_airport="IST",
        arrival_airport="VKO",
        departure_terminal="1",
        arrival_terminal="A",
        scheduled_departure_at=datetime(2026, 6, 8, 22, 0),
        actual_departure_at=None,
        estimated_departure_at=None,
        scheduled_arrival_at=datetime(2026, 6, 9, 2, 15),
        actual_arrival_at=None,
        estimated_arrival_at=None,
        status="scheduled",
        check_in_counter=None,
        gate=None,
        baggage_belt=None,
    ),
}


class MockFlightProvider(BaseFlightProvider):
    """Returns hardcoded demo data. No external API calls."""

    async def lookup(self, flight_number: str, date: datetime) -> Optional[FlightLookupResult]:
        key = flight_number.upper().replace(" ", "")
        return _MOCK_FLIGHTS.get(key)

    async def get_status(self, flight_number: str, date: datetime) -> Optional[FlightLookupResult]:
        # Same as lookup for mock — in real providers this would hit a live status endpoint
        return await self.lookup(flight_number, date)

    @property
    def provider_name(self) -> str:
        return "mock"
