from __future__ import annotations

import logging

from aiogram import BaseMiddleware, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject

from app.bot.filters import GroupAddressedFilter, strip_mention, strip_trigger
from app.bot.session import session_scope
from app.services.balance_service import BalanceService, simplify_debts
from app.services.formatting import format_money
from app.services.group_memory_service import SUMMARIZE_EVERY_N, GroupMemoryService
from app.services.trip_service import TripService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = Router(name="group_router")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


def _format_group_trips_message(active_trip, chat_trips: list) -> str:
    lines: list[str] = []
    if active_trip:
        lines.append(
            f"Активная поездка: <b>{active_trip.title}</b> ({active_trip.default_currency}) — id {active_trip.id}"
        )
    else:
        lines.append("Активная поездка: не выбрана")

    lines.append("")
    lines.append("Поездки, привязанные к этому чату:")
    if not chat_trips:
        lines.append("• (пусто)")
    else:
        for t in chat_trips:
            marker = "✅" if active_trip and t.id == active_trip.id else "•"
            lines.append(f"{marker} <b>{t.title}</b> ({t.default_currency}) — id {t.id}")

    lines.append("")
    lines.append("Если знаете ID поездки, используйте /bindtrip TRIP_ID.")
    lines.append("Я могу показать ваши доступные поездки в личном чате: /mytrips.")
    return "\n".join(lines)


def _format_members_message(trip, members: list) -> str:
    if not members:
        return (
            "Пока не вижу участников поездки.\n"
            "Попроси участников нажать /join."
        )

    lines = [f"<b>Участники поездки {trip.title}</b>"]
    for member in members:
        role = "создатель" if member.role == "owner" else "участник"
        name = member.display_name or f"участник {member.user_id}"
        lines.append(f"• {name} — {role}")
    lines.append("")
    lines.append("Новый участник может добавиться сам командой /join.")
    return "\n".join(lines)


class GroupMessageSaver(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        if isinstance(event, Message):
            text = (event.text or event.caption or "")
            if text:
                await _save_and_maybe_summarize(event)
        return await handler(event, data)


async def _save_and_maybe_summarize(message: Message) -> None:
    text = (message.text or message.caption or "")[:500]
    async with session_scope() as session:
        svc = GroupMemoryService(session)
        await svc.save_message(
            chat_id=message.chat.id,
            user_id=message.from_user.id if message.from_user else None,
            user_name=(message.from_user.full_name if message.from_user else None),
            text=text,
        )
        await session.commit()

        if await svc.should_summarize(message.chat.id):
            await _do_summarize(message.chat.id, message.bot, svc, session)


async def _do_summarize(chat_id: int, bot, svc: GroupMemoryService, session) -> None:
    messages = await svc.get_recent_messages(chat_id, SUMMARIZE_EVERY_N)
    if len(messages) < 10:
        return

    formatted = svc.format_messages_for_summary(messages)
    first_id = messages[0].id
    last_id = messages[-1].id

    from app.ai import get_ai_provider

    ai = get_ai_provider()
    if not hasattr(ai, "summarize_conversation"):
        return

    try:
        summary = await ai.summarize_conversation(formatted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summarize failed for chat=%s: %s", chat_id, exc)
        return

    if not summary or len(summary) < 10:
        return

    mem = await svc.save_memory(
        chat_id=chat_id,
        summary=summary,
        message_count=len(messages),
        first_message_id=first_id,
        last_message_id=last_id,
    )
    await svc.delete_messages([m.id for m in messages])
    await session.commit()

    logger.info("Group summary saved: chat=%s mem_id=%s msgs=%s", chat_id, mem.id, len(messages))

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"📝 <b>Саммари беседы</b> (последние {len(messages)} сообщений):\n\n{summary}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to notify group: %s", exc)


router.message.middleware(GroupMessageSaver())


@router.message(Command("newtrip"))
async def group_new_trip(message: Message):
    title = (message.text or "").partition(" ")[2].strip()
    if not title:
        await message.answer("Использование: <code>/newtrip Название</code>")
        return
    async with session_scope() as session:
        user = await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        trip = await TripService(session).create_trip(
            title=title, owner=user, telegram_chat_id=message.chat.id
        )
    await message.answer(
        f"Поездка <b>{trip.title}</b> создана.\n\n"
        "Теперь:\n"
        "1. Каждый участник нажимает /join\n"
        "2. Добавляйте расходы в чат, например:\n"
        "<code>Трейв, 500 рублей такси</code>\n\n"
        "Посмотреть: /balance, /members, /app"
    )


@router.message(Command("trips"))
async def group_trips(message: Message):
    async with session_scope() as session:
        trip_svc = TripService(session)
        active = await trip_svc.get_trip_for_chat(message.chat.id)
        chat_trips = await trip_svc.list_trips_for_chat(message.chat.id)
    await message.answer(_format_group_trips_message(active, chat_trips))


@router.message(Command("bindtrip"))
async def group_bind_trip(message: Message):
    arg = (message.text or "").partition(" ")[2].strip()
    if not arg.isdigit():
        await message.answer("Использование: <code>/bindtrip TRIP_ID</code>")
        return
    async with session_scope() as session:
        trip_svc = TripService(session)
        trip = await trip_svc.get_trip(int(arg))
        if not trip:
            await message.answer(
                "Не нашёл поездку с таким ID. Проверьте ID или откройте список в личке: /mytrips."
            )
            return
        await trip_svc.bind_to_chat(trip, message.chat.id)
    await message.answer(
        f"Готово, выбрана поездка <b>{trip.title}</b>.\n"
        "Если вы ещё не в поездке, нажмите /join."
    )


@router.message(Command("join"))
async def group_join(message: Message):
    async with session_scope() as session:
        trip_svc = TripService(session)
        trip = await trip_svc.get_trip_for_chat(message.chat.id)
        if not trip:
            await message.answer(
                "В этом чате пока нет поездки.\n\n"
                "Создайте её командой:\n"
                "<code>/newtrip</code>\n\n"
                "После этого участники смогут нажать /join."
            )
            return
        user = await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        members_before = await trip_svc.get_members(trip.id)
        was_member = any(member.user_id == user.id for member in members_before)
        await trip_svc.add_member(trip, user)
    if was_member:
        await message.answer(
            "Ты уже в этой поездке.\n\n"
            "Добавить расход можно так:\n"
            "<code>Трейв, 500 рублей такси</code>"
        )
        return
    await message.answer(
        "Готово, ты в поездке.\n\n"
        "Теперь можешь добавлять расходы:\n"
        "<code>Трейв, 500 рублей такси</code>"
    )


@router.message(Command("members"))
async def group_members(message: Message):
    async with session_scope() as session:
        trip_svc = TripService(session)
        trip = await trip_svc.get_trip_for_chat(message.chat.id)
        if not trip:
            await message.answer(
                "В этом чате пока нет поездки.\n\n"
                "Создайте её командой:\n"
                "<code>/newtrip</code>\n\n"
                "После этого участники смогут нажать /join."
            )
            return
        members = await trip_svc.get_members(trip.id)
    await message.answer(_format_members_message(trip, members))


@router.message(Command("balance"))
async def group_balance(message: Message):
    async with session_scope() as session:
        trip = await TripService(session).get_trip_for_chat(message.chat.id)
        if not trip:
            await message.answer(
                "В этом чате пока нет поездки.\n\n"
                "Создайте её командой:\n"
                "<code>/newtrip</code>\n\n"
                "После этого участники смогут нажать /join."
            )
            return
        balances = await BalanceService(session).calculate_balances(trip.id)
        transfers = simplify_debts(balances)
        members = await TripService(session).get_members(trip.id)
    if not balances:
        await message.answer(
            "Расходов пока нет.\n\n"
            "Добавьте первый расход:\n"
            "<code>Трейв, 500 рублей такси</code>"
        )
        return
    name_by_id = {m.user_id: (m.display_name or f"участник {m.user_id}") for m in members}
    cur = trip.default_currency
    bal_lines = "\n".join(
        f"• {name_by_id.get(b.user_id, b.user_id)}: оплатил {format_money(b.paid, cur)}, "
        f"доля {format_money(b.owes, cur)}, баланс {format_money(b.net, cur)}"
        for b in balances
    )
    if transfers:
        t_lines = "\n".join(
            f"→ {name_by_id.get(t.from_user_id, t.from_user_id)} должен "
            f"{name_by_id.get(t.to_user_id, t.to_user_id)} {format_money(t.amount, cur)}"
            for t in transfers
        )
    else:
        t_lines = "Все рассчитались."
    await message.answer(f"<b>{trip.title}</b> · база {cur}\n\n{bal_lines}\n\n{t_lines}")


@router.message(GroupAddressedFilter(), F.text)
async def group_natural_text(message: Message):
    from app.bot.intent_router import handle_intent_text

    raw_text = (message.text or "").strip()
    if raw_text.startswith("/"):
        return

    me = await message.bot.me()
    bot_username = (me.username or "").lower()

    cleaned = strip_mention(raw_text, bot_username)
    cleaned = strip_trigger(cleaned)

    matched_by = "trigger"
    if (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == me.id
    ):
        matched_by = "reply"
    elif bot_username and f"@{bot_username}" in raw_text.lower():
        matched_by = "mention"

    logger.info(
        "group_natural_text chat=%s user=%s matched_by=%s text=%s",
        message.chat.id,
        message.from_user.id if message.from_user else None,
        matched_by,
        cleaned[:80],
    )

    await handle_intent_text(message, cleaned, source=matched_by, use_reply=True)
