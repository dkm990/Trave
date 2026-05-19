"""Tests for ExpenseService edit/cancel/analytics + filters."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.services.expense_service import (
    ExpenseEditInput,
    ExpenseFilters,
    ExpenseInput,
    ExpenseService,
)


class _StubCurrencyInfo:
    def __init__(self, rate: Decimal):
        self.rate = rate


class _StubCurrencyService:
    """Без сетевых вызовов; возвращает заданный курс."""

    def __init__(self, rate: Decimal = Decimal("1")):
        self.rate = rate

    async def convert(self, amount: Decimal, base: str, quote: str):
        if base.upper() == quote.upper():
            return amount, _StubCurrencyInfo(Decimal("1"))
        return amount * self.rate, _StubCurrencyInfo(self.rate)


@pytest.fixture
async def trip_session():
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["APP_TIMEZONE"] = "Europe/Istanbul"
    from app.config import reload_settings
    import app.database as db
    from app.database import init_db
    from app.models.trip import Trip, TripMember
    from app.models.user import User

    reload_settings()
    db._engine = None  # noqa: SLF001
    db._session_factory = None  # noqa: SLF001
    await init_db()
    factory = db.get_session_factory()
    async with factory() as session:
        u1 = User(telegram_user_id=1, first_name="Alice")
        u2 = User(telegram_user_id=2, first_name="Bob")
        u3 = User(telegram_user_id=3, first_name="Carl")
        session.add_all([u1, u2, u3])
        await session.flush()
        trip = Trip(title="Test", default_currency="RUB", created_by_user_id=u1.id)
        session.add(trip)
        await session.flush()
        for u in (u1, u2, u3):
            session.add(
                TripMember(trip_id=trip.id, user_id=u.id, display_name=u.first_name)
            )
        await session.flush()
        yield session, trip, u1, u2, u3


@pytest.mark.asyncio
async def test_edit_amount_recalculates_base(trip_session):
    session, trip, u1, u2, u3 = trip_session
    svc = ExpenseService(session, _StubCurrencyService(Decimal("2")))
    expense = await svc.add_expense(
        ExpenseInput(
            trip_id=trip.id, payer_user_id=u1.id, title="ужин",
            amount=Decimal("100"), currency="USD",
            participant_user_ids=[u1.id, u2.id], category="food",
        )
    )
    assert expense.amount_base == Decimal("200.00")

    edited = await svc.edit_expense(expense.id, ExpenseEditInput(amount=Decimal("50")))
    assert edited.amount_original == Decimal("50")
    assert edited.amount_base == Decimal("100.00")
    assert edited.edited_count == 1


@pytest.mark.asyncio
async def test_edit_participants_recalculates_shares(trip_session):
    session, trip, u1, u2, u3 = trip_session
    svc = ExpenseService(session, _StubCurrencyService(Decimal("1")))
    expense = await svc.add_expense(
        ExpenseInput(
            trip_id=trip.id, payer_user_id=u1.id, title="t",
            amount=Decimal("300"), currency="RUB",
            participant_user_ids=[u1.id, u2.id], category="food",
        )
    )
    assert len(expense.shares) == 2

    edited = await svc.edit_expense(
        expense.id, ExpenseEditInput(participant_user_ids=[u1.id, u2.id, u3.id])
    )
    assert len(edited.shares) == 3
    assert sum(Decimal(s.share_amount_base) for s in edited.shares) == Decimal("300.00")


@pytest.mark.asyncio
async def test_cancel_expense_excludes_from_balance(trip_session):
    session, trip, u1, u2, u3 = trip_session
    from app.services.balance_service import BalanceService

    svc = ExpenseService(session, _StubCurrencyService(Decimal("1")))
    e = await svc.add_expense(
        ExpenseInput(
            trip_id=trip.id, payer_user_id=u1.id, title="t",
            amount=Decimal("300"), currency="RUB",
            participant_user_ids=[u1.id, u2.id, u3.id], category="food",
        )
    )
    await session.commit()

    balances = await BalanceService(session).calculate_balances(trip.id)
    by_user = {b.user_id: b for b in balances}
    assert by_user[u1.id].net == Decimal("200.00")

    await svc.cancel_expense(e.id)
    await session.commit()

    balances2 = await BalanceService(session).calculate_balances(trip.id)
    assert all(b.net == Decimal("0.00") for b in balances2)


@pytest.mark.asyncio
async def test_filter_by_payer(trip_session):
    session, trip, u1, u2, u3 = trip_session
    svc = ExpenseService(session, _StubCurrencyService(Decimal("1")))
    await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u1.id, title="a",
        amount=Decimal("100"), currency="RUB",
        participant_user_ids=[u1.id], category="food",
    ))
    await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u2.id, title="b",
        amount=Decimal("200"), currency="RUB",
        participant_user_ids=[u2.id], category="taxi",
    ))
    await session.commit()

    rows = await svc.list_filtered(trip.id, ExpenseFilters(payer_id=u1.id))
    assert len(rows) == 1
    assert rows[0].title == "a"


@pytest.mark.asyncio
async def test_filter_excludes_canceled_by_default(trip_session):
    session, trip, u1, u2, u3 = trip_session
    svc = ExpenseService(session, _StubCurrencyService(Decimal("1")))

    await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u1.id, title="a",
        amount=Decimal("100"), currency="RUB",
        participant_user_ids=[u1.id],
    ))
    e2 = await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u1.id, title="b",
        amount=Decimal("200"), currency="RUB",
        participant_user_ids=[u1.id],
    ))
    await svc.cancel_expense(e2.id)
    await session.commit()

    rows = await svc.list_filtered(trip.id, ExpenseFilters())
    assert {r.title for r in rows} == {"a"}

    rows_canceled = await svc.list_filtered(trip.id, ExpenseFilters(status="canceled"))
    assert {r.title for r in rows_canceled} == {"b"}


@pytest.mark.asyncio
async def test_filter_search_in_title(trip_session):
    session, trip, u1, u2, u3 = trip_session
    svc = ExpenseService(session, _StubCurrencyService(Decimal("1")))
    await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u1.id, title="ресторан",
        amount=Decimal("100"), currency="RUB",
        participant_user_ids=[u1.id], category="food",
    ))
    await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u1.id, title="такси",
        amount=Decimal("200"), currency="RUB",
        participant_user_ids=[u1.id], category="taxi",
    ))
    await session.commit()

    rows = await svc.list_filtered(trip.id, ExpenseFilters(search="ресто"))
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_analytics_excludes_canceled(trip_session):
    session, trip, u1, u2, u3 = trip_session
    svc = ExpenseService(session, _StubCurrencyService(Decimal("1")))

    await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u1.id, title="a",
        amount=Decimal("100"), currency="RUB",
        participant_user_ids=[u1.id, u2.id], category="food",
    ))
    e2 = await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u1.id, title="b",
        amount=Decimal("500"), currency="RUB",
        participant_user_ids=[u1.id, u2.id], category="food",
    ))
    await svc.cancel_expense(e2.id)
    await session.commit()

    a = await svc.analytics(trip.id, period="trip")
    assert a.count == 1
    assert a.total_display == Decimal("100.00")
    assert a.by_category_display.get("food") == Decimal("100.00")


@pytest.mark.asyncio
async def test_analytics_by_payer_and_participant(trip_session):
    session, trip, u1, u2, u3 = trip_session
    svc = ExpenseService(session, _StubCurrencyService(Decimal("1")))
    await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u1.id, title="a",
        amount=Decimal("300"), currency="RUB",
        participant_user_ids=[u1.id, u2.id, u3.id], category="food",
    ))
    await svc.add_expense(ExpenseInput(
        trip_id=trip.id, payer_user_id=u2.id, title="b",
        amount=Decimal("60"), currency="RUB",
        participant_user_ids=[u2.id, u3.id], category="taxi",
    ))
    await session.commit()

    a = await svc.analytics(trip.id, period="trip")
    assert a.by_payer[u1.id] == Decimal("300.00")
    assert a.by_payer[u2.id] == Decimal("60.00")
    assert a.by_participant[u3.id] == Decimal("130.00")  # 100 + 30


@pytest.mark.asyncio
async def test_analytics_by_day(trip_session):
    session, trip, u1, u2, u3 = trip_session
    svc = ExpenseService(session, _StubCurrencyService(Decimal("1")))
    from app.models.expense import Expense, ExpenseShare

    today = datetime.utcnow()
    yesterday = today - timedelta(days=1)
    for created_at, amount in [(today, "200"), (yesterday, "100")]:
        e = Expense(
            trip_id=trip.id,
            payer_user_id=u1.id,
            title="x",
            category="food",
            amount_original=Decimal(amount),
            currency_original="RUB",
            amount_base=Decimal(amount),
            base_currency="RUB",
            exchange_rate=Decimal("1"),
            created_by_user_id=u1.id,
            status="confirmed",
            created_at=created_at,
        )
        session.add(e)
        await session.flush()
        session.add(
            ExpenseShare(expense_id=e.id, user_id=u1.id, share_amount_base=Decimal(amount))
        )
    await session.commit()

    a = await svc.analytics(trip.id, period="trip")
    assert len(a.by_day) == 2
    assert a.count == 2
