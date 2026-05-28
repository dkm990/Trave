from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.trip import TripMember
from app.services.currency_service import CurrencyService
from app.services.trip_service import TripService

ISO_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass
class PaymentInput:
    trip_id: int
    from_user_id: int
    to_user_id: int
    amount: Decimal
    currency: str
    note: str | None = None


class PaymentService:
    def __init__(self, session: AsyncSession, currency: CurrencyService) -> None:
        self.session = session
        self.currency = currency

    async def get_payment(self, payment_id: int) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def list_payments(self, trip_id: int, *, include_canceled: bool = False) -> list[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.trip_id == trip_id)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
        )
        if not include_canceled:
            stmt = stmt.where(Payment.status == "active")
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_payment(self, payload: PaymentInput) -> Payment:
        if payload.from_user_id == payload.to_user_id:
            raise ValueError("from_user_id and to_user_id must be different")
        if payload.amount <= 0:
            raise ValueError("amount must be > 0")

        currency = (payload.currency or "").strip().upper()
        if not ISO_CURRENCY_RE.match(currency):
            raise ValueError("currency must be ISO 3-letter code")

        trip = await TripService(self.session).get_trip(payload.trip_id)
        if not trip:
            raise ValueError("trip not found")

        members = await self._member_ids(payload.trip_id)
        if payload.from_user_id not in members or payload.to_user_id not in members:
            raise ValueError("both users must be trip members")

        converted, rate_info = await self.currency.convert(payload.amount, currency, trip.trip_currency)
        amount_base = Decimal(converted).quantize(Decimal("0.01"))

        payment = Payment(
            trip_id=payload.trip_id,
            from_user_id=payload.from_user_id,
            to_user_id=payload.to_user_id,
            amount_original=payload.amount,
            currency_original=currency,
            amount_base=amount_base,
            base_currency=trip.trip_currency,
            exchange_rate=rate_info.rate,
            exchange_rate_date=getattr(rate_info, "rate_date", None),
            note=payload.note,
            status="active",
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def cancel_payment(self, payment_id: int) -> Payment:
        payment = await self.get_payment(payment_id)
        if not payment:
            raise ValueError("payment not found")
        if payment.status == "canceled":
            return payment
        payment.status = "canceled"
        payment.canceled_at = datetime.utcnow()
        payment.updated_at = datetime.utcnow()
        await self.session.flush()
        return payment

    async def _member_ids(self, trip_id: int) -> set[int]:
        rows = (
            await self.session.execute(
                select(TripMember.user_id).where(TripMember.trip_id == trip_id)
            )
        ).all()
        return {int(r[0]) for r in rows}
