from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.currency import ExchangeRateCache
from app.services.providers import (
    CurrencyProvider,
    ExchangeRateOpenProvider,
    FrankfurterProvider,
    ProviderError,
    ProviderUnsupportedPair,
)

logger = logging.getLogger(__name__)


class CurrencyError(Exception):
    """Курс валют недоступен и нет даже устаревшего кеша."""


@dataclass
class RateInfo:
    base: str
    quote: str
    rate: Decimal
    rate_date: date
    provider: str
    fetched_at: datetime
    from_cache: bool


class CurrencyService:
    """Получение курсов валют через chain провайдеров + локальный кеш в БД.

    Order of resolution:
      1. fresh cache (TTL not exceeded)
      2. providers in order (Frankfurter -> ExchangeRate-Open by default)
      3. stale cache (any age) — last resort
      4. CurrencyError
    """

    def __init__(
        self,
        session: AsyncSession,
        http_client: Optional[httpx.AsyncClient] = None,
        providers: Optional[Sequence[CurrencyProvider]] = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self._owns_client = http_client is None
        self._http = http_client
        if providers is None:
            client = http_client
            self.providers: list[CurrencyProvider] = [
                FrankfurterProvider(http_client=client),
                ExchangeRateOpenProvider(http_client=client),
            ]
        else:
            self.providers = list(providers)

    async def get_rate(self, base: str, quote: str) -> RateInfo:
        base = base.upper()
        quote = quote.upper()
        if base == quote:
            today = date.today()
            return RateInfo(
                base, quote, Decimal("1"), today, "self",
                datetime.now(timezone.utc), True,
            )

        cached = await self._get_fresh_cache(base, quote)
        if cached is not None:
            return self._cache_to_info(cached, from_cache=True)

        last_error: Optional[Exception] = None
        for provider in self.providers:
            if provider.name == "frankfurter" and ("RUB" in (base, quote)):
                logger.info("Skipping frankfurter for %s->%s (RUB not supported)", base, quote)
                continue
            try:
                result = await provider.get_rate(base, quote)
            except ProviderUnsupportedPair as exc:
                logger.info("%s unsupported %s->%s: %s", provider.name, base, quote, exc)
                last_error = exc
                continue
            except ProviderError as exc:
                logger.warning("%s failed for %s->%s: %s", provider.name, base, quote, exc)
                last_error = exc
                continue

            cache, from_cache = await self._upsert_cache_row(
                base=result.base,
                quote=result.quote,
                rate=result.rate,
                rate_date=result.rate_date,
                provider=result.provider,
            )
            return RateInfo(
                base=result.base,
                quote=result.quote,
                rate=cache.rate,
                rate_date=cache.rate_date,
                provider=cache.provider,
                fetched_at=cache.fetched_at or datetime.now(timezone.utc),
                from_cache=from_cache,
            )

        stale = await self._get_any_cache(base, quote)
        if stale is not None:
            return self._cache_to_info(stale, from_cache=True)

        raise CurrencyError(
            f"Не удалось получить курс {base}->{quote}: {last_error or 'no providers configured'}"
        )

    async def convert(self, amount: Decimal, base: str, quote: str) -> tuple[Decimal, RateInfo]:
        info = await self.get_rate(base, quote)
        return (amount * info.rate).quantize(Decimal("0.0001")), info

    @staticmethod
    def _cache_to_info(row: ExchangeRateCache, *, from_cache: bool) -> RateInfo:
        return RateInfo(
            base=row.base_currency,
            quote=row.quote_currency,
            rate=row.rate,
            rate_date=row.rate_date,
            provider=row.provider,
            fetched_at=row.fetched_at,
            from_cache=from_cache,
        )

    async def _get_fresh_cache(self, base: str, quote: str) -> ExchangeRateCache | None:
        ttl = timedelta(hours=self.settings.currency_cache_ttl_hours)
        cutoff = datetime.now(timezone.utc) - ttl
        stmt = (
            select(ExchangeRateCache)
            .where(
                ExchangeRateCache.base_currency == base,
                ExchangeRateCache.quote_currency == quote,
                ExchangeRateCache.fetched_at >= cutoff.replace(tzinfo=None),
            )
            .order_by(ExchangeRateCache.fetched_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _get_any_cache(self, base: str, quote: str) -> ExchangeRateCache | None:
        stmt = (
            select(ExchangeRateCache)
            .where(
                ExchangeRateCache.base_currency == base,
                ExchangeRateCache.quote_currency == quote,
            )
            .order_by(ExchangeRateCache.fetched_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _get_cache_by_key(
        self,
        *,
        base: str,
        quote: str,
        rate_date: date,
        provider: str,
    ) -> ExchangeRateCache | None:
        stmt = (
            select(ExchangeRateCache)
            .where(
                ExchangeRateCache.base_currency == base,
                ExchangeRateCache.quote_currency == quote,
                ExchangeRateCache.rate_date == rate_date,
                ExchangeRateCache.provider == provider,
            )
            .order_by(ExchangeRateCache.fetched_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _upsert_cache_row(
        self,
        *,
        base: str,
        quote: str,
        rate: Decimal,
        rate_date: date,
        provider: str,
    ) -> tuple[ExchangeRateCache, bool]:
        try:
            async with self.session.begin_nested():
                cache = ExchangeRateCache(
                    base_currency=base,
                    quote_currency=quote,
                    rate=rate,
                    rate_date=rate_date,
                    provider=provider,
                )
                self.session.add(cache)
                await self.session.flush()
            return cache, False
        except IntegrityError:
            logger.info(
                "Currency cache conflict for %s->%s %s %s; using existing row",
                base,
                quote,
                rate_date,
                provider,
            )
            existing = await self._get_cache_by_key(
                base=base,
                quote=quote,
                rate_date=rate_date,
                provider=provider,
            )
            if existing is not None:
                return existing, True
            raise CurrencyError(f"Currency cache conflict for {base}->{quote}") from None

    async def aclose(self) -> None:
        for p in self.providers:
            try:
                await p.aclose()
            except Exception:  # noqa: BLE001
                continue
        if self._owns_client and self._http is not None:
            await self._http.aclose()
            self._http = None
