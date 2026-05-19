"""Tests for GeminiProvider — без реальных HTTP вызовов.

Подменяем `_call_gemini` на async stub, чтобы проверить парсинг JSON,
fallback при invalid response, и retry-логику.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai.base import Intent
from app.ai.gemini_provider import GeminiProvider
from app.ai.rule_based import RuleBasedProvider


class _FakeFallback(RuleBasedProvider):
    name = "fake_fallback"

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def parse_intent(self, text: str, *, context: dict | None = None) -> Intent:
        self.calls += 1
        return await super().parse_intent(text, context=context)


def _make_provider(call_results: list, fallback: _FakeFallback | None = None) -> GeminiProvider:
    fb = fallback or _FakeFallback()
    p = GeminiProvider(fallback=fb)
    p._client = object()  # пропускаем _init_client

    queue = list(call_results)

    async def fake_call(client, text):
        if not queue:
            raise RuntimeError("queue empty")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if item == "TIMEOUT":
            await asyncio.sleep(p.settings.gemini_timeout_seconds + 1)
            return ""
        return item

    p._call_gemini = fake_call  # type: ignore[assignment]
    return p


@pytest.mark.asyncio
async def test_gemini_add_expense_kk_donghi():
    payload = json.dumps({
        "action": "add_expense",
        "confidence": 0.9,
        "needs_confirmation": True,
        "payload": {
            "amount": "1200000",
            "currency": "VND",
            "title": "ресторан",
            "split_scope": "all",
            "category": "food",
            "participant_names": None,
        },
    })
    p = _make_provider([payload])
    intent = await p.parse_intent("ресторан 1.2кк донгов за всех")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200000"
    assert intent.payload["currency"] == "VND"
    assert intent.payload["split_scope"] == "all"
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_gemini_taxi_with_zoe():
    payload = json.dumps({
        "action": "add_expense",
        "confidence": 0.85,
        "needs_confirmation": True,
        "payload": {
            "amount": "50",
            "currency": "USD",
            "title": "такси",
            "split_scope": "mentioned",
            "category": "taxi",
            "participant_names": ["Зои"],
        },
    })
    p = _make_provider([payload])
    intent = await p.parse_intent("я заплатил за такси 50 баксов, ехали с Зои")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "USD"
    assert intent.payload["split_scope"] == "mentioned"
    assert intent.payload["participant_names"] == ["Зои"]


@pytest.mark.asyncio
async def test_gemini_show_balance():
    payload = json.dumps({
        "action": "show_balance",
        "confidence": 0.9,
        "needs_confirmation": False,
        "payload": {"scope": "trip"},
    })
    p = _make_provider([payload])
    intent = await p.parse_intent("скинь баланс")
    assert intent.action == "show_balance"
    assert intent.payload["scope"] == "trip"
    assert intent.needs_confirmation is False


@pytest.mark.asyncio
async def test_gemini_show_today_spending():
    payload = json.dumps({
        "action": "show_today_spending",
        "confidence": 0.9,
        "needs_confirmation": False,
        "payload": {"date": "today", "group_by": "category"},
    })
    p = _make_provider([payload])
    intent = await p.parse_intent("сколько мы потратили за сегодня")
    assert intent.action == "show_today_spending"
    assert intent.payload["date"] == "today"


@pytest.mark.asyncio
async def test_gemini_invalid_json_fallback():
    fb = _FakeFallback()
    p = _make_provider(["NOT A JSON", "STILL NOT JSON"], fallback=fb)
    intent = await p.parse_intent("я оплатил такси 300000 VND за всех")
    assert fb.calls == 1
    assert intent.action == "add_expense"


@pytest.mark.asyncio
async def test_gemini_first_attempt_throws_then_succeeds():
    payload = json.dumps({
        "action": "show_balance",
        "confidence": 0.9,
        "needs_confirmation": False,
        "payload": {"scope": "trip"},
    })
    p = _make_provider([RuntimeError("transient 5xx"), payload])
    intent = await p.parse_intent("кто кому должен")
    assert intent.action == "show_balance"


@pytest.mark.asyncio
async def test_gemini_two_failures_then_fallback():
    fb = _FakeFallback()
    p = _make_provider(
        [RuntimeError("network"), RuntimeError("network 2")],
        fallback=fb,
    )
    intent = await p.parse_intent("кто кому должен")
    assert fb.calls == 1
    assert intent.action == "show_balance"


@pytest.mark.asyncio
async def test_gemini_429_retry_once():
    payload = json.dumps({
        "action": "show_balance",
        "confidence": 0.9,
        "needs_confirmation": False,
        "payload": {"scope": "trip"},
    })
    err = RuntimeError("429 Too Many Requests")
    p = _make_provider([err, payload])
    intent = await p.parse_intent("баланс")
    assert intent.action == "show_balance"


@pytest.mark.asyncio
async def test_gemini_empty_api_key_uses_fallback():
    fb = _FakeFallback()
    p = GeminiProvider(fallback=fb)
    p.settings.gemini_api_key = ""
    p._client = None
    p._client_init_failed = False
    intent = await p.parse_intent("скинь баланс")
    assert fb.calls == 1
    assert intent.action == "show_balance"
