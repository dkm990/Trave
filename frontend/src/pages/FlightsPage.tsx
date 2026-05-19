import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Flight } from "../api/types";

const ACTIVE_STATUSES = new Set(["scheduled", "boarding", "delayed", "departed"]);

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    scheduled: "По расписанию",
    boarding: "Посадка",
    departed: "В пути",
    arrived: "Прибыл",
    delayed: "Задержан",
    cancelled: "Отменён",
  };
  return labels[status] ?? status;
}

function FlightCard({ flight }: { flight: Flight }) {
  const departure = flight.estimated_departure_at || flight.actual_departure_at || flight.scheduled_departure_at;
  const arrival = flight.estimated_arrival_at || flight.actual_arrival_at || flight.scheduled_arrival_at;

  return (
    <article className="flight-card">
      <div className="flight-card-main">
        <div>
          <div className="flight-number">{flight.flight_number}</div>
          <div className="flight-airline">{flight.airline_name || flight.airline_code}</div>
        </div>
        <span className={`flight-status flight-status-${flight.status}`}>{statusLabel(flight.status)}</span>
      </div>

      <div className="flight-route">
        <div>
          <div className="flight-airport">{flight.departure_airport}</div>
          <div className="flight-city">{flight.departure_city}</div>
          <div className="flight-time">{formatDateTime(departure)}</div>
        </div>
        <div className="flight-route-line" aria-hidden="true" />
        <div>
          <div className="flight-airport">{flight.arrival_airport}</div>
          <div className="flight-city">{flight.arrival_city}</div>
          <div className="flight-time">{formatDateTime(arrival)}</div>
        </div>
      </div>

      <div className="flight-meta-row">
        <span>{flight.trip_title}</span>
        {flight.gate ? <span>Гейт {flight.gate}</span> : null}
        {flight.baggage_belt ? <span>Багаж {flight.baggage_belt}</span> : null}
      </div>
    </article>
  );
}

export function FlightsPage() {
  const [flights, setFlights] = useState<Flight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Flight[]>("/api/flights")
      .then(setFlights)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const grouped = useMemo(() => {
    const now = Date.now();
    const active = flights
      .filter((flight) => ACTIVE_STATUSES.has(flight.status) && new Date(flight.scheduled_arrival_at).getTime() >= now)
      .sort((a, b) => new Date(a.scheduled_departure_at).getTime() - new Date(b.scheduled_departure_at).getTime());
    const history = flights
      .filter((flight) => !active.includes(flight))
      .sort((a, b) => new Date(b.scheduled_departure_at).getTime() - new Date(a.scheduled_departure_at).getTime());
    return { active, history };
  }, [flights]);

  if (loading) {
    return (
      <div>
        <div className="skeleton" style={{ width: "45%", height: 24 }} />
        <div className="skeleton" />
        <div className="skeleton" />
      </div>
    );
  }

  if (error) return <div className="error">{error}</div>;

  return (
    <div className="flights-page">
      <div className="page-heading-row">
        <div>
          <h1 className="page-title">Рейсы</h1>
          <div className="page-subtitle">Все перелёты по поездкам</div>
        </div>
        <Link to="/trips" className="btn btn-secondary">Поездки</Link>
      </div>

      <section className="flight-group">
        <div className="flight-group-title">
          <span>Активные</span>
          <span>{grouped.active.length}</span>
        </div>
        {grouped.active.length === 0 ? (
          <div className="empty">Активных рейсов нет.</div>
        ) : (
          grouped.active.map((flight) => <FlightCard key={flight.id} flight={flight} />)
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
          grouped.history.map((flight) => <FlightCard key={flight.id} flight={flight} />)
        )}
      </section>
    </div>
  );
}
