from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from aiogram.types import InlineKeyboardMarkup


class _DummyScope:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyMessage:
    def __init__(
        self,
        chat_type: str,
        text: str = "",
        chat_id: int = 1,
        user_id: int | None = 1,
        bot=None,
        sender_chat_id: int | None = None,
    ):
        self.chat = SimpleNamespace(type=chat_type, id=chat_id)
        if user_id is None:
            self.from_user = None
        else:
            self.from_user = SimpleNamespace(
                id=user_id, username="tester", first_name="Test", last_name="User"
            )
        self.sender_chat = (
            SimpleNamespace(id=sender_chat_id) if sender_chat_id is not None else None
        )
        self.text = text
        self.bot = bot or SimpleNamespace(
            get_me=lambda: None
        )
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_start_group_returns_group_text_without_webapp(monkeypatch):
    from app.bot.handlers import basic

    class _UserService:
        def __init__(self, session):
            self.session = session

        async def get_or_create(self, **kwargs):
            return SimpleNamespace(id=1)

    monkeypatch.setattr(basic, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(basic, "UserService", _UserService)
    monkeypatch.setattr(basic, "_miniapp_kb", lambda: "KB")
    msg = _DummyMessage("group")

    await basic.cmd_start(msg)

    assert msg.answers == [(basic.GROUP_START_TEXT, None)]


@pytest.mark.asyncio
async def test_start_private_returns_private_text_with_webapp(monkeypatch):
    from app.bot.handlers import basic

    class _UserService:
        def __init__(self, session):
            self.session = session

        async def get_or_create(self, **kwargs):
            return SimpleNamespace(id=1)

    monkeypatch.setattr(basic, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(basic, "UserService", _UserService)
    monkeypatch.setattr(basic, "_miniapp_kb", lambda: "KB")
    msg = _DummyMessage("private")

    await basic.cmd_start(msg)

    assert msg.answers == [(basic.PRIVATE_START_TEXT, "KB")]


@pytest.mark.asyncio
async def test_help_group_returns_group_text_without_webapp(monkeypatch):
    from app.bot.handlers import basic

    monkeypatch.setattr(basic, "_miniapp_kb", lambda: "KB")
    msg = _DummyMessage("group")

    await basic.cmd_help(msg)

    assert msg.answers == [(basic.GROUP_HELP_TEXT, None)]


@pytest.mark.asyncio
async def test_help_private_returns_private_text_with_webapp(monkeypatch):
    from app.bot.handlers import basic

    monkeypatch.setattr(basic, "_miniapp_kb", lambda: "KB")
    msg = _DummyMessage("private")

    await basic.cmd_help(msg)

    assert msg.answers == [(basic.PRIVATE_HELP_TEXT, "KB")]


@pytest.mark.asyncio
async def test_app_private_returns_webapp_markup(monkeypatch):
    from app.bot.handlers import basic

    monkeypatch.setattr(basic, "_miniapp_kb", lambda: "KB")
    msg = _DummyMessage("private")

    await basic.cmd_app(msg)

    assert msg.answers == [
        ("Mini App: история расходов, баланс, аналитика, фильтры и редактирование.", "KB")
    ]


@pytest.mark.asyncio
async def test_app_group_returns_url_button_without_webapp():
    from app.bot.handlers import basic

    class _Bot:
        async def get_me(self):
            return SimpleNamespace(username="TravelBot")

    msg = _DummyMessage("group", bot=_Bot())
    await basic.cmd_app(msg)

    assert len(msg.answers) == 1
    text, markup = msg.answers[0]
    assert text == (
        "Mini App открывается в личке с ботом.\n\n"
        "Нажми кнопку ниже, потом открой приложение."
    )
    assert isinstance(markup, InlineKeyboardMarkup)
    assert markup.inline_keyboard[0][0].text == "Открыть в личке"
    assert markup.inline_keyboard[0][0].url == "https://t.me/TravelBot?start=app"
    assert "TrayeOBot" not in markup.inline_keyboard[0][0].url
    assert markup.inline_keyboard[0][0].web_app is None


@pytest.mark.asyncio
async def test_app_group_without_username_falls_back_to_text_only():
    from app.bot.handlers import basic

    class _Bot:
        async def get_me(self):
            return SimpleNamespace(username="")

    msg = _DummyMessage("group", bot=_Bot())
    await basic.cmd_app(msg)

    assert msg.answers == [("Открой личку с ботом и нажми /app.", None)]


def test_group_help_is_short_and_actionable():
    from app.bot.handlers.basic import GROUP_HELP_TEXT

    assert "/join" in GROUP_HELP_TEXT
    assert "/balance" in GROUP_HELP_TEXT
    assert "/members" in GROUP_HELP_TEXT
    assert "/app" in GROUP_HELP_TEXT
    assert "Трейв, 500 рублей такси" in GROUP_HELP_TEXT
    assert "Трейв, 1200 TRY ужин на всех" in GROUP_HELP_TEXT
    assert "/setdisplaycurrency" not in GROUP_HELP_TEXT
    assert "/rename" not in GROUP_HELP_TEXT


def test_private_help_explains_full_flow():
    from app.bot.handlers.basic import PRIVATE_HELP_TEXT

    assert "Добавь меня в групповой чат" in PRIVATE_HELP_TEXT
    assert "Пиши расходы обычным текстом" in PRIVATE_HELP_TEXT
    assert "<b>Команды:</b>" in PRIVATE_HELP_TEXT
    assert "/newtrip" in PRIVATE_HELP_TEXT
    assert "/join" in PRIVATE_HELP_TEXT
    assert "/app — история и аналитика" in PRIVATE_HELP_TEXT
    assert "Трейв, я оплатил 3000 рублей за отель" in PRIVATE_HELP_TEXT


def test_private_start_uses_clear_next_step_language():
    from app.bot.handlers.basic import PRIVATE_START_TEXT

    assert "Пиши расходы обычным текстом." in PRIVATE_START_TEXT
    assert "История, баланс и аналитика: /app" in PRIVATE_START_TEXT


def test_user_texts_do_not_expose_internal_terms():
    from app.bot.handlers.basic import (
        GROUP_HELP_TEXT,
        GROUP_START_TEXT,
        PRIVATE_HELP_TEXT,
        PRIVATE_START_TEXT,
    )
    from app.bot.handlers.expenses import USAGE_HINT

    text = "\n".join(
        [GROUP_HELP_TEXT, PRIVATE_HELP_TEXT, GROUP_START_TEXT, PRIVATE_START_TEXT, USAGE_HINT]
    )
    forbidden = [
        "TripMember",
        "active_trip",
        "parser error",
        "normalized currency",
        "needs_confirmation",
        "intent",
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


def test_members_empty_message_is_safe_and_clear():
    from app.bot.handlers.group_router import _format_members_message

    trip = SimpleNamespace(title="Турция")
    text = _format_members_message(trip, [])

    assert "Пока не вижу участников поездки." in text
    assert "Попроси участников нажать /join." in text


def test_expense_confirmation_has_human_summary():
    from app.bot.handlers.expenses import _build_confirm_text

    text = _build_confirm_text(
        trip_title="Турция",
        amount_str="1 200.00 TRY",
        title="ужин",
        category="food",
        payer_name="Антон",
        participants_str="Антон, Маша",
        per_person_line="\nДоля: по 600.00 TRY",
    )

    assert "Проверь расход" in text
    assert "ужин — <b>1 200.00 TRY</b>" in text
    assert "Оплатил: Антон" in text
    assert "Делим на: Антон, Маша" in text
    assert "Доля: по 600.00 TRY" in text
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

    assert "Добавил расход" in text
    assert "ужин — <b>1\xa0200.00 TRY ≈ 3\xa0600.00 RUB</b>" in text
    assert "1\xa0200.00 TRY ≈ 3\xa0600.00 RUB" in text
    assert "Оплатил: Антон" in text
    assert "Участники: Антон, Маша" in text
    assert "Доля: по 1\xa0800.00 RUB" in text
    assert "/balance" in text


def test_parse_error_contains_required_examples():
    from app.bot.handlers.expenses import USAGE_HINT

    assert "Трейв, 500 рублей такси" in USAGE_HINT
    assert "Трейв, 1200 TRY ужин на всех" in USAGE_HINT
    assert "Трейв, 30 евро музей с Антоном и Машей" in USAGE_HINT
    assert "Трейв, я оплатил 3000 рублей за отель" in USAGE_HINT


def test_format_dual_does_not_duplicate_same_currency():
    from app.services.formatting import format_dual

    assert format_dual(Decimal("500"), "TRY", Decimal("500"), "TRY") == "500.00 TRY"


@pytest.mark.asyncio
async def test_group_newtrip_without_title_asks_for_title():
    from app.bot.handlers import group_router

    group_router._pending_new_trip_titles.clear()
    msg = _DummyMessage("group", text="/newtrip", chat_id=101, user_id=501)

    await group_router.group_new_trip(msg)

    assert msg.answers == [(group_router.NEW_TRIP_PROMPT, None)]
    assert group_router._pending_new_trip_titles.get((101, "user", 501)) is True


@pytest.mark.asyncio
async def test_group_pending_title_same_user_creates_trip(monkeypatch):
    from app.bot.handlers import group_router

    created: list[tuple[str, int]] = []

    class _UserService:
        def __init__(self, session):
            self.session = session

        async def get_or_create(self, **kwargs):
            return SimpleNamespace(id=77)

    class _TripService:
        def __init__(self, session):
            self.session = session

        async def create_trip(self, *, title: str, owner, telegram_chat_id=None):
            created.append((title, telegram_chat_id))
            return SimpleNamespace(id=9, title=title)

    monkeypatch.setattr(group_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(group_router, "UserService", _UserService)
    monkeypatch.setattr(group_router, "TripService", _TripService)
    group_router._pending_new_trip_titles.clear()

    await group_router.group_new_trip(_DummyMessage("group", text="/newtrip", chat_id=101, user_id=501))
    title_msg = _DummyMessage("group", text="Армения", chat_id=101, user_id=501)
    await group_router.group_new_trip_title_input(title_msg)

    assert created == [("Армения", 101)]
    assert (101, "user", 501) not in group_router._pending_new_trip_titles
    assert "Поездка <b>Армения</b> создана." in title_msg.answers[0][0]


@pytest.mark.asyncio
async def test_group_newtrip_requires_non_anonymous_user():
    from app.bot.handlers import group_router

    group_router._pending_new_trip_titles.clear()

    msg = _DummyMessage("group", text="/newtrip", chat_id=101, user_id=None, sender_chat_id=-9001)
    await group_router.group_new_trip(msg)
    assert msg.answers == [(group_router.NEW_TRIP_USER_REQUIRED_TEXT, None)]
    assert group_router._pending_new_trip_titles == {}


@pytest.mark.asyncio
async def test_group_pending_title_other_user_does_not_create_trip(monkeypatch):
    from app.bot.handlers import group_router

    created: list[tuple[str, int]] = []

    class _UserService:
        def __init__(self, session):
            self.session = session

        async def get_or_create(self, **kwargs):
            return SimpleNamespace(id=77)

    class _TripService:
        def __init__(self, session):
            self.session = session

        async def create_trip(self, *, title: str, owner, telegram_chat_id=None):
            created.append((title, telegram_chat_id))
            return SimpleNamespace(id=9, title=title)

    monkeypatch.setattr(group_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(group_router, "UserService", _UserService)
    monkeypatch.setattr(group_router, "TripService", _TripService)
    group_router._pending_new_trip_titles.clear()

    await group_router.group_new_trip(_DummyMessage("group", text="/newtrip", chat_id=101, user_id=501))
    other_msg = _DummyMessage("group", text="Турция", chat_id=101, user_id=777)
    if await group_router.PendingNewTripTitleFilter()(other_msg):
        await group_router.group_new_trip_title_input(other_msg)

    assert created == []
    assert other_msg.answers == []
    assert group_router._pending_new_trip_titles.get((101, "user", 501)) is True


@pytest.mark.asyncio
async def test_group_cancel_clears_pending_newtrip():
    from app.bot.handlers import group_router

    group_router._pending_new_trip_titles.clear()
    await group_router.group_new_trip(_DummyMessage("group", text="/newtrip", chat_id=101, user_id=501))

    cancel_msg = _DummyMessage("group", text="/cancel", chat_id=101, user_id=501)
    await group_router.group_cancel_new_trip(cancel_msg)

    assert cancel_msg.answers == [(group_router.NEW_TRIP_CANCELLED_TEXT, None)]
    assert (101, "user", 501) not in group_router._pending_new_trip_titles


@pytest.mark.asyncio
async def test_group_newtrip_with_title_creates_immediately(monkeypatch):
    from app.bot.handlers import group_router

    created: list[tuple[str, int]] = []

    class _UserService:
        def __init__(self, session):
            self.session = session

        async def get_or_create(self, **kwargs):
            return SimpleNamespace(id=77)

    class _TripService:
        def __init__(self, session):
            self.session = session

        async def create_trip(self, *, title: str, owner, telegram_chat_id=None):
            created.append((title, telegram_chat_id))
            return SimpleNamespace(id=10, title=title)

    monkeypatch.setattr(group_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(group_router, "UserService", _UserService)
    monkeypatch.setattr(group_router, "TripService", _TripService)
    group_router._pending_new_trip_titles.clear()

    msg = _DummyMessage("group", text="/newtrip Армения", chat_id=102, user_id=502)
    await group_router.group_new_trip(msg)

    assert created == [("Армения", 102)]
    assert (102, "user", 502) not in group_router._pending_new_trip_titles
    assert "Поездка <b>Армения</b> создана." in msg.answers[0][0]


@pytest.mark.asyncio
async def test_private_newtrip_without_title_asks_for_title():
    from app.bot.handlers import private_router

    private_router._pending_new_trip_titles.clear()
    msg = _DummyMessage("private", text="/newtrip", chat_id=201, user_id=601)

    await private_router.cmd_new_trip_private(msg)

    assert msg.answers == [(private_router.NEW_TRIP_PROMPT, None)]
    assert private_router._pending_new_trip_titles.get((201, 601)) is True


@pytest.mark.asyncio
async def test_commands_during_pending_are_not_treated_as_trip_title(monkeypatch):
    from app.bot.handlers import group_router

    created: list[tuple[str, int]] = []

    class _UserService:
        def __init__(self, session):
            self.session = session

        async def get_or_create(self, **kwargs):
            return SimpleNamespace(id=77)

    class _TripService:
        def __init__(self, session):
            self.session = session

        async def create_trip(self, *, title: str, owner, telegram_chat_id=None):
            created.append((title, telegram_chat_id))
            return SimpleNamespace(id=10, title=title)

    monkeypatch.setattr(group_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(group_router, "UserService", _UserService)
    monkeypatch.setattr(group_router, "TripService", _TripService)
    group_router._pending_new_trip_titles.clear()

    await group_router.group_new_trip(_DummyMessage("group", text="/newtrip", chat_id=103, user_id=503))
    command_msg = _DummyMessage("group", text="/members", chat_id=103, user_id=503)
    await group_router.group_new_trip_title_input(command_msg)

    assert created == []
    assert command_msg.answers == []
    assert group_router._pending_new_trip_titles.get((103, "user", 503)) is True


@pytest.mark.asyncio
async def test_group_pending_filter_matches_only_same_user_pending():
    from app.bot.handlers import group_router

    group_router._pending_new_trip_titles.clear()
    flt = group_router.PendingNewTripTitleFilter()
    same = _DummyMessage("group", text="Армения", chat_id=555, user_id=777)
    other = _DummyMessage("group", text="Армения", chat_id=555, user_id=778)

    assert await flt(same) is False
    group_router._pending_new_trip_titles[(555, "user", 777)] = True
    assert await flt(same) is True
    assert await flt(other) is False


@pytest.mark.asyncio
async def test_group_pending_filter_supports_sender_chat_key():
    from app.bot.handlers import group_router

    group_router._pending_new_trip_titles.clear()
    flt = group_router.PendingNewTripTitleFilter()
    same = _DummyMessage("group", text="Вьетнам", chat_id=555, user_id=None, sender_chat_id=-444)
    other = _DummyMessage("group", text="Вьетнам", chat_id=555, user_id=None, sender_chat_id=-445)

    assert await flt(same) is False
    group_router._pending_new_trip_titles[(555, "sender_chat", -444)] = True
    assert await flt(same) is True
    assert await flt(other) is False


@pytest.mark.asyncio
async def test_group_addressed_expense_without_pending_reaches_intent_router(monkeypatch):
    from app.bot.handlers import group_router
    from app.bot import intent_router

    calls: list[tuple[str, str, bool]] = []

    async def _fake_handle_intent_text(message, text, *, source, use_reply=False):
        calls.append((text, source, use_reply))
        return True

    class _Bot:
        id = 8841451417

        async def me(self):
            return SimpleNamespace(id=self.id, username="Trave0Bot")

    monkeypatch.setattr(intent_router, "handle_intent_text", _fake_handle_intent_text)
    group_router._pending_new_trip_titles.clear()

    msg = _DummyMessage("group", text="Трейв, 400 лир такси", chat_id=600, user_id=700, bot=_Bot())
    msg.reply_to_message = None

    await group_router.group_natural_text(msg)

    assert calls
    assert "400 лир такси" in calls[0][0]
    assert calls[0][2] is True


@pytest.mark.asyncio
async def test_group_addressed_weather_without_pending_reaches_intent_router(monkeypatch):
    from app.bot.handlers import group_router
    from app.bot import intent_router

    calls: list[tuple[str, str, bool]] = []

    async def _fake_handle_intent_text(message, text, *, source, use_reply=False):
        calls.append((text, source, use_reply))
        return True

    class _Bot:
        id = 8841451417

        async def me(self):
            return SimpleNamespace(id=self.id, username="Trave0Bot")

    monkeypatch.setattr(intent_router, "handle_intent_text", _fake_handle_intent_text)
    group_router._pending_new_trip_titles.clear()

    msg = _DummyMessage(
        "group",
        text="Трейв, погода в Стамбуле на 2 дня",
        chat_id=601,
        user_id=701,
        bot=_Bot(),
    )
    msg.reply_to_message = None

    await group_router.group_natural_text(msg)

    assert calls
    assert "погода в Стамбуле на 2 дня" in calls[0][0]
    assert calls[0][2] is True


@pytest.mark.asyncio
async def test_group_pending_other_user_still_reaches_natural_text(monkeypatch):
    from app.bot.handlers import group_router
    from app.bot import intent_router

    calls: list[tuple[str, str, bool]] = []

    async def _fake_handle_intent_text(message, text, *, source, use_reply=False):
        calls.append((text, source, use_reply))
        return True

    class _Bot:
        id = 8841451417

        async def me(self):
            return SimpleNamespace(id=self.id, username="Trave0Bot")

    monkeypatch.setattr(intent_router, "handle_intent_text", _fake_handle_intent_text)
    group_router._pending_new_trip_titles.clear()
    group_router._pending_new_trip_titles[(777, "user", 111)] = True

    msg = _DummyMessage("group", text="Трейв, 500 рублей такси", chat_id=777, user_id=222, bot=_Bot())
    msg.reply_to_message = None

    assert await group_router.PendingNewTripTitleFilter()(msg) is False
    await group_router.group_natural_text(msg)

    assert calls
    assert "500 рублей такси" in calls[0][0]


@pytest.mark.asyncio
async def test_private_pending_filter_does_not_match_without_state():
    from app.bot.handlers import private_router

    private_router._pending_new_trip_titles.clear()
    flt = private_router.PendingNewTripTitleFilter()
    msg = _DummyMessage("private", text="просто текст", chat_id=900, user_id=901)
    assert await flt(msg) is False
