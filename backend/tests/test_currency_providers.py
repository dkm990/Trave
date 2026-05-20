"""Tests for currency provider chain (Frankfurter primary, ExchangeRate-Open fallback)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.services.currency_service import CurrencyError, CurrencyService
from app.services.providers.base import (
    CurrencyProvider,
    ProviderError,
    ProviderUnsupportedPair,
    RateResult,
)
from app.models.currency import ExchangeRateCache


class FakeProvider(CurrencyProvider):
    """Простой fake-провайдер для unit-tests без сетевых запросов."""

    def __init__(self, name: str, *, rates: dict | None = None,
                 unsupported: bool = False, fail: bool = False):
        self.name = name
        self.rates = rates or {}
        self.unsupported = unsupported
        self.fail = fail
        self.calls = 0

    async def get_rate(self, base: str, quote: str) -> RateResult:
        self.calls += 1
        if self.unsupported:
            raise ProviderUnsupportedPair(f"{self.name} unsupported {base}->{quote}")
        if self.fail:
            raise ProviderError(f"{self.name} transport failure")
        key = (base.upper(), quote.upper())
        if key not in self.rates:
            raise ProviderUnsupportedPair(f"{self.name} no rate for {key}")
        return RateResult(
            base=base.upper(),
            quote=quote.upper(),
            rate=Decimal(str(self.rates[key])),
            rate_date=date(2025, 1, 1),
            provider=self.name,
        )


@pytest.fixture
async def session():
    """Изолированная in-memory sqlite сессия с чистым engine на каждый тест."""
    import os

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    from app.config import reload_settings
    import app.database as db
    from app.database import init_db

    reload_settings()
    db._engine = None  # noqa: SLF001
    db._session_factory = None  # noqa: SLF001
    await init_db()
    factory = db.get_session_factory()
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_primary_success_skips_fallback(session):
    primary = FakeProvider("primary", rates={("USD", "RUB"): "90.0"})
    fallback = FakeProvider("fallback", rates={("USD", "RUB"): "999.0"})
    svc = CurrencyService(session=session, providers=[primary, fallback])

    info = await svc.get_rate("USD", "RUB")
    await session.commit()

    assert info.provider == "primary"
    assert info.rate == Decimal("90.0")
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_primary_unsupported_uses_fallback(session):
    primary = FakeProvider("primary", unsupported=True)
    fallback = FakeProvider("fallback", rates={("USD", "VND"): "25000.0"})
    svc = CurrencyService(session=session, providers=[primary, fallback])

    info = await svc.get_rate("USD", "VND")
    await session.commit()

    assert info.provider == "fallback"
    assert info.rate == Decimal("25000.0")
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_primary_transport_failure_uses_fallback(session):
    primary = FakeProvider("primary", fail=True)
    fallback = FakeProvider("fallback", rates={("USD", "EUR"): "0.92"})
    svc = CurrencyService(session=session, providers=[primary, fallback])

    info = await svc.get_rate("USD", "EUR")
    await session.commit()

    assert info.provider == "fallback"
    assert info.rate == Decimal("0.92")


@pytest.mark.asyncio
async def test_both_fail_uses_stale_cache(session):
    primary = FakeProvider("primary", rates={("USD", "KZT"): "470.0"})
    svc = CurrencyService(session=session, providers=[primary])
    await svc.get_rate("USD", "KZT")
    await session.commit()

    p1 = FakeProvider("primary", fail=True)
    p2 = FakeProvider("fallback", fail=True)
    svc2 = CurrencyService(session=session, providers=[p1, p2])
    svc2.settings.currency_cache_ttl_hours = 0
    info = await svc2.get_rate("USD", "KZT")
    assert info.from_cache is True
    assert info.rate == Decimal("470.0")
    assert info.provider == "primary"


@pytest.mark.asyncio
async def test_both_fail_no_cache_raises_currency_error(session):
    p1 = FakeProvider("primary", fail=True)
    p2 = FakeProvider("fallback", fail=True)
    svc = CurrencyService(session=session, providers=[p1, p2])

    with pytest.raises(CurrencyError):
        await svc.get_rate("USD", "AMD")


@pytest.mark.asyncio
async def test_vnd_through_fallback(session):
    primary = FakeProvider("frankfurter", unsupported=True)
    fallback = FakeProvider("exchangerate_open", rates={("RUB", "VND"): "295.0"})
    svc = CurrencyService(session=session, providers=[primary, fallback])

    info = await svc.get_rate("RUB", "VND")
    await session.commit()
    assert info.provider == "exchangerate_open"
    assert info.rate == Decimal("295.0")


@pytest.mark.asyncio
async def test_fallback_caches_with_provider_name(session):
    primary = FakeProvider("frankfurter", unsupported=True)
    fallback = FakeProvider("exchangerate_open", rates={("USD", "VND"): "25000.0"})
    svc = CurrencyService(session=session, providers=[primary, fallback])
    info = await svc.get_rate("USD", "VND")
    await session.commit()
    assert info.from_cache is False

    fallback.calls = 0
    info2 = await svc.get_rate("USD", "VND")
    assert info2.from_cache is True
    assert info2.provider == "exchangerate_open"
    assert fallback.calls == 0


@pytest.mark.parametrize("currency", ["KZT", "AMD", "UAH", "BYN"])
@pytest.mark.asyncio
async def test_travel_currencies_supported_through_fallback(session, currency):
    primary = FakeProvider("frankfurter", unsupported=True)
    fallback = FakeProvider(
        "exchangerate_open", rates={("USD", currency): "100.0"}
    )
    svc = CurrencyService(session=session, providers=[primary, fallback])
    info = await svc.get_rate("USD", currency)
    await session.commit()
    assert info.provider == "exchangerate_open"
    assert info.quote == currency


@pytest.mark.asyncio
async def test_rub_pair_skips_frankfurter_provider(session):
    frankfurter = FakeProvider("frankfurter", rates={("RUB", "USD"): "0.013"})
    fallback = FakeProvider("exchangerate_open", rates={("RUB", "USD"): "0.014"})
    svc = CurrencyService(session=session, providers=[frankfurter, fallback])

    info = await svc.get_rate("RUB", "USD")
    await session.commit()

    assert frankfurter.calls == 0
    assert fallback.calls == 1
    assert info.provider == "exchangerate_open"


@pytest.mark.asyncio
async def test_unique_cache_conflict_returns_existing_row_without_crash(session):
    # Existing row already in cache for the same unique key.
    existing = ExchangeRateCache(
        base_currency="RUB",
        quote_currency="USD",
        rate=Decimal("0.0140"),
        rate_date=date(2026, 5, 20),
        provider="exchangerate_open",
    )
    session.add(existing)
    await session.commit()

    provider = FakeProvider("exchangerate_open", rates={("RUB", "USD"): "0.0140"})
    svc = CurrencyService(session=session, providers=[provider])
    svc.settings.currency_cache_ttl_hours = -1  # force provider path, skip fresh cache

    info = await svc.get_rate("RUB", "USD")
    await session.commit()

    rows = (
        await session.execute(
            select(ExchangeRateCache).where(
                ExchangeRateCache.base_currency == "RUB",
                ExchangeRateCache.quote_currency == "USD",
                ExchangeRateCache.rate_date == date(2026, 5, 20),
                ExchangeRateCache.provider == "exchangerate_open",
            )
        )
    ).scalars().all()

    assert len(rows) == 1
    assert info.rate == Decimal("0.0140")
    assert info.provider == "exchangerate_open"
