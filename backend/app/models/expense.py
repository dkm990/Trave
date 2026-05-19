from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    # NOTE (reuse-audit, Spliit): future enhancements identified but NOT
    # implemented in MVP — keeping the model intentionally lean.
    #   - is_reimbursement: Boolean
    #   - split_mode: EVENLY | BY_SHARES | BY_PERCENTAGE | BY_AMOUNT
    # See docs/reuse-audit.md.

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    payer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    amount_original: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency_original: Mapped[str] = mapped_column(String(8))
    amount_base: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    base_currency: Mapped[str] = mapped_column(String(8))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    exchange_rate_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    edited_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="confirmed")
    # statuses: pending_confirmed | confirmed | canceled

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # source: bot | web | ai | manual

    shares: Mapped[list["ExpenseShare"]] = relationship(back_populates="expense", cascade="all, delete-orphan")


class ExpenseShare(Base):
    __tablename__ = "expense_shares"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    share_amount_base: Mapped[Decimal] = mapped_column(Numeric(18, 4))

    expense: Mapped["Expense"] = relationship(back_populates="shares")


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount_base: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | settled
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
