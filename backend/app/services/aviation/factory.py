"""Factory for aviation providers."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.services.aviation.aerodatabox import AeroDataBoxProvider
from app.services.aviation.base import BaseFlightProvider
from app.services.aviation.mock import MockFlightProvider

logger = logging.getLogger("uvicorn.error")


def get_flight_provider() -> BaseFlightProvider:
    settings = get_settings()
    provider = settings.flight_provider.strip().lower()
    logger.info("Flight provider: %s", provider)
    if provider == "aerodatabox":
        return AeroDataBoxProvider(
            api_key=settings.aerodatabox_api_key,
            api_host=settings.aerodatabox_api_host,
            cache_ttl_seconds=settings.flight_provider_cache_ttl_seconds,
        )
    return MockFlightProvider()
