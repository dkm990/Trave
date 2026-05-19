"""Сервис для хранения сообщений группы, авто-саммаризации и контекстной памяти."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group_memory import GroupMessage, GroupMemory

logger = logging.getLogger(__name__)

# Сколько сообщений накапливать перед саммаризацией
SUMMARIZE_EVERY_N = 100

# Сколько последних саммари инжектить в контекст
MAX_MEMORIES_CONTEXT = 5


@dataclass
class MemoryEntry:
    id: int
    summary: str
    created_at: str


class GroupMemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_message(
        self,
        chat_id: int,
        user_id: int | None,
        user_name: str | None,
        text: str | None,
    ) -> None:
        msg = GroupMessage(
            chat_id=chat_id,
            user_id=user_id,
            user_name=user_name,
            text=text,
        )
        self.session.add(msg)

    async def get_message_count(self, chat_id: int) -> int:
        stmt = select(func.count()).where(GroupMessage.chat_id == chat_id)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def get_recent_messages(
        self, chat_id: int, limit: int = SUMMARIZE_EVERY_N
    ) -> list[GroupMessage]:
        stmt = (
            select(GroupMessage)
            .where(GroupMessage.chat_id == chat_id)
            .order_by(GroupMessage.id.asc())
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars())

    async def delete_messages(self, message_ids: list[int]) -> None:
        if not message_ids:
            return
        await self.session.execute(
            delete(GroupMessage).where(GroupMessage.id.in_(message_ids))
        )

    async def save_memory(
        self,
        chat_id: int,
        summary: str,
        message_count: int,
        first_message_id: int | None = None,
        last_message_id: int | None = None,
    ) -> GroupMemory:
        mem = GroupMemory(
            chat_id=chat_id,
            summary=summary,
            source_message_count=message_count,
            first_message_id=first_message_id,
            last_message_id=last_message_id,
        )
        self.session.add(mem)
        await self.session.flush()
        return mem

    async def get_recent_memories(
        self, chat_id: int, limit: int = MAX_MEMORIES_CONTEXT
    ) -> list[MemoryEntry]:
        stmt = (
            select(GroupMemory)
            .where(GroupMemory.chat_id == chat_id)
            .order_by(GroupMemory.id.desc())
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return [
            MemoryEntry(
                id=r.id,
                summary=r.summary,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rows.scalars()
        ]

    async def should_summarize(self, chat_id: int) -> bool:
        """Проверяет, пора ли делать саммари."""
        count = await self.get_message_count(chat_id)
        return count >= SUMMARIZE_EVERY_N

    def format_messages_for_summary(self, messages: list[GroupMessage]) -> str:
        """Форматирует сообщения в строку для отправки в LLM."""
        lines: list[str] = []
        for m in messages:
            name = m.user_name or f"user_{m.user_id}" or "unknown"
            text = m.text or ""
            # Обрезаем слишком длинные сообщения
            if len(text) > 300:
                text = text[:297] + "..."
            lines.append(f"[{name}]: {text}")
        return "\n".join(lines)

    def format_memories_for_context(self, memories: list[MemoryEntry]) -> str:
        """Форматирует саммари для вставки в промпт."""
        if not memories:
            return ""
        parts: list[str] = [f"--- ПАМЯТЬ ГРУППЫ (последние {len(memories)} саммари) ---"]
        for m in reversed(memories):  # хронологический порядок
            parts.append(f"• {m.summary}")
        return "\n".join(parts)
