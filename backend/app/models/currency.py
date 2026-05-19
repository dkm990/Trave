from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ExchangeRateCache(Base):
    __tablename__ = "exchange_rate_cache"
    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "quote_currency",
            "rate_date",
            "provider",
            name="uq_rate_base_quote_date_provider",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(8), index=True)
    quote_currency: Mapped[str] = mapped_column(String(8), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    rate_date: Mapped[date] = mapped_column(Date)
    provider: Mapped[str] = mapped_column(String(32), default="frankfurter")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
