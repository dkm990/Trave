"""Aviation data providers.

Clean adapter layer. UI only depends on `BaseFlightProvider` interface.
To add a new provider, subclass `BaseFlightProvider` and wire it in.
"""

from app.services.aviation.base import BaseFlightProvider, FlightLookupResult
from app.services.aviation.mock import MockFlightProvider

__all__ = [
    "BaseFlightProvider",
    "FlightLookupResult",
    "MockFlightProvider",
]
