from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.session import session_scope
from app.services.balance_service import BalanceService, simplify_debts
from app.services.formatting import format_money
from app.services.trip_service import TripService
from app.services.user_service import UserService

router = Router(name="private_router")
router.message.filter(F.chat.type == ChatType.PRIVATE)

MAX_TRIP_TITLE_LENGTH = 200
NEW_TRIP_PROMPT = (
    "Как назовём поездку?\n\n"
    "Например:\n"
    "Армения\n"
    "Турция май 2026\n"
    "Ереван с друзьями\n\n"
    "Чтобы отменить: /cancel"
)
NEW_TRIP_CANCELLED_TEXT = "Ок, создание поездки отменено."
NEW_TRIP_EMPTY_TITLE_TEXT = "Название не должно быть пустым. Напишите название поездки или /cancel."
NEW_TRIP_LONG_TITLE_TEXT = f"Название слишком длинное. Максимум {MAX_TRIP_TITLE_LENGTH} символов."

_pending_new_trip_titles: dict[tuple[int, int], bool] = {}


def _pending_new_trip_key(message: Message) -> tuple[int, int] | None:
    if not message.from_user:
        return None
    return (message.chat.id, message.from_user.id)


def _validate_new_trip_title(raw_title: str) -> tuple[str | None, str | None]:
    title = (raw_title or "").strip()
    if not title:
        return None, NEW_TRIP_EMPTY_TITLE_TEXT
    if len(title) > MAX_TRIP_TITLE_LENGTH:
        return None, NEW_TRIP_LONG_TITLE_TEXT
    return title, None


def _format_my_trips_message(trips: list) -> str:
    if not trips:
        return (
            "У вас пока нет поездок.\n"
            "Создайте поездку в групповом чате: <code>/newtrip</code>."
        )
    lines = [f"• <b>{t.title}</b> ({t.default_currency}) — id {t.id}" for t in trips]
    lines.append("")
    lines.append("Чтобы выбрать поездку в группе, напишите там: /bindtrip TRIP_ID")
    return "Ваши поездки:\n" + "\n".join(lines)


def _private_trip_created_text(trip_id: int, title: str) -> str:
    return (
        f"Поездка <b>{title}</b> создана.\n\n"
        "Чтобы считать расходы вместе, добавьте бота в групповой чат и "
        f"выберите эту поездку там: <code>/bindtrip {trip_id}</code>.\n"
        "Участники добавляются командой /join в группе."
    )


@router.message(Command("newtrip"))
async def cmd_new_trip_private(message: Message):
    provided = (message.text or "").partition(" ")[2]
    key = _pending_new_trip_key(message)
    if not provided.strip():
        if key:
            _pending_new_trip_titles[key] = True
        await message.answer(NEW_TRIP_PROMPT)
        return
    title, error_text = _validate_new_trip_title(provided)
    if error_text:
        await message.answer(error_text)
        return
    async with session_scope() as session:
        user = await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        trip = await TripService(session).create_trip(title=title, owner=user)
    if key:
        _pending_new_trip_titles.pop(key, None)
    await message.answer(_private_trip_created_text(trip.id, trip.title))


@router.message(Command("cancel"))
async def private_cancel_new_trip(message: Message):
    key = _pending_new_trip_key(message)
    if not key or not _pending_new_trip_titles.pop(key, None):
        await message.answer("Сейчас нет создания поездки, которое нужно отменить.")
        return
    await message.answer(NEW_TRIP_CANCELLED_TEXT)


@router.message(Command("trips"))
async def cmd_trips(message: Message):
    await _send_user_trips(message)


@router.message(Command("mytrips"))
async def cmd_my_trips(message: Message):
    await _send_user_trips(message)


@router.message(Command("members"))
async def cmd_members_private(message: Message):
    async with session_scope() as session:
        user = await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        trip_svc = TripService(session)
        trips = await trip_svc.list_user_trips(user.id)
        if not trips:
            await message.answer(
                "У вас пока нет поездок.\n"
                "Создайте поездку в групповом чате: <code>/newtrip</code>."
            )
            return
        trip = trips[0]
        members = await trip_svc.get_members(trip.id)

    lines = [f"<b>Участники поездки {trip.title}</b>"]
    if members:
        for member in members:
            role = "создатель" if member.role == "owner" else "участник"
            name = member.display_name or f"участник {member.user_id}"
            lines.append(f"• {name} — {role}")
    else:
        lines.append("Пока никого нет.")
    lines.append("")
    lines.append("В группе новый участник может добавиться командой /join.")
    await message.answer("\n".join(lines))


async def _send_user_trips(message: Message):
    async with session_scope() as session:
        user = await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        trips = await TripService(session).list_user_trips(user.id)
    await message.answer(_format_my_trips_message(trips))


@router.message(Command("balance"))
async def cmd_balance_private(message: Message):
    async with session_scope() as session:
        user = await UserService(session).get_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer(
                "Сначала создайте поездку в группе: <code>/newtrip</code>."
            )
            return
        trips = await TripService(session).list_user_trips(user.id)
        if not trips:
            await message.answer(
                "У вас пока нет поездок.\n"
                "Создайте поездку в групповом чате: <code>/newtrip</code>."
            )
            return
        trip = trips[0]
        balances = await BalanceService(session).calculate_balances(trip.id)
        transfers = simplify_debts(balances)
        members = await TripService(session).get_members(trip.id)

    name_by_id = {m.user_id: (m.display_name or f"участник {m.user_id}") for m in members}
    cur = trip.default_currency
    head = f"<b>{trip.title}</b> · база {cur}\n"
    if not balances:
        await message.answer(
            "Расходов пока нет.\n\n"
            "Добавьте первый расход в группе:\n"
            "<code>Трейв, 500 рублей такси</code>"
        )
        return

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
    await message.answer(f"{head}\n{bal_lines}\n\n{t_lines}")


@router.message(F.text)
async def private_new_trip_title_input(message: Message):
    key = _pending_new_trip_key(message)
    if not key or not _pending_new_trip_titles.get(key):
        return

    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    title, error_text = _validate_new_trip_title(text)
    if error_text:
        await message.answer(error_text)
        return

    async with session_scope() as session:
        user = await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        trip = await TripService(session).create_trip(title=title, owner=user)

    _pending_new_trip_titles.pop(key, None)
    await message.answer(_private_trip_created_text(trip.id, trip.title))
