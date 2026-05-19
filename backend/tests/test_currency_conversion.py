"""Smoke tests for CurrencyService cache + same-currency shortcut.

Provider-chain тесты живут в test_currency_providers.py.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.services.currency_service import CurrencyService
from app.services.providers.base import (
    CurrencyProvider,
    ProviderUnsupportedPair,
    RateResult,
)


class _OneShotProvider(CurrencyProvider):
    """Возвращает фиксированный курс ровно один раз; на всех последующих
    вызовах считает их (для assert calls == 1)."""

    name = "test_oneshot"

    def __init__(self, base: str, quote: str, rate: str):
        self.base = base.upper()
        self.quote = quote.upper()
        self.rate = Decimal(rate)
        self.calls = 0

    async def get_rate(self, base: str, quote: str) -> RateResult:
        self.calls += 1
        if (base.upper(), quote.upper()) != (self.base, self.quote):
            raise ProviderUnsupportedPair("not configured")
        return RateResult(
            base=self.base,
            quote=self.quote,
            rate=self.rate,
            rate_date=date(2025, 1, 1),
            provider=self.name,
        )


@pytest.mark.asyncio
async def test_convert_same_currency():
    svc = CurrencyService(session=None, providers=[])
    info = await svc.get_rate("USD", "USD")
    assert info.rate == Decimal("1")
    assert info.base == info.quote
    assert info.from_cache is True


@pytest.mark.asyncio
async def test_convert_caches_first_call():
    """Первый вызов идёт в провайдер, второй — из fresh cache."""
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
    async with factory() as session:
        provider = _OneShotProvider("USD", "RUB", "90.0")
        svc = CurrencyService(session=session, providers=[provider])

        info = await svc.get_rate("USD", "RUB")
        await session.commit()
        assert info.rate == Decimal("90.0")
        assert info.from_cache is False
        assert provider.calls == 1

        info2 = await svc.get_rate("USD", "RUB")
        assert info2.from_cache is True
        assert provider.calls == 1
