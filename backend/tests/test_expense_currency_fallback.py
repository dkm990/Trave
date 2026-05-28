from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.ai.rule_based import RuleBasedProvider


@pytest.mark.asyncio
async def test_parser_extracts_explicit_currency():
    provider = RuleBasedProvider()
    intent = await provider.parse_intent("Трейв, 500 рублей такси")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "500"
    assert intent.payload["currency"] == "RUB"


@pytest.mark.asyncio
async def test_parser_extracts_try_from_лир():
    provider = RuleBasedProvider()
    intent = await provider.parse_intent("Трейв, 400 лир такси")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "400"
    assert intent.payload["currency"] == "TRY"


@pytest.mark.asyncio
async def test_parser_returns_expense_with_none_currency_when_missing():
    provider = RuleBasedProvider()
    intent = await provider.parse_intent("я оплатил кофе 500")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "500"
    assert intent.payload.get("currency") is None


@pytest.mark.asyncio
async def test_parser_returns_expense_with_none_currency_paid_verb():
    provider = RuleBasedProvider()
    intent = await provider.parse_intent("оплатил ужин 1200")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200"
    assert intent.payload.get("currency") is None
