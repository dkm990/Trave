"""Tests for ExpenseService.today_summary with timezone-aware boundaries."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.services.expense_service import ExpenseService


class _DummyCurrency:
    pass


@pytest.fixture
async def session_with_trip():
    """In-memory sqlite session with a trip and a payer user."""
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
            title="Test Trip",
            default_currency="RUB",
            created_by_user_id=user.id,
        )
        session.add(trip)
        await session.flush()
        member = TripMember(
            trip_id=trip.id, user_id=user.id, display_name="Test", role="owner"
        )
        session.add(member)
        await session.flush()
        yield session, trip, user


def _make_expense(*, trip_id, payer_user_id, created_at, amount="100.00",
                  category="food", status="confirmed"):
    from app.models.expense import Expense

    return Expense(
        trip_id=trip_id,
        payer_user_id=payer_user_id,
        title="test",
        category=category,
        amount_original=Decimal(amount),
        currency_original="RUB",
        amount_base=Decimal(amount),
        base_currency="RUB",
        exchange_rate=Decimal("1"),
        created_by_user_id=payer_user_id,
        status=status,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_today_summary_picks_up_recent_expense(session_with_trip):
    session, trip, user = session_with_trip
    now_utc_naive = datetime.utcnow()
    session.add(_make_expense(
        trip_id=trip.id, payer_user_id=user.id, created_at=now_utc_naive,
        amount="1500.00", category="food",
    ))
    await session.commit()

    svc = ExpenseService(session, _DummyCurrency())
    summary = await svc.today_summary(trip.id)
    assert summary.count == 1
    assert summary.total == Decimal("1500.00")
    assert summary.by_category.get("food") == Decimal("1500.00")


@pytest.mark.asyncio
async def test_today_summary_ignores_yesterday(session_with_trip):
    session, trip, user = session_with_trip
    two_days_ago = datetime.utcnow() - timedelta(days=2)
    session.add(_make_expense(
        trip_id=trip.id, payer_user_id=user.id, created_at=two_days_ago,
        amount="999.00",
    ))
    await session.commit()

    svc = ExpenseService(session, _DummyCurrency())
    summary = await svc.today_summary(trip.id)
    assert summary.count == 0
    assert summary.total == Decimal("0.00")


@pytest.mark.asyncio
async def test_today_summary_groups_by_category(session_with_trip):
    session, trip, user = session_with_trip
    now = datetime.utcnow()
    session.add(_make_expense(
        trip_id=trip.id, payer_user_id=user.id, created_at=now,
        amount="500.00", category="taxi",
    ))
    session.add(_make_expense(
        trip_id=trip.id, payer_user_id=user.id, created_at=now,
        amount="1500.00", category="food",
    ))
    session.add(_make_expense(
        trip_id=trip.id, payer_user_id=user.id, created_at=now,
        amount="300.00", category="food",
    ))
    await session.commit()

    svc = ExpenseService(session, _DummyCurrency())
    summary = await svc.today_summary(trip.id)
    assert summary.count == 3
    assert summary.total == Decimal("2300.00")
    assert summary.by_category["food"] == Decimal("1800.00")
    assert summary.by_category["taxi"] == Decimal("500.00")
    assert list(summary.by_category.keys())[0] == "food"


@pytest.mark.asyncio
async def test_today_summary_pending_excluded(session_with_trip):
    session, trip, user = session_with_trip
    now = datetime.utcnow()
    session.add(_make_expense(
        trip_id=trip.id, payer_user_id=user.id, created_at=now,
        status="pending_confirmed",
    ))
    await session.commit()

    svc = ExpenseService(session, _DummyCurrency())
    summary = await svc.today_summary(trip.id)
    assert summary.count == 0


@pytest.mark.asyncio
async def test_today_summary_empty_returns_zero(session_with_trip):
    session, trip, user = session_with_trip
    svc = ExpenseService(session, _DummyCurrency())
    summary = await svc.today_summary(trip.id)
    assert summary.count == 0
    assert summary.total == Decimal("0.00")
    assert summary.by_category == {}
