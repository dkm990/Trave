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
    "<b>Как пользоваться Трейвом</b>\n\n"
    "1. Присоединиться к поездке:\n"
    "<code>/join</code>\n\n"
    "2. Добавить расход:\n"
    "<code>Трейв, 500 рублей такси</code>\n"
    "<code>Трейв, 1200 TRY ужин на всех</code>\n"
    "<code>Трейв, 30 евро музей с Антоном и Машей</code>\n\n"
    "3. Посмотреть:\n"
    "Баланс — /balance\n"
    "Участники — /members\n"
    "История и аналитика — /app"
)


PRIVATE_HELP_TEXT = (
    "<b>Трейв помогает считать расходы в поездках</b>\n\n"
    "Быстрый старт:\n"
    "1. Добавь меня в групповой чат.\n"
    "2. Создай поездку: <code>/newtrip</code>\n"
    "3. Участники нажимают <code>/join</code>\n"
    "4. Пиши расходы обычным текстом.\n\n"
    "<b>Примеры трат</b>\n"
    f"{EXPENSE_EXAMPLES}\n\n"
    "<b>Команды:</b>\n"
    "/balance — кто кому должен\n"
    "/members — участники поездки\n"
    "/app — история и аналитика\n"
    "/help — помощь"
)


PRIVATE_START_TEXT = (
    "Привет! Я Трейв — бот для расходов в поездках.\n\n"
    "Как начать:\n"
    "1. Добавь меня в групповой чат поездки.\n"
    "2. Создай поездку: <code>/newtrip</code>\n"
    "3. Попроси участников нажать <code>/join</code>.\n"
    "4. Пиши расходы обычным текстом.\n\n"
    "Пример:\n"
    "<code>Трейв, 500 рублей такси</code>\n\n"
    "История, баланс и аналитика: /app\n"
    "Помощь: /help"
)


GROUP_START_TEXT = (
    "Я Трейв — помогу считать расходы в поездке.\n\n"
    "Чтобы начать:\n"
    "1. Создайте поездку: <code>/newtrip</code>\n"
    "2. Каждый участник нажимает <code>/join</code>\n"
    "3. Потом пишите расходы прямо в чат:\n\n"
    "<code>Трейв, 500 рублей такси</code>\n"
    "<code>Трейв, 1200 TRY ужин на всех</code>\n\n"
    "Помощь: /help"
)


def _is_group_chat(message: Message) -> bool:
    return message.chat.type in {"group", "supergroup"}


def _command_kb(message: Message) -> InlineKeyboardMarkup | None:
    # Telegram does not allow web_app buttons in group chats.
    if _is_group_chat(message):
        return None
    return _miniapp_kb()


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
        reply_markup=_command_kb(message),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = GROUP_HELP_TEXT if _is_group_chat(message) else PRIVATE_HELP_TEXT
    await message.answer(text, reply_markup=_command_kb(message))


@router.message(Command("app"))
async def cmd_app(message: Message):
    await message.answer(
        "Mini App: история расходов, баланс, аналитика, фильтры и редактирование.",
        reply_markup=_command_kb(message),
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
