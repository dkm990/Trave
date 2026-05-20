from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from app.api import currency as currency_api
from app.models.currency import ExchangeRateCache
from app.services.currency_service import CurrencyService
from app.services.providers.base import CurrencyProvider, RateResult


class _FixedProvider(CurrencyProvider):
    name = "exchangerate_open"

    async def get_rate(self, base: str, quote: str) -> RateResult:
        return RateResult(
            base=base.upper(),
            quote=quote.upper(),
            rate=Decimal("0.0140"),
            rate_date=date(2026, 5, 20),
            provider=self.name,
        )


@pytest.fixture
async def session():
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
async def test_convert_endpoint_no_500_on_cache_conflict(session, monkeypatch):
    # Preseed same unique key to trigger conflict path during insert.
    session.add(
        ExchangeRateCache(
            base_currency="RUB",
            quote_currency="USD",
            rate=Decimal("0.0140"),
            rate_date=date(2026, 5, 20),
            provider="exchangerate_open",
        )
    )
    await session.commit()

    class _Service(CurrencyService):
        def __init__(self, s):
            super().__init__(session=s, providers=[_FixedProvider()])
            self.settings.currency_cache_ttl_hours = -1  # bypass fresh cache

    monkeypatch.setattr(currency_api, "CurrencyService", _Service)

    out = await currency_api.convert(
        amount=Decimal("100"),
        base="RUB",
        quote="USD",
        session=session,
    )

    assert out.quote == "USD"
    assert out.base == "RUB"
    assert out.rate.provider == "exchangerate_open"
    assert out.converted == Decimal("1.4000")
