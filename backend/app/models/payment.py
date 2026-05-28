from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    amount_original: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency_original: Mapped[str] = mapped_column(String(8))
    amount_base: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    base_currency: Mapped[str] = mapped_column(String(8))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    exchange_rate_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | canceled

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
