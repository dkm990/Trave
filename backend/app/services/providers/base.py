"""Базовый интерфейс currency-провайдеров.

Делим типы ошибок на:
- ProviderUnsupportedPair: пара/валюта не поддерживается этим провайдером.
  Сервис должен немедленно перейти к следующему fallback'у.
- ProviderError: транспорт/HTTP/таймаут/невалидный ответ — всё, что может
  пройти на повторе или у другого провайдера.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class ProviderError(Exception):
    """Сетевая/временная ошибка провайдера. Можно пробовать следующий."""


class ProviderUnsupportedPair(ProviderError):
    """Провайдер заведомо не умеет конкретную пару — сразу к fallback."""


@dataclass
class RateResult:
    base: str
    quote: str
    rate: Decimal
    rate_date: date
    provider: str  # имя провайдера, например 'frankfurter' или 'exchangerate_open'


class CurrencyProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def get_rate(self, base: str, quote: str) -> RateResult:
        """Возвращает RateResult или кидает ProviderError/ProviderUnsupportedPair."""

    async def aclose(self) -> None:  # pragma: no cover - hook
        return None
