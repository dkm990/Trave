from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.ai.base import Intent
from app.ai.mimo_provider import MimoProvider
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
    return SimpleNamespace(
        enable_travel_intent_extractor=enabled,
        conversational_provider_order="mimo,gemini",
        mimo_api_key="mimo-key",
        mimo_base_url="https://token-plan-sgp.xiaomimimo.com/v1",
        mimo_model="mimo-v2.5-pro",
        mimo_timeout_seconds=5,
        mimo_retry_count=0,
        mimo_auth_header="api-key",
        mimo_extraction_mode="tool_call",
        mimo_max_completion_tokens=512,
        mimo_temperature=0.3,
        mimo_top_p=0.95,
        gemini_api_key="gemini-key",
    )


def _weather_payload(*, location: str, surface: str | None, period: str, date_text: str | None = None, days: int | None = None):
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


def test_flat_mimo_json_is_parsed_tolerantly():
    service = TravelIntentService()
    parsed = service._parse_response(
        json.dumps(
            {
                "intent": "weather",
                "confidence": 0.95,
                "location": "Стамбул",
                "location_surface": "в Стамбуле",
                "period_type": "exact_date",
                "date_text": "4 июня",
                "days": None,
                "asks_rain": None,
            },
            ensure_ascii=False,
        )
    )

    assert parsed is not None
    assert parsed.intent == "weather"
    assert parsed.weather.location == "Стамбул"
    assert parsed.weather.period_type == "exact_date"


@pytest.mark.asyncio
async def test_mimo_provider_builds_tool_call_request(monkeypatch):
    captured: dict = {}

    class _Response:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "extract_travel_intent",
                                        "arguments": json.dumps(
                                            {
                                                "intent": "weather",
                                                "confidence": 0.9,
                                                "weather": {"location": "Istanbul"},
                                                "expense": {},
                                            }
                                        ),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Response()

    monkeypatch.setattr("app.ai.mimo_provider.httpx.AsyncClient", _Client)
    provider = MimoProvider(
        api_key="secret-token",
        base_url="https://token-plan-sgp.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        timeout_seconds=5,
        retry_count=0,
    )
    out = await provider.generate_json(system_instruction="sys", prompt="hello")

    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "mimo-v2.5-pro"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1]["role"] == "user"
    assert captured["json"]["max_completion_tokens"] == 512
    assert captured["json"]["stream"] is False
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["json"]["temperature"] == 0.3
    assert captured["json"]["top_p"] == 0.95
    assert captured["json"]["tools"][0]["function"]["name"] == "extract_travel_intent"
    assert captured["json"]["tool_choice"] == {
        "type": "function",
        "function": {"name": "extract_travel_intent"},
    }
    assert captured["headers"]["api-key"] == "secret-token"
    assert "Authorization" not in captured["headers"]
    assert "weather" in out


@pytest.mark.asyncio
async def test_mimo_provider_can_use_bearer_header(monkeypatch):
    captured: dict = {}

    class _Response:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '{"intent":"unknown"}'}}]}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers=None, json=None):
            captured["headers"] = headers
            return _Response()

    monkeypatch.setattr("app.ai.mimo_provider.httpx.AsyncClient", _Client)
    provider = MimoProvider(
        api_key="secret-token",
        base_url="https://token-plan-sgp.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        auth_header="bearer",
        extraction_mode="json_object",
    )
    await provider.generate_json(system_instruction="sys", prompt="hello")

    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert "api-key" not in captured["headers"]


@pytest.mark.asyncio
async def test_mimo_valid_json_used_without_gemini(monkeypatch):
    service = TravelIntentService()
    service.settings = SimpleNamespace(
        travel_intent_provider_order="mimo,gemini",
        mimo_api_key="k",
        mimo_base_url="https://x/v1",
        mimo_model="mimo",
        mimo_timeout_seconds=5,
        mimo_retry_count=0,
        gemini_api_key="g",
        gemini_model="gemini-2.5-flash",
        travel_intent_timeout_seconds=5,
        travel_intent_retry_count=0,
    )
    calls = {"mimo": 0, "gemini": 0}

    async def _mimo(*, system_instruction: str, prompt: str) -> str:
        calls["mimo"] += 1
        return json.dumps(_weather_payload(location="Istanbul", surface="in Istanbul", period="today"))

    class _FakeMimo:
        generate_json = staticmethod(_mimo)

    service._mimo_provider = _FakeMimo()  # type: ignore[assignment]
    monkeypatch.setattr(service, "_init_mimo_provider", lambda: service._mimo_provider)

    async def _gemini(client, prompt):
        calls["gemini"] += 1
        return "{}"

    monkeypatch.setattr(service, "_call_gemini", _gemini)
    monkeypatch.setattr(service, "_init_gemini_client", lambda: object())

    out = await service.extract("weather in istanbul", chat_context="group", current_dt=datetime.now())
    assert out.intent == "weather"
    assert out.provider == "mimo"
    assert calls["mimo"] == 1
    assert calls["gemini"] == 0


@pytest.mark.asyncio
async def test_mimo_invalid_json_falls_back_to_gemini(monkeypatch):
    service = TravelIntentService()
    service.settings = SimpleNamespace(
        travel_intent_provider_order="mimo,gemini",
        mimo_api_key="k",
        mimo_base_url="https://x/v1",
        mimo_model="mimo",
        mimo_timeout_seconds=5,
        mimo_retry_count=0,
        gemini_api_key="g",
        gemini_model="gemini-2.5-flash",
        travel_intent_timeout_seconds=5,
        travel_intent_retry_count=0,
    )

    class _FakeMimo:
        @staticmethod
        async def generate_json(*, system_instruction: str, prompt: str) -> str:
            return "{not-json"

    service._mimo_provider = _FakeMimo()  # type: ignore[assignment]
    monkeypatch.setattr(service, "_init_mimo_provider", lambda: service._mimo_provider)
    monkeypatch.setattr(service, "_init_gemini_client", lambda: object())
    monkeypatch.setattr(
        service,
        "_call_gemini",
        lambda client, prompt: asyncio.sleep(
            0,
            result=json.dumps(_weather_payload(location="Moscow", surface="in Moscow", period="tomorrow")),
        ),
    )

    out = await service.extract("weather", chat_context="group", current_dt=datetime.now())
    assert out.intent == "weather"
    assert out.provider == "gemini"


@pytest.mark.asyncio
async def test_mimo_429_falls_back_to_gemini(monkeypatch):
    service = TravelIntentService()
    service.settings = SimpleNamespace(
        travel_intent_provider_order="mimo,gemini",
        mimo_api_key="k",
        mimo_base_url="https://x/v1",
        mimo_model="mimo",
        mimo_timeout_seconds=5,
        mimo_retry_count=0,
        gemini_api_key="g",
        gemini_model="gemini-2.5-flash",
        travel_intent_timeout_seconds=5,
        travel_intent_retry_count=0,
    )

    class _FakeMimo:
        @staticmethod
        async def generate_json(*, system_instruction: str, prompt: str) -> str:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    service._mimo_provider = _FakeMimo()  # type: ignore[assignment]
    monkeypatch.setattr(service, "_init_mimo_provider", lambda: service._mimo_provider)
    monkeypatch.setattr(service, "_init_gemini_client", lambda: object())
    monkeypatch.setattr(
        service,
        "_call_gemini",
        lambda client, prompt: asyncio.sleep(
            0,
            result=json.dumps(_weather_payload(location="Bali", surface="on Bali", period="week", days=7)),
        ),
    )

    out = await service.extract("weather", chat_context="group", current_dt=datetime.now())
    assert out.intent == "weather"
    assert out.provider == "gemini"


@pytest.mark.asyncio
async def test_mimo_timeout_falls_back_to_gemini(monkeypatch):
    service = TravelIntentService()
    service.settings = SimpleNamespace(
        travel_intent_provider_order="mimo,gemini",
        mimo_api_key="k",
        mimo_base_url="https://x/v1",
        mimo_model="mimo",
        mimo_timeout_seconds=5,
        mimo_retry_count=0,
        gemini_api_key="g",
        gemini_model="gemini-2.5-flash",
        travel_intent_timeout_seconds=5,
        travel_intent_retry_count=0,
    )

    class _FakeMimo:
        @staticmethod
        async def generate_json(*, system_instruction: str, prompt: str) -> str:
            raise TimeoutError("timeout")

    service._mimo_provider = _FakeMimo()  # type: ignore[assignment]
    monkeypatch.setattr(service, "_init_mimo_provider", lambda: service._mimo_provider)
    monkeypatch.setattr(service, "_init_gemini_client", lambda: object())
    monkeypatch.setattr(
        service,
        "_call_gemini",
        lambda client, prompt: asyncio.sleep(
            0,
            result=json.dumps(_weather_payload(location="Moscow", surface="in Moscow", period="tomorrow")),
        ),
    )

    out = await service.extract("weather", chat_context="group", current_dt=datetime.now())
    assert out.intent == "weather"
    assert out.provider == "gemini"


@pytest.mark.asyncio
async def test_both_fail_return_unknown(monkeypatch):
    service = TravelIntentService()
    service.settings = SimpleNamespace(
        travel_intent_provider_order="mimo,gemini",
        mimo_api_key="k",
        mimo_base_url="https://x/v1",
        mimo_model="mimo",
        mimo_timeout_seconds=5,
        mimo_retry_count=0,
        gemini_api_key="g",
        gemini_model="gemini-2.5-flash",
        travel_intent_timeout_seconds=5,
        travel_intent_retry_count=0,
    )

    class _FakeMimo:
        @staticmethod
        async def generate_json(*, system_instruction: str, prompt: str) -> str:
            raise RuntimeError("503 UNAVAILABLE")

    service._mimo_provider = _FakeMimo()  # type: ignore[assignment]
    monkeypatch.setattr(service, "_init_mimo_provider", lambda: service._mimo_provider)
    monkeypatch.setattr(service, "_init_gemini_client", lambda: object())
    monkeypatch.setattr(service, "_call_gemini", lambda client, prompt: asyncio.sleep(0, result="{broken"))

    out = await service.extract("weather", chat_context="group", current_dt=datetime.now())
    assert out.intent == "unknown"
    assert out.provider is None


@pytest.mark.asyncio
async def test_api_key_not_logged(monkeypatch, caplog):
    secret = "mimo-super-secret-token"
    service = TravelIntentService()
    service.settings = SimpleNamespace(
        travel_intent_provider_order="mimo",
        mimo_api_key=secret,
        mimo_base_url="https://x/v1",
        mimo_model="mimo",
        mimo_timeout_seconds=5,
        mimo_retry_count=0,
        gemini_api_key="",
        gemini_model="gemini-2.5-flash",
        travel_intent_timeout_seconds=5,
        travel_intent_retry_count=0,
    )

    class _FakeMimo:
        @staticmethod
        async def generate_json(*, system_instruction: str, prompt: str) -> str:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    service._mimo_provider = _FakeMimo()  # type: ignore[assignment]
    monkeypatch.setattr(service, "_init_mimo_provider", lambda: service._mimo_provider)

    with caplog.at_level(logging.WARNING):
        _ = await service.extract("test", chat_context="group", current_dt=datetime.now())

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert secret not in log_text


@pytest.mark.asyncio
async def test_expense_like_text_still_uses_existing_parser(monkeypatch):
    calls: list[str] = []

    async def _fake_propose(message, intent, *, source, use_reply=False):
        calls.append(intent.action)

    fake_provider = _FakeProvider(
        Intent(
            action="add_expense",
            confidence=0.9,
            payload={"amount": "400", "currency": "TRY", "title": "taxi", "split_scope": "self"},
            raw_text="trave 400 try taxi",
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
    monkeypatch.setattr(intent_router, "_resolve_active_trip", lambda session, message: asyncio.sleep(0, result=None))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _NeverCalledExtractor())
    monkeypatch.setattr("app.bot.handlers.expenses.propose_expense_from_intent", _fake_propose)

    msg = _DummyMessage("trave 400 try taxi", chat_type="group")
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
        weather=TravelWeatherIntent(location="Istanbul", location_surface="in Istanbul", period_type="days", days=2),
    )

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_weather", _fake_weather)
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(intent_router, "_resolve_active_trip", lambda session, message: asyncio.sleep(0, result=None))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _FakeExtractor(extracted))

    msg = _DummyMessage("weather in istanbul for 2 days", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert weather_calls
    assert weather_calls[0][0] == "Istanbul"
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

    msg = _DummyMessage("hello", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert called["value"] is False


@pytest.mark.asyncio
async def test_weather_message_calls_travel_intent_extractor(monkeypatch):
    called = {"value": False}

    class _CalledExtractor:
        async def extract(self, *args, **kwargs):
            called["value"] = True
            return TravelIntentResult(
                intent="weather",
                confidence=0.8,
                weather=TravelWeatherIntent(location="Istanbul", period_type="today"),
            )

    fake_provider = _FakeProvider(Intent(action="unknown", confidence=0.0, payload={}, raw_text="x"))

    async def _fake_weather(city, **kwargs):
        return "weather"

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _CalledExtractor())
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "get_weather", _fake_weather)
    monkeypatch.setattr(intent_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(intent_router, "_resolve_active_trip", lambda session, message: asyncio.sleep(0, result=None))

    msg = _DummyMessage("weather in istanbul", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert called["value"] is True


@pytest.mark.asyncio
async def test_casual_message_uses_direct_chat_without_extractor(monkeypatch):
    called = {"extractor": False, "chat": False}

    class _ShouldNotBeCalled:
        async def extract(self, *args, **kwargs):
            called["extractor"] = True
            return TravelIntentResult.unknown()

    fake_provider = _FakeProvider(Intent(action="unknown", confidence=0.0, payload={}, raw_text="x"))

    async def _fake_chat_response(message, text, send):
        called["chat"] = True
        await send("chat")

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _ShouldNotBeCalled())
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "_chat_response", _fake_chat_response)

    msg = _DummyMessage("чем заняться в Турции?", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert called == {"extractor": False, "chat": True}


@pytest.mark.asyncio
async def test_esim_question_uses_direct_chat_without_extractor(monkeypatch):
    called = {"extractor": False, "chat": False}

    class _ShouldNotBeCalled:
        async def extract(self, *args, **kwargs):
            called["extractor"] = True
            return TravelIntentResult.unknown()

    async def _fake_chat_response(message, text, send):
        called["chat"] = True
        await send("chat")

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _ShouldNotBeCalled())
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: _FakeProvider(Intent(action="unknown")))
    monkeypatch.setattr(intent_router, "_chat_response", _fake_chat_response)

    msg = _DummyMessage("какие eSIM взять в Турции?", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert called == {"extractor": False, "chat": True}


@pytest.mark.asyncio
async def test_private_casual_text_uses_direct_chat_without_extractor(monkeypatch):
    called = {"extractor": False, "chat": False}

    class _ShouldNotBeCalled:
        async def extract(self, *args, **kwargs):
            called["extractor"] = True
            return TravelIntentResult.unknown()

    async def _fake_chat_response(message, text, send):
        called["chat"] = True
        await send("chat")

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _ShouldNotBeCalled())
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: _FakeProvider(Intent(action="unknown")))
    monkeypatch.setattr(intent_router, "_chat_response", _fake_chat_response)

    msg = _DummyMessage("привет, чем занят?", chat_type="private")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="private", use_reply=False)
    assert ok is True
    assert called == {"extractor": False, "chat": True}


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
    msg = _DummyMessage("weather in moscow tomorrow", chat_type="private")

    await private_router.private_natural_text(msg)
    assert calls == [("weather in moscow tomorrow", "private")]


def test_chat_response_sanitizer_removes_raw_markdown():
    text = intent_router._sanitize_chat_response("### План\n**Первое**\n\n\n__Второе__")
    assert "###" not in text
    assert "**" not in text
    assert "__" not in text
    assert "План" in text


@pytest.mark.asyncio
async def test_travel_advice_uses_mimo_chat_first(monkeypatch):
    calls: list[str] = []

    async def _mimo(text, *, context="", trip_info=""):
        calls.append("mimo")
        return "**Проверь район**, возьми наличные."

    async def _gemini(text, *, context="", trip_info=""):
        calls.append("gemini")
        return "gemini"

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "_generate_mimo_chat_response", _mimo)
    monkeypatch.setattr(intent_router, "_generate_gemini_chat_response", _gemini)

    out = await intent_router._generate_conversational_response("чем заняться в Турции?")
    assert calls == ["mimo"]
    assert "**" not in out
    assert "Проверь район" in out


@pytest.mark.asyncio
async def test_casual_chat_uses_mimo_first(monkeypatch):
    calls: list[str] = []

    async def _mimo(text, *, context="", trip_info=""):
        calls.append("mimo")
        return "Я на связи."

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "_generate_mimo_chat_response", _mimo)

    out = await intent_router._generate_conversational_response("привет")
    assert calls == ["mimo"]
    assert out == "Я на связи."


@pytest.mark.asyncio
async def test_mimo_chat_failure_falls_back_to_gemini(monkeypatch):
    calls: list[str] = []

    async def _mimo(text, *, context="", trip_info=""):
        calls.append("mimo")
        raise RuntimeError("timeout")

    async def _gemini(text, *, context="", trip_info=""):
        calls.append("gemini")
        return "Ответ Gemini"

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "_generate_mimo_chat_response", _mimo)
    monkeypatch.setattr(intent_router, "_generate_gemini_chat_response", _gemini)

    out = await intent_router._generate_conversational_response("какие eSIM взять?")
    assert calls == ["mimo", "gemini"]
    assert out == "Ответ Gemini"


@pytest.mark.asyncio
async def test_gemini_429_after_mimo_failure_returns_safe_fallback(monkeypatch):
    async def _mimo(text, *, context="", trip_info=""):
        raise RuntimeError("timeout")

    async def _gemini(text, *, context="", trip_info=""):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "_generate_mimo_chat_response", _mimo)
    monkeypatch.setattr(intent_router, "_generate_gemini_chat_response", _gemini)

    out = await intent_router._generate_conversational_response("какие eSIM взять?")
    assert out == intent_router.CHAT_SAFE_FALLBACK


@pytest.mark.asyncio
async def test_weather_path_does_not_call_chat_provider(monkeypatch):
    weather_calls: list[str] = []
    chat_called = {"value": False}

    async def _fake_weather(city, **kwargs):
        weather_calls.append(city)
        return "weather"

    async def _chat(*args, **kwargs):
        chat_called["value"] = True
        return "chat"

    fake_provider = _FakeProvider(Intent(action="unknown", confidence=0.0, payload={}, raw_text="x"))
    extracted = TravelIntentResult(
        intent="weather",
        confidence=0.9,
        weather=TravelWeatherIntent(location="Istanbul", period_type="today"),
    )

    monkeypatch.setattr(intent_router, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(intent_router, "get_weather", _fake_weather)
    monkeypatch.setattr(intent_router, "get_ai_provider", lambda: fake_provider)
    monkeypatch.setattr(intent_router, "session_scope", lambda: _DummyScope())
    monkeypatch.setattr(intent_router, "_resolve_active_trip", lambda session, message: asyncio.sleep(0, result=None))
    monkeypatch.setattr(intent_router, "get_travel_intent_service", lambda: _FakeExtractor(extracted))
    monkeypatch.setattr(intent_router, "_generate_conversational_response", _chat)

    msg = _DummyMessage("weather in istanbul", chat_type="group")
    ok = await intent_router.handle_intent_text(msg, msg.text, source="trigger", use_reply=True)
    assert ok is True
    assert weather_calls == ["Istanbul"]
    assert chat_called["value"] is False
