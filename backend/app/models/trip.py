from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    default_currency: Mapped[str] = mapped_column(String(8), default="RUB")
    local_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    members: Mapped[list["TripMember"]] = relationship(back_populates="trip", cascade="all, delete-orphan")


class TripMember(Base):
    __tablename__ = "trip_members"
    __table_args__ = (UniqueConstraint("trip_id", "user_id", name="uq_trip_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # owner | member
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    trip: Mapped["Trip"] = relationship(back_populates="members")
