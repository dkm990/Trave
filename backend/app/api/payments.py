from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.models.user import User
from app.schemas.common import PaymentCreateRequest, PaymentOut
from app.services.currency_service import CurrencyService
from app.services.payment_service import PaymentInput, PaymentService
from app.services.trip_service import TripService

router = APIRouter(prefix="/api/trips", tags=["payments"])


@router.post("/{trip_id}/payments", response_model=PaymentOut)
async def create_payment(
    trip_id: int,
    payload: PaymentCreateRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    if not await TripService(session).get_trip(trip_id):
        raise HTTPException(404, "Trip not found")
    svc = PaymentService(session, CurrencyService(session))
    try:
        payment = await svc.create_payment(
            PaymentInput(
                trip_id=trip_id,
                from_user_id=payload.from_user_id,
                to_user_id=payload.to_user_id,
                amount=payload.amount,
                currency=payload.currency,
                note=payload.note,
            )
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return payment


@router.get("/{trip_id}/payments", response_model=list[PaymentOut])
async def list_payments(
    trip_id: int,
    include_canceled: bool = Query(default=False),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    if not await TripService(session).get_trip(trip_id):
        raise HTTPException(404, "Trip not found")
    svc = PaymentService(session, CurrencyService(session))
    return await svc.list_payments(trip_id, include_canceled=include_canceled)


@router.patch("/{trip_id}/payments/{payment_id}/cancel", response_model=PaymentOut)
async def cancel_payment(
    trip_id: int,
    payment_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(db_session),
):
    if not await TripService(session).get_trip(trip_id):
        raise HTTPException(404, "Trip not found")
    svc = PaymentService(session, CurrencyService(session))
    payment = await svc.get_payment(payment_id)
    if not payment or payment.trip_id != trip_id:
        raise HTTPException(404, "Payment not found")
    try:
        return await svc.cancel_payment(payment_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
