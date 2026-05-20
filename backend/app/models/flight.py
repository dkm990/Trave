"""FlightInfo model — track flights attached to a trip."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FlightInfo(Base):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))

    # Identity
    flight_number: Mapped[str] = mapped_column(String(16))
    airline_code: Mapped[str] = mapped_column(String(8))
    airline_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Route
    departure_city: Mapped[str] = mapped_column(String(64))
    arrival_city: Mapped[str] = mapped_column(String(64))
    departure_airport: Mapped[str] = mapped_column(String(8))   # IATA
    arrival_airport: Mapped[str] = mapped_column(String(8))     # IATA
    departure_terminal: Mapped[str | None] = mapped_column(String(8), nullable=True)
    arrival_terminal: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Times
    scheduled_departure_at: Mapped[datetime] = mapped_column(DateTime)
    actual_departure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estimated_departure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_arrival_at: Mapped[datetime] = mapped_column(DateTime)
    actual_arrival_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estimated_arrival_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(16), default="scheduled"
    )  # scheduled / boarding / departed / arrived / delayed / cancelled

    # Airport logistics (nullable — only available near departure/during flight)
    check_in_counter: Mapped[str | None] = mapped_column(String(16), nullable=True)
    gate: Mapped[str | None] = mapped_column(String(8), nullable=True)
    baggage_belt: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Metadata
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index(
    "uq_flights_trip_normalized_number_date",
    FlightInfo.trip_id,
    func.upper(func.replace(func.replace(FlightInfo.flight_number, " ", ""), "-", "")),
    func.date(FlightInfo.scheduled_departure_at),
    unique=True,
)
