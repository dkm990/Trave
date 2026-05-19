"""Aviation data providers.

Clean adapter layer. UI only depends on `BaseFlightProvider` interface.
To add a new provider, subclass `BaseFlightProvider` and wire it in.
"""

from app.services.aviation.base import BaseFlightProvider, FlightLookupResult, ProviderConfigurationError, ProviderRateLimitError
from app.services.aviation.aerodatabox import AeroDataBoxProvider
from app.services.aviation.factory import get_flight_provider
from app.services.aviation.mock import MockFlightProvider

__all__ = [
    "BaseFlightProvider",
    "FlightLookupResult",
    "ProviderConfigurationError",
    "ProviderRateLimitError",
    "AeroDataBoxProvider",
    "get_flight_provider",
    "MockFlightProvider",
]
