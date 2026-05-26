from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.ai.base import Intent
from app.bot import intent_router
from app.services.travel_intent_service import (
    TravelIntentResult,
    TravelIntentService,
    TravelWeatherIntent,
)


class _DummyScope:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyMessage:
    def __init__(self, text: str, *, chat_type: str = "group"):
        self.text = text
        self.chat = SimpleNamespace(type=chat_type, id=123)
        self.from_user = SimpleNamespace(id=456, username="u", first_name="U", last_name="S")
        self.answers: list[str] = []
        self.replies: list[str] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append(text)

    async def reply(self, text: str, reply_markup=None):
        self.replies.append(text)


class _FakeProvider:
    def __init__(self, intent: Intent):
        self._intent = intent

    async def parse_intent(self, text: str, *, context=None) -> Intent:
        return self._intent

    async def generate_chat_response(self, text: str, *, context: str = "", trip_info: str = "") -> str:
        return "chat"

    @property
    def name(self) -> str:
        return "fake"


class _FakeExtractor:
    def __init__(self, result: TravelIntentResult):
        self.result = result

    async def extract(self, raw_text: str, *, chat_context: str, current_dt: datetime, active_trip_title: str | None = None):
        return self.result


def _settings(*, enabled: bool):
    return SimpleNamespace(enable_travel_intent_extractor=enabled)


def _mk_weather_json(location: str, *, surface: str | None, period: str, date_text: str | None = None, days: int | None = None):
    return {
        "intent": "weather",
        "confidence": 0.93,
        "weather": {
            "location": location,
            "location_surface": surface,
            "period_type": period,
            "date_text": date_text,
            "days": days,
        },
        "expense": {
            "amount": None,
            "currency": None,
            "description": None,
            "participants_text": None,
        },
    }


@pytest.mark.asyncio
async def test_travel_intent_extract_weather_free_form_date(monkeypatch):
    service = TravelIntentService()
    monkeypatch.setattr(service, "_init_client", lambda: object())
    payload = _mk_weather_json("Стамбул", surface=None, period="exact_date", date_text="4 июня")
    monkeypatch.setattr(service, "_call_gemini", lambda client, prompt: payload and __import__("asyncio").sleep(0, result=__import__("json").dumps(payload)))

    out = await service.extract(
        "трейв погода стамбул 4 июня",
        chat_context="group",
        current_dt=datetime.now(),
    )
    assert out.intent == "weather"
    assert out.weather and out.weather.location == "Стамбул"
    assert out.weather.date_text == "4 июня"
    assert out.weather.period_type == "exact_date"


@pytest.mark.asyncio
async def test_travel_intent_extract_weather_weekend(monkeypatch):
    service = TravelIntentService()
    monkeypatch.setattr(service, "_init_client", lambda: object())
    payload = _mk_weather_json("Стамбул", surface="в Стамбуле", period="weekend")
    monkeypatch.setattr(service, "_call_gemini", lambda client, prompt: __import__("asyncio").sleep(0, result=__import__("json").dumps(payload)))

    out = await service.extract(
        "трейв что там по погоде в Стамбуле на выходных",
        chat_context="group",
        current_dt=datetime.now(),
    )
    assert out.intent == "weather"
    assert out.weather and out.weather.period_type == "weekend"
    assert out.weather.location == "Стамбул"


@pytest.mark.asyncio
async def test_travel_intent_extract_weather_tomorrow(monkeypatch):
    service = TravelIntentService()
    monkeypatch.setattr(service, "_init_client", lambda: object())
    payload = _mk_weather_json("Москва", surface="в Москве", period="tomorrow")
    monkeypatch.setattr(service, "_call_gemini", lambda client, prompt: __import__("asyncio").sleep(0, result=__import__("json").dumps(payload)))

    out = await service.extract(
        "трейв в москве завтра дождь?",
        chat_context="group",
        current_dt=datetime.now(),
    )
    assert out.intent == "weather"
    assert out.weather and out.weather.location == "Москва"
    assert out.weather.period_type == "tomorrow"


@pytest.mark.asyncio
async def test_travel_intent_extract_weather_week(monkeypatch):
    service = TravelIntentService()
    monkeypatch.setattr(service, "_init_client", lambda: object())
    payload = _mk_weather_json("Бали", surface="на Бали", period="week", days=7)
    monkeypatch.setattr(service, "_call_gemini", lambda client, prompt: __import__("asyncio").sleep(0, result=__import__("json").dumps(payload)))

    out = await service.extract(
        "трейв глянь погоду на бали на неделю",
        chat_context="group",
        current_dt=datetime.now(),
    )
    assert out.intent == "weather"
    assert out.weather and out.weather.location == "Бали"
    assert out.weather.period_type == "week"
    assert out.weather.days == 7


@pytest.mark.asyncio
async def test_travel_intent_invalid_json_returns_unknown(monkeypatch):
    service = TravelIntentService()
    monkeypatch.setattr(service, "_init_client", lambda: object())
    monkeypatch.setattr(service, "_call_gemini", lambda client, prompt: __import__("asyncio").sleep(0, result="{not-json"))

    out = await service.extract(
        "трейв погода стамбул",
        chat_context="group",
        current_dt=datetime.now(),
    )
    assert out.intent == "unknown"


@pytest.mark.asyncio
async def test_expense_like_text_still_uses_existing_parser(monkeypatch):
    calls: list[str] = []

    async def _fake_propose(message, intent, *, source, use_reply=False):
        calls.append(intent.action)

    fake_provider = _FakeProvider(
        Intent(
            action="add_expense",
            confidence=0.9,
            payload={"amount": "400", "currency": "TRY", "title": "такси", "split_scope": "self"},
            raw_text="трейв 400 лир такси",
            needs_confirmation=True,
        )
    )

    extractor_called = {"value": False}

    class _NeverCalledExtractor:
        async def extract(self, *args, **kwargs):
            extractor_called["value"] = True
            return TravelIntentResult.unknown()

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(intent_router, "_resolve_active_trip", lambda session, message: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _NeverCalledExtractor())
    monkeypatch.setattr("app.bot.handlers.expenses.propose_expense_from_intent", _fake_propose)

    msg = _DummyMessage("трейв 400 лир такси", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert calls == ["add_expense"]
    assert extractor_called["value"] is False


@pytest.mark.asyncio
async def test_weather_routing_uses_weather_api_not_llm_facts(monkeypatch):
    weather_calls: list[tuple[str, dict]] = []

    async def _fake_weather(city, **kwargs):
        weather_calls.append((city, kwargs))
        return "weather-api-response"

    fake_provider = _FakeProvider(Intent(action="unknown", confidence=0.0, payload={}, raw_text="x"))
    extracted = TravelIntentResult(
        intent="weather",
        confidence=0.9,
        weather=TravelWeatherIntent(location="Стамбул", location_surface="в Стамбуле", period_type="days", days=2),
    )

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_weather", _fake_weather)
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(intent_router, "_resolve_active_trip", lambda session, message: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _FakeExtractor(extracted))

    msg = _DummyMessage("трейв погода стамбул 2 дня", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert weather_calls
    assert weather_calls[0][0] == "Стамбул"
    assert weather_calls[0][1].get("days") == 2
    assert msg.replies == ["weather-api-response"]


@pytest.mark.asyncio
async def test_flag_false_does_not_call_travel_intent_extractor(monkeypatch):
    called = {"value": False}

    class _ShouldNotBeCalled:
        async def extract(self, *args, **kwargs):
            called["value"] = True
            return TravelIntentResult.unknown()

    fake_provider = _FakeProvider(Intent(action="unknown", confidence=0.0, payload={}, raw_text="x"))
    async def _fake_chat_response(message, text, send):
        await send("chat")
    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=False))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _ShouldNotBeCalled())
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "_chat_response", _fake_chat_response)

    msg = _DummyMessage("привет", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert called["value"] is False


@pytest.mark.asyncio
async def test_flag_true_calls_travel_intent_extractor(monkeypatch):
    called = {"value": False}

    class _CalledExtractor:
        async def extract(self, *args, **kwargs):
            called["value"] = True
            return TravelIntentResult(intent="casual_chat", confidence=0.8)

    fake_provider = _FakeProvider(Intent(action="unknown", confidence=0.0, payload={}, raw_text="x"))
    async def _fake_chat_response(message, text, send):
        await send("chat")
    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _CalledExtractor())
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(intent_router, "_resolve_active_trip", lambda session, message: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr(intent_router, "_chat_response", _fake_chat_response)

    msg = _DummyMessage("трейв привет", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert called["value"] is True


@pytest.mark.asyncio
async def test_invalid_extractor_result_safe_fallback(monkeypatch):
    class _UnknownExtractor:
        async def extract(self, *args, **kwargs):
            return TravelIntentResult.unknown()

    fake_provider = _FakeProvider(Intent(action="unknown", confidence=0.0, payload={}, raw_text="x"))
    async def _fake_chat_response(message, text, send):
        await send("chat")
    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _UnknownExtractor())
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(intent_router, "_resolve_active_trip", lambda session, message: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr(intent_router, "_chat_response", _fake_chat_response)

    msg = _DummyMessage("трейв привет", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True


def test_travel_intent_extractor_default_flag_is_false():
    from app.config import Settings

    s = Settings(_env_file=None)
    assert s.enable_travel_intent_extractor is False


@pytest.mark.asyncio
async def test_private_text_without_pending_routes_to_intent_handler(monkeypatch):
    from app.bot.handlers import private_router

    calls: list[tuple[str, str]] = []

    async def _fake_handle(message, text, *, source, use_reply=False):
        calls.append((text, source))
        return True

    private_router._pending_new_trip_titles.clear()
    monkeypatch.setattr("app.bot.intent_router.handle_intent_text", _fake_handle)
    msg = _DummyMessage("погода в москве завтра", chat_type="private")

    await private_router.private_natural_text(msg)
    assert calls == [("погода в москве завтра", "private")]
