import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Flight, Trip } from "../api/types";
import { ACTIVE_STATUSES, AddFlightModal, type AddFlightPayload, FlightCard } from "../components/FlightComponents";

function splitFlights(flights: Flight[]) {
  const now = Date.now();
  const active = flights
    .filter((flight) => ACTIVE_STATUSES.has(flight.status) && new Date(flight.scheduled_arrival_at).getTime() >= now)
    .sort((a, b) => new Date(a.scheduled_departure_at).getTime() - new Date(b.scheduled_departure_at).getTime());
  const history = flights
    .filter((flight) => !active.includes(flight))
    .sort((a, b) => new Date(b.scheduled_departure_at).getTime() - new Date(a.scheduled_departure_at).getTime());
  return { active, history };
}

export function TripFlightsPage() {
  const { tripId } = useParams();
  const numericTripId = Number(tripId);
  const [trip, setTrip] = useState<Trip | null>(null);
  const [flights, setFlights] = useState<Flight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  async function load() {
    if (!numericTripId) return;
    setError(null);
    const [tripRow, flightRows] = await Promise.all([
      api<Trip>(`/api/trips/${numericTripId}`),
      api<Flight[]>(`/api/trips/${numericTripId}/flights`),
    ]);
    setTrip(tripRow);
    setFlights(flightRows);
  }

  useEffect(() => {
    load()
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  const grouped = useMemo(() => splitFlights(flights), [flights]);

  async function addFlight(payload: AddFlightPayload) {
    await api<Flight>(`/api/trips/${numericTripId}/flights`, {
      method: "POST",
      body: JSON.stringify({
        flight_number: payload.flightNumber,
        flight_date: payload.flightDate,
      }),
    });
    setModalOpen(false);
    await load();
  }

  if (loading) {
    return (
      <div>
        <div className="skeleton" style={{ width: "55%", height: 22 }} />
        <div className="skeleton" />
      </div>
    );
  }

  const modalTrips = trip ? [trip] : [];

  return (
    <div className="flights-page">
      <Link to={numericTripId ? `/trips/${numericTripId}` : "/trips"} className="back-link">← К поездке</Link>
      <div className="page-heading-row">
        <div>
          <h1 className="page-title">Рейсы</h1>
          <div className="page-subtitle">{trip?.title || "Без названия"}</div>
        </div>
        <div className="flight-header-actions">
          <button type="button" className="icon-btn" aria-label="Обновить рейсы" onClick={() => load().catch((e) => setError((e as Error).message))}>↻</button>
          <button type="button" className="btn-sm primary add-flight-button" onClick={() => setModalOpen(true)}>+ Рейс</button>
        </div>
      </div>

      {error ? <div className="error">{error}</div> : null}

      <section className="flight-group">
        <div className="flight-group-title">
          <span>Активные</span>
          <span>{grouped.active.length}</span>
        </div>
        {grouped.active.length === 0 ? (
          <div className="empty">Активных рейсов нет.</div>
        ) : (
          grouped.active.map((flight) => <FlightCard key={flight.id} flight={flight} showTrip={false} />)
        )}
      </section>

      <section className="flight-group">
        <div className="flight-group-title">
          <span>История</span>
          <span>{grouped.history.length}</span>
        </div>
        {grouped.history.length === 0 ? (
          <div className="empty">История рейсов пока пуста.</div>
        ) : (
          grouped.history.map((flight) => <FlightCard key={flight.id} flight={flight} showTrip={false} />)
        )}
      </section>

      {modalOpen ? (
        <AddFlightModal
          trips={modalTrips}
          initialTripId={numericTripId}
          onClose={() => setModalOpen(false)}
          onSubmit={addFlight}
        />
      ) : null}
    </div>
  );
}
