"""Unit tests для group mention/reply detection и strip_mention."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.filters import (
    GroupAddressedFilter,
    _is_mentioned,
    _is_reply_to_bot,
    strip_mention,
)


# --- strip_mention ---


def test_strip_mention_exact_username():
    assert strip_mention("@Trave0Bot я оплатил такси", "trave0bot") == "я оплатил такси"


def test_strip_mention_lowercase_username():
    assert strip_mention("@trave0bot я оплатил", "trave0bot") == "я оплатил"


def test_strip_mention_uppercase_username():
    assert strip_mention("@TRAVE0BOT я оплатил", "trave0bot") == "я оплатил"


def test_strip_mention_in_middle_of_text():
    assert strip_mention("привет @Trave0Bot всем", "trave0bot") == "привет  всем".strip()


def test_strip_mention_does_not_touch_other_usernames():
    assert (
        strip_mention("@SomeOther @Trave0Bot привет", "trave0bot")
        == "@SomeOther  привет".strip()
    )


def test_strip_mention_empty_username_returns_text_as_is():
    assert strip_mention("привет всем", "") == "привет всем"


# --- _is_mentioned ---


def _msg(text: str, entities=None, caption: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        caption=caption,
        entities=entities,
        caption_entities=None,
    )


def _entity(text: str, sub: str, type_="mention"):
    """SimpleNamespace, имитирующий aiogram MessageEntity."""
    offset = text.find(sub)
    return SimpleNamespace(type=type_, offset=offset, length=len(sub))


def test_mention_via_entity_lowercase():
    text = "@trave0bot я оплатил такси"
    msg = _msg(text, entities=[_entity(text, "@trave0bot")])
    assert _is_mentioned(msg, "trave0bot") is True


def test_mention_via_entity_mixed_case():
    text = "@Trave0Bot я оплатил такси"
    msg = _msg(text, entities=[_entity(text, "@Trave0Bot")])
    assert _is_mentioned(msg, "trave0bot") is True


def test_mention_via_regex_when_no_entity():
    text = "Эй, @trave0bot — добавь расход"
    msg = _msg(text, entities=[])
    assert _is_mentioned(msg, "trave0bot") is True


def test_no_mention_for_other_username():
    text = "@SomeOther привет"
    msg = _msg(text, entities=[_entity(text, "@SomeOther")])
    assert _is_mentioned(msg, "trave0bot") is False


def test_no_mention_for_substring_match_inside_word():
    text = "@trave0botxyz привет"
    msg = _msg(text, entities=[])
    assert _is_mentioned(msg, "trave0bot") is False


def test_no_mention_when_text_empty():
    msg = _msg("", entities=[])
    assert _is_mentioned(msg, "trave0bot") is False


# --- _is_reply_to_bot ---


def test_reply_to_bot_detected():
    bot_id = 8841451417
    reply = SimpleNamespace(from_user=SimpleNamespace(id=bot_id))
    msg = SimpleNamespace(reply_to_message=reply)
    assert _is_reply_to_bot(msg, bot_id) is True


def test_reply_to_other_user_not_bot():
    bot_id = 8841451417
    reply = SimpleNamespace(from_user=SimpleNamespace(id=999))
    msg = SimpleNamespace(reply_to_message=reply)
    assert _is_reply_to_bot(msg, bot_id) is False


def test_no_reply_at_all():
    msg = SimpleNamespace(reply_to_message=None)
    assert _is_reply_to_bot(msg, 1) is False


# --- GroupAddressedFilter integration ---


class _FakeBot:
    def __init__(self, username="trave0bot", uid=8841451417):
        self._me = SimpleNamespace(username=username, id=uid)

    async def me(self):
        return self._me


def _full_msg(text="", chat_type="supergroup", reply_user_id=None, entities=None):
    reply = None
    if reply_user_id is not None:
        reply = SimpleNamespace(from_user=SimpleNamespace(id=reply_user_id))
    return SimpleNamespace(
        text=text,
        caption=None,
        entities=entities,
        caption_entities=None,
        chat=SimpleNamespace(type=chat_type),
        reply_to_message=reply,
    )


@pytest.mark.asyncio
async def test_filter_passes_in_private():
    f = GroupAddressedFilter()
    msg = _full_msg(text="anything", chat_type="private")
    assert await f(msg, _FakeBot()) is True


@pytest.mark.asyncio
async def test_filter_passes_on_mention_lowercase():
    f = GroupAddressedFilter()
    text = "@trave0bot я оплатил такси 300000 VND за всех"
    msg = _full_msg(text=text, entities=[_entity(text, "@trave0bot")])
    assert await f(msg, _FakeBot()) is True


@pytest.mark.asyncio
async def test_filter_passes_on_mention_uppercase():
    f = GroupAddressedFilter()
    text = "@TRAVE0BOT я оплатил такси"
    msg = _full_msg(text=text, entities=[])
    assert await f(msg, _FakeBot()) is True


@pytest.mark.asyncio
async def test_filter_passes_on_reply_to_bot():
    f = GroupAddressedFilter()
    msg = _full_msg(text="я оплатил 100 RUB ужин", reply_user_id=8841451417)
    assert await f(msg, _FakeBot()) is True


@pytest.mark.asyncio
async def test_filter_blocks_random_group_message():
    f = GroupAddressedFilter()
    msg = _full_msg(text="всем привет, как дела")
    assert await f(msg, _FakeBot()) is False


@pytest.mark.asyncio
async def test_filter_blocks_other_bot_mention():
    f = GroupAddressedFilter()
    text = "@otherbot привет"
    msg = _full_msg(text=text, entities=[_entity(text, "@otherbot")])
    assert await f(msg, _FakeBot()) is False


# --- end-to-end через rule_based parser ---


@pytest.mark.asyncio
async def test_mention_text_after_strip_parses_as_expense():
    """После strip_mention парсер видит 'я оплатил такси 300000 VND за всех'
    и распознаёт его как add_expense с обязательным confirmation."""
    from app.ai.rule_based import RuleBasedProvider

    raw = "@Trave0Bot я оплатил такси 300000 VND за всех"
    cleaned = strip_mention(raw, "trave0bot")
    intent = await RuleBasedProvider().parse_intent(cleaned)
    assert intent.action == "add_expense"
    assert intent.payload["currency"] == "VND"
    assert intent.payload["amount"] == "300000"
    assert intent.needs_confirmation is True


# --- trigger words tests ---

from app.bot.filters import starts_with_trigger, strip_trigger


def test_trigger_traev_comma():
    assert starts_with_trigger("Трейв, кто кому должен?") is True
    assert strip_trigger("Трейв, кто кому должен?") == "кто кому должен?"


def test_trigger_travelbot_no_at():
    assert starts_with_trigger("TravelBot скинь баланс") is True
    assert strip_trigger("TravelBot скинь баланс") == "скинь баланс"


def test_trigger_bot_lowercase_with_comma():
    assert starts_with_trigger("бот, скинь баланс") is True
    assert strip_trigger("бот, скинь баланс") == "скинь баланс"


def test_trigger_does_not_match_botany():
    assert starts_with_trigger("боты дома сидят") is False
    assert starts_with_trigger("ботаник пишет код") is False


def test_trigger_travel_word_boundary():
    assert starts_with_trigger("Travelman вышел из чата") is False


def test_trigger_in_middle_not_match():
    assert starts_with_trigger("привет Трейв") is False


@pytest.mark.asyncio
async def test_filter_passes_on_trigger_word():
    f = GroupAddressedFilter()
    msg = _full_msg(text="Трейв, кто кому должен?")
    assert await f(msg, _FakeBot()) is True


@pytest.mark.asyncio
async def test_filter_blocks_normal_group_text_no_trigger():
    """С privacy disabled бот видит обычные сообщения, но без trigger
    мы их не обрабатываем."""
    f = GroupAddressedFilter()
    msg = _full_msg(text="как там погода в Ханое")
    assert await f(msg, _FakeBot()) is False
