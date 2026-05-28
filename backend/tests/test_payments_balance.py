from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.services.balance_service import BalanceService, simplify_debts
from app.services.expense_service import ExpenseInput, ExpenseService
from app.services.payment_service import PaymentInput, PaymentService
from app.services.trip_service import TripService


@dataclass
class _RateInfo:
    rate: Decimal
    rate_date: date


class _StubCurrency:
    async def convert(self, amount: Decimal, base: str, quote: str):
        b = base.upper()
        q = quote.upper()
        if b == q:
            return amount, _RateInfo(Decimal("1"), date.today())
        if b == "RUB" and q == "TRY":
            rate = Decimal("0.6379")
            return (amount * rate), _RateInfo(rate, date.today())
        rate = Decimal("2.0000")
        return (amount * rate), _RateInfo(rate, date.today())


@pytest.mark.asyncio
async def test_payment_reduces_debt_in_balance():
    from app.database import Base, get_engine, get_session_factory
    from app.models.trip import TripMember
    from app.models.user import User

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        creditor = User(telegram_user_id=100, first_name="Дык", last_name="Ань")
        debtor = User(telegram_user_id=200, first_name="Zoe", last_name="Ramirez")
        session.add_all([creditor, debtor])
        await session.flush()

        trip = await TripService(session).create_trip("Istanbul", creditor, trip_currency="TRY")
        session.add(TripMember(trip_id=trip.id, user_id=debtor.id, display_name="Zoe Ramirez"))
        await session.flush()

        currency = _StubCurrency()
        expense_svc = ExpenseService(session, currency)
        await expense_svc.add_expense(
            ExpenseInput(
                trip_id=trip.id,
                payer_user_id=creditor.id,
                title="Taxi",
                amount=Decimal("500"),
                currency="TRY",
                participant_user_ids=[creditor.id, debtor.id],
            )
        )

        balance_svc = BalanceService(session)
        before = await balance_svc.calculate_balances(trip.id)
        by_id = {b.user_id: b for b in before}
        assert by_id[debtor.id].net == Decimal("-250.00")
        assert by_id[creditor.id].net == Decimal("250.00")

        pay_svc = PaymentService(session, currency)
        await pay_svc.create_payment(
            PaymentInput(
                trip_id=trip.id,
                from_user_id=debtor.id,
                to_user_id=creditor.id,
                amount=Decimal("100"),
                currency="TRY",
                note="cash",
            )
        )

        after = await balance_svc.calculate_balances(trip.id)
        by_id = {b.user_id: b for b in after}
        assert by_id[debtor.id].net == Decimal("-150.00")
        assert by_id[creditor.id].net == Decimal("150.00")
        transfers = simplify_debts(after)
        assert len(transfers) == 1
        assert transfers[0].from_user_id == debtor.id
        assert transfers[0].to_user_id == creditor.id
        assert transfers[0].amount == Decimal("150.00")


@pytest.mark.asyncio
async def test_payment_other_currency_stores_base():
    from app.database import Base, get_engine, get_session_factory
    from app.models.trip import TripMember
    from app.models.user import User

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        creditor = User(telegram_user_id=101, first_name="A", last_name="B")
        debtor = User(telegram_user_id=201, first_name="C", last_name="D")
        session.add_all([creditor, debtor])
        await session.flush()

        trip = await TripService(session).create_trip("Istanbul", creditor, trip_currency="TRY")
        session.add(TripMember(trip_id=trip.id, user_id=debtor.id))
        await session.flush()

        svc = PaymentService(session, _StubCurrency())
        payment = await svc.create_payment(
            PaymentInput(
                trip_id=trip.id,
                from_user_id=debtor.id,
                to_user_id=creditor.id,
                amount=Decimal("100"),
                currency="RUB",
            )
        )
        assert payment.currency_original == "RUB"
        assert payment.base_currency == "TRY"
        assert payment.amount_base == Decimal("63.79")


@pytest.mark.asyncio
async def test_canceled_payment_not_affect_balance():
    from app.database import Base, get_engine, get_session_factory
    from app.models.trip import TripMember
    from app.models.user import User

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        creditor = User(telegram_user_id=102, first_name="E", last_name="F")
        debtor = User(telegram_user_id=202, first_name="G", last_name="H")
        session.add_all([creditor, debtor])
        await session.flush()

        trip = await TripService(session).create_trip("Istanbul", creditor, trip_currency="TRY")
        session.add(TripMember(trip_id=trip.id, user_id=debtor.id))
        await session.flush()

        currency = _StubCurrency()
        expense_svc = ExpenseService(session, currency)
        await expense_svc.add_expense(
            ExpenseInput(
                trip_id=trip.id,
                payer_user_id=creditor.id,
                title="Taxi",
                amount=Decimal("500"),
                currency="TRY",
                participant_user_ids=[creditor.id, debtor.id],
            )
        )

        pay_svc = PaymentService(session, currency)
        p = await pay_svc.create_payment(
            PaymentInput(
                trip_id=trip.id,
                from_user_id=debtor.id,
                to_user_id=creditor.id,
                amount=Decimal("100"),
                currency="TRY",
            )
        )
        await pay_svc.cancel_payment(p.id)

        balances = await BalanceService(session).calculate_balances(trip.id)
        by_id = {b.user_id: b for b in balances}
        assert by_id[debtor.id].net == Decimal("-250.00")
        assert by_id[creditor.id].net == Decimal("250.00")


@pytest.mark.asyncio
async def test_payment_validations():
    from app.database import Base, get_engine, get_session_factory
    from app.models.trip import TripMember
    from app.models.user import User

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        creditor = User(telegram_user_id=103, first_name="I", last_name="J")
        debtor = User(telegram_user_id=203, first_name="K", last_name="L")
        session.add_all([creditor, debtor])
        await session.flush()

        trip = await TripService(session).create_trip("Istanbul", creditor, trip_currency="TRY")
        session.add(TripMember(trip_id=trip.id, user_id=debtor.id))
        await session.flush()

        svc = PaymentService(session, _StubCurrency())

        with pytest.raises(ValueError, match="different"):
            await svc.create_payment(
                PaymentInput(trip_id=trip.id, from_user_id=debtor.id, to_user_id=debtor.id, amount=Decimal("10"), currency="TRY")
            )

        with pytest.raises(ValueError, match="ISO"):
            await svc.create_payment(
                PaymentInput(trip_id=trip.id, from_user_id=debtor.id, to_user_id=creditor.id, amount=Decimal("10"), currency="T1")
            )

        outsider = User(telegram_user_id=300, first_name="Out")
        session.add(outsider)
        await session.flush()
        with pytest.raises(ValueError, match="member"):
            await svc.create_payment(
                PaymentInput(trip_id=trip.id, from_user_id=outsider.id, to_user_id=creditor.id, amount=Decimal("10"), currency="TRY")
            )


@pytest.mark.asyncio
async def test_payment_list_and_cancel():
    from app.database import Base, get_engine, get_session_factory
    from app.models.trip import TripMember
    from app.models.user import User

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        creditor = User(telegram_user_id=104, first_name="M", last_name="N")
        debtor = User(telegram_user_id=204, first_name="O", last_name="P")
        session.add_all([creditor, debtor])
        await session.flush()

        trip = await TripService(session).create_trip("Istanbul", creditor, trip_currency="TRY")
        session.add(TripMember(trip_id=trip.id, user_id=debtor.id))
        await session.flush()

        svc = PaymentService(session, _StubCurrency())
        p1 = await svc.create_payment(
            PaymentInput(trip_id=trip.id, from_user_id=debtor.id, to_user_id=creditor.id, amount=Decimal("50"), currency="TRY")
        )
        p2 = await svc.create_payment(
            PaymentInput(trip_id=trip.id, from_user_id=debtor.id, to_user_id=creditor.id, amount=Decimal("30"), currency="TRY")
        )

        active = await svc.list_payments(trip.id)
        assert len(active) == 2

        await svc.cancel_payment(p1.id)
        active_after = await svc.list_payments(trip.id)
        assert len(active_after) == 1
        assert active_after[0].id == p2.id

        all_payments = await svc.list_payments(trip.id, include_canceled=True)
        assert len(all_payments) == 2
