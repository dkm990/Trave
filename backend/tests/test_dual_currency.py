"""Tests для dual-currency display: format_dual + today summary."""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.formatting import format_dual
from app.services.expense_service import ExpenseService
from app.services.trip_service import TripService


def test_format_dual_different_currencies():
    s = format_dual(Decimal("500"), "TRY", Decimal("804.45"), "RUB")
    assert "TRY" in s
    assert "≈" in s
    assert "RUB" in s


def test_format_dual_same_currency_no_approx():
    s = format_dual(Decimal("500"), "RUB", Decimal("500"), "RUB")
    assert "≈" not in s
    assert s.endswith(" RUB")


def test_format_dual_lowercase_codes_normalized():
    s = format_dual(Decimal("100"), "try", Decimal("100"), "TRY")
    assert "≈" not in s


def test_format_dual_mixed_case_normalized_diff():
    s = format_dual(Decimal("100"), "Usd", Decimal("90"), "rub")
    assert "USD" in s
    assert "RUB" in s
    assert "≈" in s


class _DummyCurrency:
    pass


@pytest.fixture
async def session_with_trip():
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
        user = User(telegram_user_id=42, first_name="Test")
        session.add(user)
        await session.flush()
        trip = Trip(
            title="Турция",
            default_currency="RUB",
            created_by_user_id=user.id,
        )
        session.add(trip)
        await session.flush()
        m = TripMember(trip_id=trip.id, user_id=user.id, display_name="Test", role="owner")
        session.add(m)
        await session.flush()
        yield session, trip, user


def _add_expense(
    session,
    *,
    trip_id,
    user_id,
    amount_original="500",
    currency_original="TRY",
    amount_base="804.45",
    base_currency="RUB",
    category="taxi",
    created_at=None,
):
    from app.models.expense import Expense

    e = Expense(
        trip_id=trip_id,
        payer_user_id=user_id,
        title="t",
        category=category,
        amount_original=Decimal(amount_original),
        currency_original=currency_original,
        amount_base=Decimal(amount_base),
        base_currency=base_currency,
        exchange_rate=Decimal("1.6089"),
        created_by_user_id=user_id,
        status="confirmed",
        created_at=created_at or datetime.utcnow(),
    )
    session.add(e)
    return e


@pytest.mark.asyncio
async def test_today_summary_single_original_currency(session_with_trip):
    session, trip, user = session_with_trip
    _add_expense(session, trip_id=trip.id, user_id=user.id,
                 amount_original="500", currency_original="TRY",
                 amount_base="804.45", base_currency="RUB", category="taxi")
    _add_expense(session, trip_id=trip.id, user_id=user.id,
                 amount_original="1200", currency_original="TRY",
                 amount_base="1930.69", base_currency="RUB", category="food")
    await session.commit()

    svc = ExpenseService(session, _DummyCurrency())
    summary = await svc.today_summary(trip.id)
    assert summary.count == 2
    assert summary.total == Decimal("2735.14")
    assert summary.by_original_currency == {"TRY": Decimal("1700.00")}
    assert summary.by_category_original["food"] == {"TRY": Decimal("1200.00")}
    assert summary.by_category_original["taxi"] == {"TRY": Decimal("500.00")}


@pytest.mark.asyncio
async def test_today_summary_multiple_currencies(session_with_trip):
    session, trip, user = session_with_trip
    _add_expense(session, trip_id=trip.id, user_id=user.id,
                 amount_original="1000", currency_original="TRY",
                 amount_base="1608.90", base_currency="RUB", category="food")
    _add_expense(session, trip_id=trip.id, user_id=user.id,
                 amount_original="50", currency_original="USD",
                 amount_base="4500.00", base_currency="RUB", category="taxi")
    await session.commit()

    svc = ExpenseService(session, _DummyCurrency())
    summary = await svc.today_summary(trip.id)
    assert summary.count == 2
    assert "TRY" in summary.by_original_currency
    assert "USD" in summary.by_original_currency
    assert summary.by_original_currency["TRY"] == Decimal("1000.00")
    assert summary.by_original_currency["USD"] == Decimal("50.00")


@pytest.mark.asyncio
async def test_today_summary_original_eq_base(session_with_trip):
    """Expense в RUB и base RUB → нет ≈ в format_dual."""
    session, trip, user = session_with_trip
    _add_expense(session, trip_id=trip.id, user_id=user.id,
                 amount_original="1000", currency_original="RUB",
                 amount_base="1000.00", base_currency="RUB", category="food")
    await session.commit()

    svc = ExpenseService(session, _DummyCurrency())
    summary = await svc.today_summary(trip.id)
    assert summary.by_original_currency == {"RUB": Decimal("1000.00")}
    head = format_dual(
        list(summary.by_original_currency.values())[0],
        list(summary.by_original_currency.keys())[0],
        summary.total,
        summary.base_currency,
    )
    assert "≈" not in head


@pytest.mark.asyncio
async def test_set_local_currency(session_with_trip):
    session, trip, _ = session_with_trip
    assert trip.local_currency is None
    await TripService(session).set_local_currency(trip, "try")
    await session.commit()
    assert trip.local_currency == "TRY"


@pytest.mark.asyncio
async def test_set_local_currency_after_expenses_allowed(session_with_trip):
    """local_currency — analytics setting, можно менять даже после расходов."""
    session, trip, user = session_with_trip
    _add_expense(session, trip_id=trip.id, user_id=user.id)
    await session.commit()
    svc = TripService(session)
    assert await svc.has_expenses(trip.id) is True
    await svc.set_local_currency(trip, "TRY")
    await session.commit()
    assert trip.local_currency == "TRY"
