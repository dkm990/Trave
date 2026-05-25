from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.bot.session import session_scope
from app.config import get_settings
from app.services.formatting import format_money
from app.services.user_service import UserService

router = Router(name="basic")


def _miniapp_kb() -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть Mini App",
                    web_app=WebAppInfo(url=settings.mini_app_url),
                )
            ]
        ]
    )


EXPENSE_EXAMPLES = (
    "<code>Трейв, 500 рублей такси</code>\n"
    "<code>Трейв, 1200 TRY ужин на всех</code>\n"
    "<code>Трейв, 30 евро музей с Антоном и Машей</code>\n"
    "<code>Трейв, я оплатил 3000 рублей за отель</code>"
)


GROUP_HELP_TEXT = (
    "<b>Трейв считает расходы в поездке</b>\n\n"
    "<b>Как начать в группе</b>\n"
    "1. Создайте поездку: <code>/newtrip Турция 2026</code>\n"
    "2. Каждый участник пишет: <code>/join</code>\n"
    "3. Добавляйте траты обычным текстом.\n\n"
    "<b>Примеры трат</b>\n"
    f"{EXPENSE_EXAMPLES}\n\n"
    "<b>Основные команды</b>\n"
    "/newtrip — создать поездку\n"
    "/join — присоединиться к поездке\n"
    "/balance — баланс и долги\n"
    "/members — участники поездки\n"
    "/app — история, аналитика и редактирование\n"
    "/help — эта подсказка\n\n"
    "Если бот не понял расход, напишите его короче: "
    "<code>Трейв, 500 рублей такси</code>."
)


PRIVATE_HELP_TEXT = (
    "<b>Трейв помогает считать общие расходы в поездках</b>\n\n"
    "<b>Полный сценарий</b>\n"
    "1. Добавьте бота в групповой чат поездки.\n"
    "2. В группе создайте поездку: <code>/newtrip Турция 2026</code>\n"
    "3. Каждый участник пишет в группе: <code>/join</code>\n"
    "4. Пишите траты обычным текстом, а бот предложит подтвердить.\n\n"
    "<b>Примеры трат</b>\n"
    f"{EXPENSE_EXAMPLES}\n\n"
    "<b>Где смотреть результат</b>\n"
    "/balance — кто кому должен\n"
    "/members — кто участвует в поездке\n"
    "/app — история, аналитика, фильтры и редактирование\n\n"
    "<b>Дополнительно</b>\n"
    "/trips или /mytrips — ваши поездки\n"
    "/bindtrip ID — выбрать активную поездку для группы\n"
    "/summary — краткие итоги поездки\n"
    "/rate 100 USD RUB — быстрый курс валют\n\n"
    "Если бот не понял расход, попробуйте короткий формат: "
    "<code>500 RUB такси</code>."
)


PRIVATE_START_TEXT = (
    "Привет! Я Трейв. Помогаю группе считать расходы в поездке: кто оплатил, "
    "на кого делим и кто кому должен.\n\n"
    "Чтобы начать, добавьте меня в групповой чат и напишите там "
    "<code>/newtrip Название поездки</code>. Потом каждый участник пишет "
    "<code>/join</code>."
)


GROUP_START_TEXT = (
    "Я Трейв, считаю общие расходы поездки в этом чате.\n\n"
    "Начните с <code>/newtrip Название поездки</code>. "
    "После этого каждый участник пишет <code>/join</code>.\n"
    "История и аналитика: /app."
)


def _is_group_chat(message: Message) -> bool:
    return message.chat.type in {"group", "supergroup"}


@router.message(CommandStart())
async def cmd_start(message: Message):
    async with session_scope() as session:
        await UserService(session).get_or_create(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
    await message.answer(
        GROUP_START_TEXT if _is_group_chat(message) else PRIVATE_START_TEXT,
        reply_markup=_miniapp_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = GROUP_HELP_TEXT if _is_group_chat(message) else PRIVATE_HELP_TEXT
    await message.answer(text, reply_markup=_miniapp_kb())


@router.message(Command("app"))
async def cmd_app(message: Message):
    await message.answer(
        "Mini App: история расходов, баланс, аналитика, фильтры и редактирование.",
        reply_markup=_miniapp_kb(),
    )


@router.message(Command("rate"))
async def cmd_rate(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 4:
        await message.answer("Использование: <code>/rate 100 USD RUB</code>")
        return
    from decimal import Decimal, InvalidOperation

    from app.services.currency_service import CurrencyError, CurrencyService

    try:
        amount = Decimal(parts[1].replace(",", "."))
    except InvalidOperation:
        await message.answer("Не понял сумму. Пример: <code>/rate 100 USD RUB</code>")
        return

    base = parts[2].upper()
    quote = parts[3].upper()
    async with session_scope() as session:
        try:
            converted, info = await CurrencyService(session).convert(amount, base, quote)
        except CurrencyError as exc:
            await message.answer(f"Курс недоступен: {exc}")
            return

    age = "из кеша" if info.from_cache else "свежий"
    await message.answer(
        f"<b>{format_money(amount, base)} = {format_money(converted, quote)}</b>\n"
        f"Курс: 1 {base} = {info.rate} {quote}\n"
        f"Дата: {info.rate_date.isoformat()} ({age}, {info.provider})"
    )
