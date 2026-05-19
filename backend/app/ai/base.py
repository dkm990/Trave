from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# Все известные actions. Если LLM вернёт что-то другое — приводим к "unknown".
KNOWN_ACTIONS = frozenset(
    {
        "add_expense",
        "show_balance",
        "show_today_spending",
        "convert_currency",
        "find_document",
        "save_document",
        "get_weather",
        "chat",
        "unknown",
    }
)


@dataclass
class Intent:
    """Структурированный результат разбора текста.

    add_expense    payload: amount, currency, title, payer_name,
                            participant_names (list|None),
                            split_scope ("all"|"mentioned"|"self"|"unknown"),
                            category ("food"|"taxi"|"hotel"|"tickets"|
                                     "shopping"|"other"|"unknown"),
                            split_count (int|None),
                            split_all (bool, derived from split_scope)
    show_balance         payload: scope ("trip")
    show_today_spending  payload: date ("today"), group_by ("category"|"none")
    convert_currency     payload: amount, from, to
    find_document        payload: query, doc_type
    save_document        payload: doc_type, title
    get_weather          payload: city (str)
    chat                 payload: topic (str) — тема разговора
    unknown              payload: пусто
    """

    action: str
    confidence: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    needs_confirmation: bool = False

    def __post_init__(self) -> None:
        if self.action not in KNOWN_ACTIONS:
            self.action = "unknown"


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def parse_intent(self, text: str, *, context: dict | None = None) -> Intent:
        ...

    async def aclose(self) -> None:  # pragma: no cover
        return None
