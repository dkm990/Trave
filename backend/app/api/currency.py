from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.schemas.common import CurrencyConvertOut, CurrencyRateOut
from app.services.currency_service import CurrencyError, CurrencyService

router = APIRouter(prefix="/api/currency", tags=["currency"])


@router.get("/rate", response_model=CurrencyRateOut)
async def get_rate(
    base: str = Query(min_length=3, max_length=8),
    quote: str = Query(min_length=3, max_length=8),
    session: AsyncSession = Depends(db_session),
):
    svc = CurrencyService(session)
    try:
        info = await svc.get_rate(base, quote)
    except CurrencyError as exc:
        raise HTTPException(503, str(exc)) from exc
    return CurrencyRateOut(
        base=info.base,
        quote=info.quote,
        rate=info.rate,
        rate_date=info.rate_date,
        provider=info.provider,
        fetched_at=info.fetched_at,
        from_cache=info.from_cache,
    )


@router.get("/convert", response_model=CurrencyConvertOut)
async def convert(
    amount: Decimal = Query(gt=0),
    base: str = Query(min_length=3, max_length=8),
    quote: str = Query(min_length=3, max_length=8),
    session: AsyncSession = Depends(db_session),
):
    svc = CurrencyService(session)
    try:
        converted, info = await svc.convert(amount, base, quote)
    except CurrencyError as exc:
        raise HTTPException(503, str(exc)) from exc
    return CurrencyConvertOut(
        amount=amount,
        base=info.base,
        quote=info.quote,
        converted=converted,
        rate=CurrencyRateOut(
            base=info.base,
            quote=info.quote,
            rate=info.rate,
            rate_date=info.rate_date,
            provider=info.provider,
            fetched_at=info.fetched_at,
            from_cache=info.from_cache,
        ),
    )


@router.get("/trip/{trip_id}/quick")
async def quick_currencies(
    trip_id: int,
    session: AsyncSession = Depends(db_session),
):
    """Возвращает рекомендованные валюты для quick-bar в Mini App конвертере."""
    from app.services.trip_service import TripService

    trip = await TripService(session).get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    quick = []
    seen: set[str] = set()
    for c in (trip.local_currency, trip.default_currency, "USD", "EUR", "TRY", "RUB"):
        if c and c not in seen:
            seen.add(c)
            quick.append(c)
    return {"currencies": quick}
