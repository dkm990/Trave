"""FlightService — persists FlightInfo to DB and delegates lookups to aviation providers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.flight import FlightInfo
from app.models.trip import Trip, TripMember
from app.services.aviation.base import BaseFlightProvider


class FlightService:
    """Manages FlightInfo persistence and provider lookups."""

    def __init__(self, session: AsyncSession, provider: Optional[BaseFlightProvider] = None) -> None:
        self._session = session
        self._provider = provider

    # ── Queries ─────────────────────────────

    async def list_for_trip(self, trip_id: int) -> list[FlightInfo]:
        result = await self._session.execute(
            select(FlightInfo)
            .where(FlightInfo.trip_id == trip_id)
            .order_by(FlightInfo.scheduled_departure_at)
        )
        return list(result.scalars().all())

    async def list_for_user(self, user_id: int) -> list[FlightInfo]:
        """Get all flights across all trips the user belongs to."""
        result = await self._session.execute(
            select(FlightInfo)
            .join(Trip, FlightInfo.trip_id == Trip.id)
            .join(TripMember, Trip.id == TripMember.trip_id)
            .where(TripMember.user_id == user_id)
            .order_by(FlightInfo.scheduled_departure_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, flight_id: int) -> Optional[FlightInfo]:
        return await self._session.get(FlightInfo, flight_id)

    async def refresh_status(self, flight_id: int) -> Optional[FlightInfo]:
        """Pull latest status from provider and update DB row."""
        flight = await self.get(flight_id)
        if flight is None or self._provider is None:
            return flight

        now = datetime.utcnow()
        result = await self._provider.lookup(
            flight_number=flight.flight_number,
            date=flight.scheduled_departure_at or now,
        )

        if result:
            flight.status = result.status
            flight.departure_terminal = result.departure_terminal or flight.departure_terminal
            flight.arrival_terminal = result.arrival_terminal or flight.arrival_terminal
            flight.actual_departure_at = result.actual_departure_at or flight.actual_departure_at
            flight.estimated_departure_at = result.estimated_departure_at or flight.estimated_departure_at
            flight.actual_arrival_at = result.actual_arrival_at or flight.actual_arrival_at
            flight.estimated_arrival_at = result.estimated_arrival_at or flight.estimated_arrival_at
            flight.check_in_counter = result.check_in_counter or flight.check_in_counter
            flight.gate = result.gate or flight.gate
            flight.baggage_belt = result.baggage_belt or flight.baggage_belt

        flight.updated_at = now
        await self._session.flush()
        return flight
