"""Запуск Telegram-бота в режиме long polling.

Использование:
    python run_bot.py

Перед запуском убедись, что заполнен TELEGRAM_BOT_TOKEN в backend/.env
"""
from __future__ import annotations

import asyncio
import logging

from app.bot import build_bot, build_dispatcher, setup_bot_commands
from app.database import init_db


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    from app.diagnostics import log_startup_report

    log_startup_report("bot")
    await init_db()
    bot = build_bot()
    await setup_bot_commands(bot)
    dp = build_dispatcher()
    me = await bot.me()
    logging.info("Bot @%s started in polling mode", me.username)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
