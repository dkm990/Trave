from __future__ import annotations

import re

from aiogram import Bot
from aiogram.enums import ChatType, MessageEntityType
from aiogram.filters import BaseFilter
from aiogram.types import Message


# Trigger words в начале сообщения, при которых бот в группе обрабатывает
# текст как обращение. Сравнение case-insensitive.
TRIGGER_WORDS = (
    "Трейв",
    "Тревел",
    "TravelBot",
    "Travel",
    "Yo",
)
# "бот," и "бот " — отдельно, чтобы не ловить "роботы" / "ботаник".
TRIGGER_PREFIXES = ("бот,", "бот ", "bot,", "bot ")


def _starts_with_trigger(text: str) -> tuple[bool, str]:
    """Возвращает (matched, leftover_text)."""
    stripped = text.lstrip()
    low = stripped.lower()
    for word in TRIGGER_WORDS:
        wl = word.lower()
        if low.startswith(wl):
            after = stripped[len(word):]
            # требуем разделитель, чтобы не ловить 'Travelman'
            if after == "" or after[0] in " ,:;.!?":
                return True, after.lstrip(" ,:;.")
    for prefix in TRIGGER_PREFIXES:
        if low.startswith(prefix):
            return True, stripped[len(prefix):].lstrip()
    return False, text


def starts_with_trigger(text: str) -> bool:
    matched, _ = _starts_with_trigger(text)
    return matched


def strip_trigger(text: str) -> str:
    matched, leftover = _starts_with_trigger(text)
    return leftover if matched else text


def _is_reply_to_bot(message: Message, bot_user_id: int) -> bool:
    if not message.reply_to_message:
        return False
    if not message.reply_to_message.from_user:
        return False
    return message.reply_to_message.from_user.id == bot_user_id


def _is_mentioned(message: Message, bot_username: str) -> bool:
    if not bot_username:
        return False
    text = message.text or message.caption or ""
    if not text:
        return False
    entities = (message.entities or []) + (message.caption_entities or [])
    needle = f"@{bot_username}".lower()
    for ent in entities:
        if ent.type == MessageEntityType.MENTION:
            mention = text[ent.offset : ent.offset + ent.length].lower()
            if mention == needle:
                return True
    pattern = re.compile(rf"(?<![A-Za-z0-9_])@{re.escape(bot_username)}\b", re.IGNORECASE)
    return bool(pattern.search(text))


def strip_mention(text: str, bot_username: str) -> str:
    if not text or not bot_username:
        return text or ""
    pattern = re.compile(rf"(?<![A-Za-z0-9_])@{re.escape(bot_username)}\b", re.IGNORECASE)
    return pattern.sub("", text).strip()


class GroupAddressedFilter(BaseFilter):
    """В группе срабатывает только если бот упомянут / reply на бота /
    сообщение начинается с trigger word ('Трейв,' / 'TravelBot' / 'бот,').
    В личке всегда True."""

    async def __call__(self, message: Message, bot: Bot) -> bool:
        if message.chat.type == ChatType.PRIVATE:
            return True
        try:
            me = await bot.me()
        except Exception:  # noqa: BLE001
            return False
        if _is_reply_to_bot(message, me.id):
            return True
        username = (me.username or "").lower()
        if _is_mentioned(message, username):
            return True
        text = message.text or message.caption or ""
        if starts_with_trigger(text):
            return True
        return False
