"""Flight API endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user, db_session
from app.models.flight import FlightInfo
from app.models.trip import Trip
from app.models.user import User
from app.schemas.common import FlightCreateRequest, FlightOut
from app.services.aviation import MockFlightProvider
from app.services.flight_service import FlightService
from app.services.trip_service import TripService

router = APIRouter(tags=["flights"])
flight_router = APIRouter(prefix="/api/trips/{trip_id}/flights", tags=["flights"])
status_router = APIRouter(prefix="/api/flights", tags=["flights"])

# Single shared provider instance
_provider = MockFlightProvider()


def _flight_out(flight: FlightInfo, trip_title: str) -> dict:
    """Serialize a FlightInfo row with trip title for FlightOut."""
    return {
        "id": flight.id,
        "trip_id": flight.trip_id,
        "trip_title": trip_title,
        "flight_number": flight.flight_number,
        "airline_code": flight.airline_code,
        "airline_name": flight.airline_name,
        "departure_city": flight.departure_city,
        "arrival_city": flight.arrival_city,
        "departure_airport": flight.departure_airport,
        "arrival_airport": flight.arrival_airport,
        "departure_terminal": flight.departure_terminal,
        "arrival_terminal": flight.arrival_terminal,
        "scheduled_departure_at": flight.scheduled_departure_at,
        "actual_departure_at": flight.actual_departure_at,
        "estimated_departure_at": flight.estimated_departure_at,
        "scheduled_arrival_at": flight.scheduled_arrival_at,
        "actual_arrival_at": flight.actual_arrival_at,
        "estimated_arrival_at": flight.estimated_arrival_at,
        "status": flight.status,
        "check_in_counter": flight.check_in_counter,
        "gate": flight.gate,
        "baggage_belt": flight.baggage_belt,
        "created_at": flight.created_at,
        "updated_at": flight.updated_at,
    }


@flight_router.get("", response_model=list[FlightOut])
async def list_flights(
    trip_id: int,
    user: User = Depends(current_user),
    session=Depends(db_session),
):
    """Get all flights for a trip, sorted by departure time."""
    trip = await TripService(session).get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    svc = FlightService(session, _provider)
    flights = await svc.list_for_trip(trip_id)
    return [_flight_out(flight, trip.title) for flight in flights]


@flight_router.post("", response_model=FlightOut, status_code=201)
async def add_flight(
    trip_id: int,
    payload: FlightCreateRequest,
    user: User = Depends(current_user),
    session=Depends(db_session),
):
    """Add a flight to a trip.

    MVP flow: provide just flight_number + flight_date → provider fills the rest.
    Full flow: provide all fields directly (provider used for enrichment only).
    """
    trip = await TripService(session).get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")

    lookup_date = (
        datetime.combine(payload.flight_date, datetime.min.time())
        if payload.flight_date
        else payload.scheduled_departure_at or datetime.utcnow()
    )

    # Try provider lookup to fill missing fields
    provider_result = None
    if _provider:
        provider_result = await _provider.lookup(
            flight_number=payload.flight_number,
            date=lookup_date,
        )

    # MVP mode: if no explicit route data provided, require provider result
    is_mvp_mode = not payload.airline_code and not payload.departure_airport
    if is_mvp_mode and not provider_result:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "FLIGHT_NOT_FOUND",
                "message": "Рейс не найден. Проверьте номер рейса и дату.",
            },
        )

    # Build flight with explicit fields, falling back to provider
    airline_code = payload.airline_code or (provider_result.airline_code if provider_result else "??")

    flight = FlightInfo(
        trip_id=trip_id,
        created_by_user_id=user.id,
        flight_number=payload.flight_number,
        airline_code=airline_code,
        airline_name=payload.airline_name or (provider_result.airline_name if provider_result else None),
        departure_city=payload.departure_city or (provider_result.departure_city if provider_result else "") or "—",
        arrival_city=payload.arrival_city or (provider_result.arrival_city if provider_result else "") or "—",
        departure_airport=payload.departure_airport or (provider_result.departure_airport if provider_result else "") or "???",
        arrival_airport=payload.arrival_airport or (provider_result.arrival_airport if provider_result else "") or "???",
        departure_terminal=payload.departure_terminal or (provider_result.departure_terminal if provider_result else None),
        arrival_terminal=payload.arrival_terminal or (provider_result.arrival_terminal if provider_result else None),
        scheduled_departure_at=(
            payload.scheduled_departure_at
            or (provider_result.scheduled_departure_at if provider_result else None)
            or lookup_date
        ),
        scheduled_arrival_at=(
            payload.scheduled_arrival_at
            or (provider_result.scheduled_arrival_at if provider_result else None)
            or lookup_date
        ),
        status=provider_result.status if provider_result else "scheduled",
    )
    session.add(flight)
    await session.flush()

    # Refresh full status from provider
    svc = FlightService(session, _provider)
    await svc.refresh_status(flight.id)

    return _flight_out(flight, trip.title)


@status_router.get("/{flight_id}/status", response_model=FlightOut)
async def get_flight_status(
    flight_id: int,
    user: User = Depends(current_user),
    session=Depends(db_session),
):
    """Get latest status for a single flight (with provider refresh)."""
    svc = FlightService(session, _provider)
    flight = await svc.refresh_status(flight_id)
    if flight is None:
        raise HTTPException(404, "Flight not found")
    trip = await TripService(session).get_trip(flight.trip_id)
    return _flight_out(flight, trip.title if trip else f"Поездка #{flight.trip_id}")


# ── Global flights (all user's flights across trips) ──

@status_router.get("", response_model=list[FlightOut])
async def list_all_flights(
    user: User = Depends(current_user),
    session=Depends(db_session),
):
    """Get all flights for the current user across all trips."""
    svc = FlightService(session, _provider)
    rows = await svc.list_for_user(user.id)
    return [_flight_out(flight, trip_title) for flight, trip_title in rows]
