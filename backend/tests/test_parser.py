import pytest

from app.ai.rule_based import RuleBasedProvider


@pytest.mark.asyncio
async def test_parse_paid_dinner_rub():
    p = RuleBasedProvider()
    intent = await p.parse_intent("я оплатил ужин 1200 рублей за всех")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200"
    assert intent.payload["currency"] == "RUB"
    assert intent.payload["split_all"] is True
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_paid_usd_for_two():
    p = RuleBasedProvider()
    intent = await p.parse_intent("Антон заплатил 300 usd за отель за меня и Настю")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "USD"
    assert intent.payload["amount"] == "300"


@pytest.mark.asyncio
async def test_parse_taxi_split_three():
    p = RuleBasedProvider()
    intent = await p.parse_intent("такси 30 GEL делим на троих")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "GEL"
    assert intent.payload["amount"] == "30"
    assert intent.payload["split_count"] == 3


@pytest.mark.asyncio
async def test_parse_convert():
    p = RuleBasedProvider()
    intent = await p.parse_intent("конвертируй 100 USD в RUB")
    assert intent.action == "convert_currency"
    assert intent.payload["from"] == "USD"
    assert intent.payload["to"] == "RUB"


@pytest.mark.asyncio
async def test_parse_balances():
    p = RuleBasedProvider()
    intent = await p.parse_intent("кто кому должен")
    assert intent.action == "show_balance"


@pytest.mark.asyncio
async def test_parse_unknown():
    p = RuleBasedProvider()
    intent = await p.parse_intent("привет, как дела?")
    assert intent.action == "unknown"


# Edge cases inspired by Nomad-Expense / Splitwise Telegram Bot reference review.

@pytest.mark.asyncio
async def test_parse_short_form_thb_coffee():
    p = RuleBasedProvider()
    intent = await p.parse_intent("100 THB Coffee")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "100"
    assert intent.payload["currency"] == "THB"
    assert intent.payload["title"].lower() == "coffee"
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_short_form_usd_lunch():
    p = RuleBasedProvider()
    intent = await p.parse_intent("50 USD lunch")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "USD"
    assert intent.payload["amount"] == "50"
    assert intent.payload["title"].lower() == "lunch"


@pytest.mark.asyncio
async def test_parse_short_form_ru_taxi():
    p = RuleBasedProvider()
    intent = await p.parse_intent("200р такси")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "RUB"
    assert intent.payload["amount"] == "200"
    assert "такси" in intent.payload["title"].lower()


@pytest.mark.asyncio
async def test_parse_amount_only_is_self_split():
    """'100 RUB' без verb/keyword/participants → add_expense scope=self
    (default split safety: только текущий пользователь, требуется
    confirmation)."""
    p = RuleBasedProvider()
    intent = await p.parse_intent("100 RUB")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "RUB"
    assert intent.payload["amount"] == "100"
    assert intent.payload["split_scope"] == "self"
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_two_numbers_returns_first_amount():
    """Defensive: parser should accept the first money match and not crash."""
    p = RuleBasedProvider()
    intent = await p.parse_intent("я оплатил 1200 рублей за ужин на 4 человек")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200"
    assert intent.payload["currency"] == "RUB"
    assert intent.payload["split_count"] == 4


@pytest.mark.asyncio
async def test_parse_decimal_amount_with_dot():
    p = RuleBasedProvider()
    intent = await p.parse_intent("я заплатил 12.50 EUR за круассан за всех")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "12.50"
    assert intent.payload["currency"] == "EUR"
    assert intent.payload["split_all"] is True


@pytest.mark.asyncio
async def test_parse_thousand_separator():
    p = RuleBasedProvider()
    intent = await p.parse_intent("я оплатил 1 200 рублей за ужин за всех")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200"
    assert intent.payload["currency"] == "RUB"


@pytest.mark.asyncio
async def test_parse_convert_arrow():
    p = RuleBasedProvider()
    intent = await p.parse_intent("convert 100 usd to rub")
    assert intent.action == "convert_currency"
    assert intent.payload["from"] == "USD"
    assert intent.payload["to"] == "RUB"
    assert intent.payload["amount"] == "100"


@pytest.mark.asyncio
async def test_parse_empty_text():
    p = RuleBasedProvider()
    intent = await p.parse_intent("")
    assert intent.action == "unknown"


@pytest.mark.asyncio
async def test_parse_find_document():
    p = RuleBasedProvider()
    intent = await p.parse_intent("найди бронь отеля")
    assert intent.action == "find_document"


@pytest.mark.asyncio
async def test_parse_thb_short_form():
    p = RuleBasedProvider()
    intent = await p.parse_intent("1 200 THB Coffee")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200"
    assert intent.payload["currency"] == "THB"
    assert "coffee" in intent.payload["title"].lower()
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_vnd_short_form():
    p = RuleBasedProvider()
    intent = await p.parse_intent("1 200 VND taxi")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200"
    assert intent.payload["currency"] == "VND"
    assert "taxi" in intent.payload["title"].lower()
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_gel_short_form():
    p = RuleBasedProvider()
    intent = await p.parse_intent("1 200 GEL dinner")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200"
    assert intent.payload["currency"] == "GEL"
    assert "dinner" in intent.payload["title"].lower()
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_short_form_without_title_self_split():
    """Голая сумма без описания → add_expense scope=self (default safety)."""
    p = RuleBasedProvider()
    intent = await p.parse_intent("100 RUB")
    assert intent.action == "add_expense"
    assert intent.payload["split_scope"] == "self"


@pytest.mark.parametrize(
    "raw,expected_currency",
    [
        ("1200000 VN D ресторан за всех", "VND"),
        ("100 US D Coffee", "USD"),
        ("500 RU B такси", "RUB"),
        ("30 GE L ужин на троих", "GEL"),
        ("100 TH B кофе", "THB"),
    ],
)
@pytest.mark.asyncio
async def test_parse_currency_typo_with_space(raw, expected_currency):
    """Mobile typo: код валюты разорван пробелом → парсер должен починить."""
    p = RuleBasedProvider()
    intent = await p.parse_intent(raw)
    assert intent.action == "add_expense", f"failed for: {raw}"
    assert intent.payload["currency"] == expected_currency


def test_normalize_does_not_fix_unknown_pair():
    """'EU and US' не должно превращаться в 'EUA US' — только known codes."""
    from app.ai.rule_based import _normalize_currency_typos

    assert _normalize_currency_typos("EU and US") == "EU and US"


def test_normalize_keeps_other_text_intact():
    from app.ai.rule_based import _normalize_currency_typos

    text = "я заплатил VN D за такси"
    assert _normalize_currency_typos(text) == "я заплатил VND за такси"


@pytest.mark.asyncio
async def test_parse_ai_command_phrase_recognized():
    """Текст для /ai команды передаётся в parser как есть."""
    p = RuleBasedProvider()
    intent = await p.parse_intent("я оплатил такси 300000 VND за всех")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "300000"
    assert intent.payload["currency"] == "VND"
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_expense_command_phrase_recognized():
    p = RuleBasedProvider()
    intent = await p.parse_intent("200 GEL ужин за всех")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "GEL"
    assert intent.payload["amount"] == "200"
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_ai_greeting_returns_unknown():
    p = RuleBasedProvider()
    intent = await p.parse_intent("привет")
    assert intent.action == "unknown"


@pytest.mark.asyncio
async def test_parse_kk_donghi_for_all():
    """1.2кк донгов = 1200000 VND."""
    p = RuleBasedProvider()
    intent = await p.parse_intent("ресторан 1.2кк донгов за всех")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "1200000"
    assert intent.payload["currency"] == "VND"
    assert intent.payload["split_scope"] == "all"
    assert intent.payload["category"] == "food"


@pytest.mark.asyncio
async def test_parse_baksov_with_zoe():
    """50 баксов с Зои = 50 USD, participants ['Зои']."""
    p = RuleBasedProvider()
    intent = await p.parse_intent("я заплатил за такси 50 баксов, ехали с Зои")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "50"
    assert intent.payload["currency"] == "USD"
    assert intent.payload["split_scope"] == "mentioned"
    assert intent.payload["participant_names"] == ["Зои"]
    assert intent.payload["category"] == "taxi"


@pytest.mark.asyncio
async def test_parse_skin_balance():
    p = RuleBasedProvider()
    intent = await p.parse_intent("скинь баланс")
    assert intent.action == "show_balance"
    assert intent.payload.get("scope") == "trip"


@pytest.mark.asyncio
async def test_parse_kto_komu_dolzhen():
    p = RuleBasedProvider()
    intent = await p.parse_intent("кто кому должен")
    assert intent.action == "show_balance"


@pytest.mark.asyncio
async def test_parse_skolko_potratili_segodnya():
    p = RuleBasedProvider()
    intent = await p.parse_intent("сколько мы потратили за сегодня")
    assert intent.action == "show_today_spending"
    assert intent.payload.get("date") == "today"


@pytest.mark.asyncio
async def test_parse_short_form_thb_coffee():
    p = RuleBasedProvider()
    intent = await p.parse_intent("100 THB Coffee")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "THB"


@pytest.mark.asyncio
async def test_parse_kk_no_decimals():
    p = RuleBasedProvider()
    intent = await p.parse_intent("ужин 2кк донгов за всех")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "2000000"
    assert intent.payload["currency"] == "VND"


@pytest.mark.asyncio
async def test_parse_50k_thb():
    p = RuleBasedProvider()
    intent = await p.parse_intent("50k THB hotel за всех")
    assert intent.action == "add_expense"
    assert intent.payload["amount"] == "50000"
    assert intent.payload["currency"] == "THB"
    assert intent.payload["category"] == "hotel"


# --- TRY / Turkish lira tests ---


@pytest.mark.parametrize(
    "raw,expected_amount",
    [
        ("ресторан 1200 лир за всех", "1200"),
        ("такси 500 лир с Зои", "500"),
        ("кофе 250 TRY за всех", "250"),
        ("отель 100 лиры за всех", "100"),
        ("500 турецких лир", "500"),
    ],
)
@pytest.mark.asyncio
async def test_parse_try_aliases(raw, expected_amount):
    p = RuleBasedProvider()
    intent = await p.parse_intent(raw)
    assert intent.action == "add_expense", f"failed for: {raw}"
    assert intent.payload["currency"] == "TRY"
    assert intent.payload["amount"] == expected_amount
    assert intent.needs_confirmation is True


@pytest.mark.asyncio
async def test_parse_try_symbol_prefix():
    p = RuleBasedProvider()
    intent = await p.parse_intent("₺250 за всех")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "TRY"
    assert intent.payload["amount"] == "250"
    assert intent.payload["split_scope"] == "all"


@pytest.mark.asyncio
async def test_parse_try_with_zoe_mentioned():
    p = RuleBasedProvider()
    intent = await p.parse_intent("такси 500 лир с Зои")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "TRY"
    assert intent.payload["split_scope"] == "mentioned"
    assert intent.payload["participant_names"] == ["Зои"]


# --- default split safety ---


@pytest.mark.asyncio
async def test_parse_paid_verb_without_split_keyword_self():
    """Verb «оплатил/заплатил» без явного split keyword → scope=self.
    Защита от автоматического деления на всех при неоднозначном вводе."""
    p = RuleBasedProvider()
    intent = await p.parse_intent("я заплатил за такси 50 баксов")
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "USD"
    assert intent.payload["split_scope"] == "self"
    assert intent.payload["split_all"] is False


@pytest.mark.asyncio
async def test_parse_explicit_split_all_overrides_self():
    p = RuleBasedProvider()
    intent = await p.parse_intent("я заплатил такси 50 баксов за всех")
    assert intent.payload["split_scope"] == "all"


@pytest.mark.asyncio
async def test_parse_explicit_with_zoe_overrides_self():
    p = RuleBasedProvider()
    intent = await p.parse_intent("я заплатил такси 50 баксов с Зои")
    assert intent.payload["split_scope"] == "mentioned"
    assert intent.payload["participant_names"] == ["Зои"]


@pytest.mark.asyncio
async def test_parse_show_balance_simple():
    p = RuleBasedProvider()
    intent = await p.parse_intent("скинь баланс")
    assert intent.action == "show_balance"


@pytest.mark.asyncio
async def test_parse_show_today_spending_simple():
    p = RuleBasedProvider()
    intent = await p.parse_intent("сколько потратили сегодня")
    assert intent.action == "show_today_spending"
