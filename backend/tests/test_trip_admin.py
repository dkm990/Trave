"""Tests for trip admin operations: rename, set_default_currency, has_expenses."""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.trip_service import TripService


@pytest.fixture
async def session_with_trip():
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
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


def _add_expense(session, *, trip_id, user_id, amount="100", currency="RUB"):
    from app.models.expense import Expense

    e = Expense(
        trip_id=trip_id,
        payer_user_id=user_id,
        title="t",
        category="food",
        amount_original=Decimal(amount),
        currency_original=currency,
        amount_base=Decimal(amount),
        base_currency=currency,
        exchange_rate=Decimal("1"),
        created_by_user_id=user_id,
        status="confirmed",
        created_at=datetime.utcnow(),
    )
    session.add(e)
    return e


@pytest.mark.asyncio
async def test_rename_changes_title(session_with_trip):
    session, trip, _ = session_with_trip
    await TripService(session).rename(trip, "Турция")
    await session.commit()
    assert trip.title == "Турция"


@pytest.mark.asyncio
async def test_rename_strips_and_truncates(session_with_trip):
    session, trip, _ = session_with_trip
    long_name = "  " + "X" * 250 + "  "
    await TripService(session).rename(trip, long_name)
    await session.commit()
    assert len(trip.title) == 200
    assert not trip.title.startswith(" ")


@pytest.mark.asyncio
async def test_has_expenses_initially_false(session_with_trip):
    session, trip, _ = session_with_trip
    assert await TripService(session).has_expenses(trip.id) is False


@pytest.mark.asyncio
async def test_has_expenses_true_after_add(session_with_trip):
    session, trip, user = session_with_trip
    _add_expense(session, trip_id=trip.id, user_id=user.id)
    await session.commit()
    assert await TripService(session).has_expenses(trip.id) is True


@pytest.mark.asyncio
async def test_set_default_currency_uppercase(session_with_trip):
    session, trip, _ = session_with_trip
    await TripService(session).set_default_currency(trip, "try")
    await session.commit()
    assert trip.default_currency == "TRY"


@pytest.mark.asyncio
async def test_set_currency_before_expenses_allowed(session_with_trip):
    session, trip, _ = session_with_trip
    svc = TripService(session)
    assert await svc.has_expenses(trip.id) is False
    await svc.set_default_currency(trip, "TRY")
    await session.commit()
    assert trip.default_currency == "TRY"


@pytest.mark.asyncio
async def test_set_currency_after_expenses_should_be_blocked_at_handler(
    session_with_trip,
):
    """Service-level allows change; handler should check has_expenses."""
    session, trip, user = session_with_trip
    svc = TripService(session)
    _add_expense(session, trip_id=trip.id, user_id=user.id)
    await session.commit()
    assert await svc.has_expenses(trip.id) is True


@pytest.mark.asyncio
async def test_bind_older_trip_switches_active_trip(session_with_trip):
    session, trip, user = session_with_trip
    from app.models.trip import Trip

    svc = TripService(session)
    await svc.bind_to_chat(trip, 777)

    newer = Trip(
        title="Newer",
        default_currency="RUB",
        created_by_user_id=user.id,
        telegram_chat_id=777,
    )
    session.add(newer)
    await session.flush()
    await session.commit()

    await svc.bind_to_chat(trip, 777)
    await session.commit()

    active_after_bind = await svc.get_trip_for_chat(777)
    assert active_after_bind is not None
    assert active_after_bind.id == trip.id
    assert newer.telegram_chat_id is None


def test_expense_confirmation_trip_line():
    from app.bot.handlers.expenses import _trip_label_line

    assert _trip_label_line("Чечня") == "Поездка: <b>Чечня</b>\n"


def test_expense_confirmation_text_contains_selected_trip():
    from app.bot.handlers.expenses import _build_confirm_text

    text = _build_confirm_text(
        trip_title="Trip A",
        amount_str="1000 RUB",
        title="такси",
        payer_name="Alex",
        participants_str="Alex, Ahmed",
        per_person_line="",
    )
    assert "Поездка: <b>Trip A</b>" in text


@pytest.mark.asyncio
async def test_group_trips_does_not_leak_user_personal_trips(session_with_trip):
    session, trip_a, user = session_with_trip
    from app.bot.handlers.group_router import _format_group_trips_message
    from app.models.trip import Trip, TripMember

    svc = TripService(session)
    await svc.bind_to_chat(trip_a, 777)

    trip_b = Trip(
        title="Trip B",
        default_currency="RUB",
        created_by_user_id=user.id,
        telegram_chat_id=777,
    )
    session.add(trip_b)
    await session.flush()
    session.add(
        TripMember(
            trip_id=trip_b.id,
            user_id=user.id,
            display_name="Test",
            role="owner",
        )
    )
    await session.flush()

    private_trip = Trip(
        title="Private Only",
        default_currency="RUB",
        created_by_user_id=user.id,
    )
    session.add(private_trip)
    await session.flush()
    session.add(
        TripMember(
            trip_id=private_trip.id,
            user_id=user.id,
            display_name="Test",
            role="member",
        )
    )
    await session.flush()

    await svc.bind_to_chat(trip_a, 777)
    await session.commit()

    active = await svc.get_trip_for_chat(777)
    chat_trips = await svc.list_trips_for_chat(777)
    text = _format_group_trips_message(active, chat_trips)

    assert active is not None
    assert active.id == trip_a.id
    assert "Активная поездка:" in text
    assert "Поездки, привязанные к этому чату:" in text
    assert "Trip B" not in text
    assert "Private Only" not in text


def test_private_mytrips_shows_user_trips():
    from types import SimpleNamespace

    from app.bot.handlers.private_router import _format_my_trips_message

    text = _format_my_trips_message(
        [
            SimpleNamespace(id=1, title="Trip A", default_currency="RUB"),
            SimpleNamespace(id=2, title="Trip B", default_currency="USD"),
        ]
    )

    assert "Trip A" in text
    assert "Trip B" in text
    assert "/bindtrip TRIP_ID" in text


@pytest.mark.asyncio
async def test_summary_total_and_balances(session_with_trip):
    session, trip, user = session_with_trip
    from app.services.balance_service import BalanceService, simplify_debts
    from app.services.expense_service import ExpenseService

    _add_expense(session, trip_id=trip.id, user_id=user.id, amount="500")
    _add_expense(session, trip_id=trip.id, user_id=user.id, amount="300")
    from app.models.expense import ExpenseShare

    expenses_q = await ExpenseService(session, None).list_expenses(trip.id)
    for e in expenses_q:
        session.add(
            ExpenseShare(
                expense_id=e.id, user_id=user.id, share_amount_base=Decimal(e.amount_base)
            )
        )
    await session.commit()

    expenses = await ExpenseService(session, None).list_expenses(trip.id)
    total = sum(Decimal(e.amount_base) for e in expenses if e.status == "confirmed")
    assert total == Decimal("800")
    balances = await BalanceService(session).calculate_balances(trip.id)
    transfers = simplify_debts(balances)
    assert balances[0].paid == Decimal("800.00")
    assert transfers == []


def test_validate_currency_basic():
    from app.ai.rule_based import KNOWN_CURRENCY_CODES

    for code in ("USD", "EUR", "RUB", "TRY", "GEL", "VND", "THB"):
        assert code in KNOWN_CURRENCY_CODES


def test_validate_currency_rejects_garbage():
    from app.ai.rule_based import KNOWN_CURRENCY_CODES

    assert "XYZ" not in KNOWN_CURRENCY_CODES
    assert "12" not in KNOWN_CURRENCY_CODES
    assert "" not in KNOWN_CURRENCY_CODES
