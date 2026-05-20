import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Flight, Trip } from "../api/types";
import { ACTIVE_STATUSES, AddFlightModal, type AddFlightPayload, FlightCard } from "../components/FlightComponents";
import { FrogHero } from "../components/FrogHero";

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

export function FlightsPage() {
  const [flights, setFlights] = useState<Flight[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  async function load() {
    setError(null);
    const [flightRows, tripRows] = await Promise.all([
      api<Flight[]>("/api/flights"),
      api<Trip[]>("/api/trips"),
    ]);
    setFlights(flightRows);
    setTrips(tripRows);
  }

  useEffect(() => {
    load()
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const grouped = useMemo(() => splitFlights(flights), [flights]);

  async function addFlight(payload: AddFlightPayload) {
    await api<Flight>(`/api/trips/${payload.tripId}/flights`, {
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
        <div className="skeleton" style={{ width: "45%", height: 24 }} />
        <div className="skeleton" />
        <div className="skeleton" />
      </div>
    );
  }

  return (
    <div className="flights-page">
      <div className="page-heading-row">
        <div className="flight-title-with-mascot">
          <FrogHero variant="pilot" size={36} />
          <div>
            <h1 className="page-title">Рейсы</h1>
            <div className="page-subtitle">Все перелеты по поездкам</div>
          </div>
        </div>
        <div className="flight-header-actions">
          <button
            type="button"
            className="icon-btn"
            aria-label="Обновить рейсы"
            onClick={() => load().catch((e) => setError((e as Error).message))}
          >
            ↻
          </button>
          <button
            type="button"
            className="icon-btn primary"
            aria-label="Добавить рейс"
            onClick={() => setModalOpen(true)}
          >
            +
          </button>
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
          grouped.active.map((flight) => <FlightCard key={flight.id} flight={flight} variant="list" />)
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
          grouped.history.map((flight) => <FlightCard key={flight.id} flight={flight} variant="list" />)
        )}
      </section>

      {modalOpen ? (
        <AddFlightModal
          trips={trips}
          onClose={() => setModalOpen(false)}
          onSubmit={addFlight}
        />
      ) : null}
    </div>
  );
}
