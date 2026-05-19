"""Проверка покрытия валют двумя провайдерами.

Использование:
    .\\.venv\\Scripts\\python.exe scripts\\check_currency_support.py
    .\\.venv\\Scripts\\python.exe scripts\\check_currency_support.py --base USD

Скрипт делает по одному реальному HTTP-запросу к каждому провайдеру,
с таймаутом и без падения на первой ошибке. Полезен перед live Telegram smoke-test
чтобы понимать, какие пары точно ходят.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

# Позволяет запускать скрипт напрямую: добавляет backend/ в PYTHONPATH.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.providers import (  # noqa: E402
    ExchangeRateOpenProvider,
    FrankfurterProvider,
    ProviderError,
    ProviderUnsupportedPair,
)

DEFAULT_QUOTES = [
    "RUB", "USD", "EUR", "THB", "VND", "GEL", "IDR",
    "KZT", "AMD", "UAH", "BYN", "TRY", "CNY", "JPY", "KRW",
]


async def check_pair(provider, base: str, quote: str) -> tuple[str, str]:
    try:
        result = await provider.get_rate(base, quote)
        return ("ok", f"{result.rate}")
    except ProviderUnsupportedPair as exc:
        return ("unsupported", str(exc))
    except ProviderError as exc:
        return ("error", str(exc))
    except Exception as exc:  # noqa: BLE001
        return ("error", f"unexpected: {exc!r}")


async def main_async(base: str) -> int:
    async with httpx.AsyncClient(timeout=10.0) as client:
        providers = [
            FrankfurterProvider(http_client=client),
            ExchangeRateOpenProvider(http_client=client),
        ]
        col_currency = 10
        col_status = 28
        header = f"{'currency':<{col_currency}}"
        for p in providers:
            header += f"{p.name:<{col_status}}"
        print(header)
        print("-" * len(header))

        for quote in DEFAULT_QUOTES:
            if quote == base:
                continue
            row = f"{quote:<{col_currency}}"
            for provider in providers:
                status, detail = await check_pair(provider, base, quote)
                cell = f"{status}: {detail[:18]}"
                row += f"{cell:<{col_status}}"
            print(row)

        for p in providers:
            await p.aclose()

    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="USD", help="Базовая валюта (default: USD)")
    args = parser.parse_args()
    base = args.base.upper()
    print(f"Checking {base} -> ... with timeout=10s per request\n")
    code = asyncio.run(main_async(base))
    sys.exit(code)


if __name__ == "__main__":
    main()
