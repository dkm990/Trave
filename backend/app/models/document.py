from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TravelDocument(Base):
    __tablename__ = "travel_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    visibility: Mapped[str] = mapped_column(String(16), default="private")  # private | shared
    doc_type: Mapped[str] = mapped_column(String(32))
    # ticket | hotel_booking | insurance | itinerary | voucher | other

    title: Mapped[str] = mapped_column(String(200))
    telegram_file_id: Mapped[str] = mapped_column(String(256))
    telegram_file_unique_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
