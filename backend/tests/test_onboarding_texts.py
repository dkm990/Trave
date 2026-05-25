from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace


def test_group_help_is_short_and_actionable():
    from app.bot.handlers.basic import GROUP_HELP_TEXT

    assert "/newtrip" in GROUP_HELP_TEXT
    assert "/join" in GROUP_HELP_TEXT
    assert "/balance" in GROUP_HELP_TEXT
    assert "/members" in GROUP_HELP_TEXT
    assert "/app" in GROUP_HELP_TEXT
    assert "Трейв, 500 рублей такси" in GROUP_HELP_TEXT
    assert "/setdisplaycurrency" not in GROUP_HELP_TEXT
    assert "/rename" not in GROUP_HELP_TEXT


def test_private_help_explains_full_flow():
    from app.bot.handlers.basic import PRIVATE_HELP_TEXT

    assert "Добавьте бота в групповой чат" in PRIVATE_HELP_TEXT
    assert "/newtrip" in PRIVATE_HELP_TEXT
    assert "/join" in PRIVATE_HELP_TEXT
    assert "история, аналитика" in PRIVATE_HELP_TEXT
    assert "Трейв, я оплатил 3000 рублей за отель" in PRIVATE_HELP_TEXT
    assert "/bindtrip ID" in PRIVATE_HELP_TEXT


def test_user_texts_do_not_expose_internal_terms():
    from app.bot.handlers.basic import GROUP_HELP_TEXT, GROUP_START_TEXT, PRIVATE_HELP_TEXT
    from app.bot.handlers.expenses import USAGE_HINT

    text = "\n".join([GROUP_HELP_TEXT, PRIVATE_HELP_TEXT, GROUP_START_TEXT, USAGE_HINT])
    forbidden = [
        "TripMember",
        "active_trip",
        "parser error",
        "normalized currency",
        "needs_confirmation",
    ]
    for term in forbidden:
        assert term not in text


def test_members_message_points_to_join():
    from app.bot.handlers.group_router import _format_members_message

    trip = SimpleNamespace(title="Турция")
    member = SimpleNamespace(display_name="Антон", user_id=10, role="member")
    text = _format_members_message(trip, [member])

    assert "Участники поездки Турция" in text
    assert "Антон" in text
    assert "/join" in text


def test_expense_confirmation_has_human_summary():
    from app.bot.handlers.expenses import _build_confirm_text

    text = _build_confirm_text(
        trip_title="Турция",
        amount_str="1 200.00 TRY",
        title="ужин",
        category="food",
        payer_name="Антон",
        participants_str="Антон, Маша",
        per_person_line="\nДоля каждого: 600.00 TRY",
    )

    assert "Поездка: <b>Турция</b>" in text
    assert "Понял расход" in text
    assert "Категория: еда" in text
    assert "Описание: ужин" in text
    assert "Оплатил: Антон" in text
    assert "Делим на: Антон, Маша" in text
    assert "Доля каждого" in text
    assert "Per person" not in text


def test_expense_success_text_shows_amount_conversion_and_balance_command():
    from app.bot.handlers.expenses import PendingExpense, _build_success_text

    pending = PendingExpense(
        chat_id=1,
        from_user_id=10,
        trip_id=5,
        trip_title="Турция",
        payer_user_id=10,
        title="ужин",
        amount="1200",
        currency="TRY",
        category="food",
        participants=[10, 11],
        available=[(10, "Антон"), (11, "Маша")],
    )
    expense = SimpleNamespace(
        amount_original=Decimal("1200"),
        currency_original="TRY",
        amount_base=Decimal("3600"),
        base_currency="RUB",
        shares=[
            SimpleNamespace(user_id=10, share_amount_base=Decimal("1800")),
            SimpleNamespace(user_id=11, share_amount_base=Decimal("1800")),
        ],
    )

    text = _build_success_text(pending, expense)

    assert "Расход добавлен" in text
    assert "Категория: еда" in text
    assert "Описание: ужин" in text
    assert "1\xa0200.00 TRY ≈ 3\xa0600.00 RUB" in text
    assert "Оплатил: Антон" in text
    assert "Участники: Антон, Маша" in text
    assert "• Маша: 1\xa0800.00 RUB" in text
    assert "/balance" in text


def test_format_dual_does_not_duplicate_same_currency():
    from app.services.formatting import format_dual

    assert format_dual(Decimal("500"), "TRY", Decimal("500"), "TRY") == "500.00 TRY"
