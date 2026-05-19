from __future__ import annotations

from aiogram import F, Router
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
                    text="📱 Открыть Mini App",
                    web_app=WebAppInfo(url=settings.mini_app_url),
                )
            ]
        ]
    )


HELP_TEXT = (
    "<b>Yo — помощник в групповых поездках</b>\n\n"
    "<b>Поездки</b>\n"
    "/newtrip Название — создать поездку\n"
    "/trips — список поездок\n"
    "/rename Новое название — переименовать активную\n"
    "/setlocalcurrency TRY — валюта страны (для отображения)\n"
    "/setdisplaycurrency RUB — валюта расчётов (только до первого расхода)\n"
    "/balance — кто кому должен\n"
    "/summary — итоги поездки (всего, по категориям, кто кому должен)\n\n"
    "<b>Расходы</b>\n"
    "/add 1200 RUB ужин за всех — структурированный ввод\n"
    "/ai я оплатил такси 300000 VND за всех — свободная фраза\n"
    "/expense 100 THB Coffee — короткий ввод\n"
    "Любой расход проходит через подтверждение Да/Изменить/Отмена.\n\n"
    "<b>Валюта и документы</b>\n"
    "/rate 100 USD RUB — конвертация валют\n"
    "/docs или /docs hotel — поиск документов\n\n"
    "<b>Mini App</b>\n"
    "/app — открыть Mini App\n\n"
    "<b>В группе</b>\n"
    "Бот реагирует только на команды, reply на бота и упоминания.\n"
    "Если @mention не срабатывает (privacy mode Telegram), используй /ai или /expense.\n"
    "Reply на сообщение бота тоже работает.\n\n"
    "<b>Участники расхода</b>\n"
    "Если бот не понял кого включить (например, «Зои» не в участниках),\n"
    "откроется picker — нажми галочки или используй 👥 Все / 🙋 Только я.\n"
    "В confirmation можно нажать ✏️ Изменить и выбрать заново."
)


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
        "Привет! Я помогаю отслеживать общие расходы, валюты и документы поездки.\n\n"
        "Открой Mini App или напиши /help.",
        reply_markup=_miniapp_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=_miniapp_kb())


@router.message(Command("app"))
async def cmd_app(message: Message):
    await message.answer("Открыть Mini App:", reply_markup=_miniapp_kb())


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
