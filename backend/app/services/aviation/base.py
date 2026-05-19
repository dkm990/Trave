"""Abstract base for flight data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class ProviderConfigurationError(Exception):
    """Raised when a provider is selected but not configured."""


class ProviderRateLimitError(Exception):
    """Raised when a provider rate limit is reached."""


@dataclass
class FlightLookupResult:
    """Normalized flight data returned by any provider."""

    flight_number: str
    airline_code: str
    airline_name: Optional[str] = None

    departure_city: str = ""
    arrival_city: str = ""
    departure_airport: str = ""
    arrival_airport: str = ""
    departure_terminal: Optional[str] = None
    arrival_terminal: Optional[str] = None

    scheduled_departure_at: Optional[datetime] = None
    actual_departure_at: Optional[datetime] = None
    estimated_departure_at: Optional[datetime] = None
    scheduled_arrival_at: Optional[datetime] = None
    actual_arrival_at: Optional[datetime] = None
    estimated_arrival_at: Optional[datetime] = None

    status: str = "scheduled"

    check_in_counter: Optional[str] = None
    gate: Optional[str] = None
    baggage_belt: Optional[str] = None

    raw: dict = field(default_factory=dict)  # original provider response


class BaseFlightProvider(ABC):
    """Interface for flight data providers.

    Implementations:
      - MockFlightProvider (dev/demo)
      - AviationstackProvider (future)
      - CiriumProvider (future)
      - FlightAwareProvider (future)
      - AeroDataBoxProvider (future)
    """

    @abstractmethod
    async def lookup(self, flight_number: str, date: datetime) -> Optional[FlightLookupResult]:
        """Look up a flight by number and date. Returns None if not found."""
        ...

    @abstractmethod
    async def get_status(self, flight_number: str, date: datetime) -> Optional[FlightLookupResult]:
        """Get current status of a flight. Returns None if not found."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for logging."""
        ...
