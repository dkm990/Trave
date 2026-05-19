from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, future=True, echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Create tables if not exist (для dev/тестов; в prod использовать alembic).

    Также делает идемпотентные мини-миграции для колонок, которые добавились
    позже — чтобы не ломать существующие dev/local БД. Для prod — Alembic.
    """
    from app.models import all_models  # noqa: F401  ensure metadata is populated

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text

        # trip.local_currency
        try:
            await conn.execute(
                text("ALTER TABLE trips ADD COLUMN local_currency VARCHAR(8)")
            )
        except Exception:
            pass

        # expense additive columns (web v1)
        for ddl in (
            "ALTER TABLE expenses ADD COLUMN updated_at DATETIME",
            "ALTER TABLE expenses ADD COLUMN canceled_at DATETIME",
            "ALTER TABLE expenses ADD COLUMN edited_count INTEGER DEFAULT 0",
            "ALTER TABLE expenses ADD COLUMN note TEXT",
            "ALTER TABLE expenses ADD COLUMN source VARCHAR(16)",
        ):
            try:
                await conn.execute(text(ddl))
            except Exception:
                pass
