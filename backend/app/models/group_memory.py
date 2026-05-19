from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GroupMessage(Base):
    """Буфер сообщений группы для саммаризации."""

    __tablename__ = "group_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GroupMemory(Base):
    """Саммари бесед группы."""

    __tablename__ = "group_memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    summary: Mapped[str] = mapped_column(Text)
    source_message_count: Mapped[int] = mapped_column(Integer, default=0)
    first_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
