import { FormEvent, useMemo, useState } from "react";
import type { Flight, Trip } from "../api/types";

export const ACTIVE_STATUSES = new Set(["scheduled", "boarding", "delayed", "departed"]);

export interface AddFlightPayload {
  tripId: number;
  flightNumber: string;
  flightDate: string;
}

function parseDate(value: string): Date {
  return new Date(value);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parseDate(value));
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parseDate(value));
}

function sameMinute(a: string | null, b: string): boolean {
  if (!a) return true;
  return Math.floor(parseDate(a).getTime() / 60000) === Math.floor(parseDate(b).getTime() / 60000);
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

function tripLabel(flight: Flight): string {
  return flight.trip_title?.trim() || "Без названия";
}

function FlightTime({ scheduled, actual }: { scheduled: string; actual: string | null }) {
  const changed = actual && !sameMinute(actual, scheduled);
  return (
    <div className="flight-time-stack">
      <div className="flight-time-large">{formatTime(actual || scheduled)}</div>
      {changed ? <div className="flight-time-scheduled">{formatTime(scheduled)}</div> : null}
    </div>
  );
}

function Logistics({ flight }: { flight: Flight }) {
  const items = [
    flight.check_in_counter ? ["Регистрация", flight.check_in_counter] : null,
    flight.gate ? ["Гейт", flight.gate] : null,
    flight.baggage_belt ? ["Багаж", flight.baggage_belt] : null,
  ].filter(Boolean) as string[][];

  if (!items.length) return null;
  return (
    <div className="flight-logistics">
      {items.map(([label, value]) => (
        <div key={label} className="flight-logistic">
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function FlightAdvice({ flight }: { flight: Flight }) {
  if (!ACTIVE_STATUSES.has(flight.status)) return null;
  const departure = flight.estimated_departure_at || flight.actual_departure_at || flight.scheduled_departure_at;
  const tips = [
    flight.status === "delayed" ? "Проверьте обновления времени вылета перед выездом в аэропорт." : null,
    flight.check_in_counter ? `Регистрация: стойки ${flight.check_in_counter}.` : null,
    flight.gate ? `Посадка через гейт ${flight.gate}.` : "Гейт может появиться ближе к вылету.",
    `Плановое отправление: ${formatDate(departure)}, ${formatTime(departure)}.`,
  ].filter(Boolean);

  return (
    <div className="flight-advice">
      <div className="flight-advice-title">Что нужно знать</div>
      <ul>
        {tips.map((tip) => <li key={tip}>{tip}</li>)}
      </ul>
    </div>
  );
}

export function FlightCard({ flight, variant = "full", showTrip = true }: { flight: Flight; variant?: "full" | "list"; showTrip?: boolean }) {
  const departureActual = flight.estimated_departure_at || flight.actual_departure_at;
  const arrivalActual = flight.estimated_arrival_at || flight.actual_arrival_at;
  const compact = variant === "list" && ["arrived", "cancelled"].includes(flight.status);

  return (
    <article className={`flight-card flight-card-${variant}${compact ? " is-compact" : ""}`}>
      <div className="flight-card-top">
        <div className="flight-title-block">
          <div className="flight-route-title">{flight.departure_city} → {flight.arrival_city}</div>
          <div className="flight-subtitle">
            {(flight.airline_name || flight.airline_code)} · {flight.flight_number}
          </div>
        </div>
        <span className={`flight-status flight-status-${flight.status}`}>{statusLabel(flight.status)}</span>
      </div>

      <div className="flight-date-row">
        <span>{formatDate(flight.scheduled_departure_at)}</span>
        {showTrip ? <span>{tripLabel(flight)}</span> : null}
      </div>

      <div className="flight-timeline">
        <div className="flight-point">
          <FlightTime scheduled={flight.scheduled_departure_at} actual={departureActual} />
          <div className="flight-airport-line">
            <strong>{flight.departure_airport}</strong>
            {flight.departure_terminal ? <span>Терминал {flight.departure_terminal}</span> : null}
          </div>
        </div>
        <div className="flight-progress" aria-hidden="true">
          <span className="flight-progress-line" />
          <span className="flight-plane">✈</span>
        </div>
        <div className="flight-point flight-point-arrival">
          <FlightTime scheduled={flight.scheduled_arrival_at} actual={arrivalActual} />
          <div className="flight-airport-line">
            <strong>{flight.arrival_airport}</strong>
            {flight.arrival_terminal ? <span>Терминал {flight.arrival_terminal}</span> : null}
          </div>
        </div>
      </div>

      <Logistics flight={flight} />
      {!compact ? <FlightAdvice flight={flight} /> : null}
    </article>
  );
}

export function AddFlightModal({
  trips,
  initialTripId,
  onClose,
  onSubmit,
}: {
  trips: Trip[];
  initialTripId?: number;
  onClose: () => void;
  onSubmit: (payload: AddFlightPayload) => Promise<void>;
}) {
  const [tripId, setTripId] = useState(String(initialTripId || trips[0]?.id || ""));
  const [flightNumber, setFlightNumber] = useState("");
  const [flightDate, setFlightDate] = useState(new Date().toISOString().slice(0, 10));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fixedTrip = Boolean(initialTripId);
  const selectedTrip = useMemo(() => trips.find((trip) => trip.id === Number(tripId)), [trips, tripId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!tripId || !flightNumber.trim() || !flightDate) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        tripId: Number(tripId),
        flightNumber: flightNumber.trim().toUpperCase().replace(/\s+/g, ""),
        flightDate,
      });
    } catch (e) {
      const raw = (e as Error).message;
      setError(
        raw.includes("FLIGHT_ALREADY_EXISTS")
          ? "Этот рейс уже добавлен"
          : raw.includes("FLIGHT_PROVIDER_RATE_LIMITED")
            ? "Источник данных временно ограничил запросы. Попробуйте позже."
            : raw.includes("FLIGHT_NOT_FOUND")
              ? "Рейс не найден. Проверьте номер и дату."
              : raw.includes("FLIGHT_PROVIDER")
                ? "Источник данных временно недоступен"
                : raw
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal add-flight-modal" onSubmit={submit}>
        <div className="modal-header">
          <div className="modal-title">Добавить рейс</div>
          <button type="button" className="modal-close" onClick={onClose}>×</button>
        </div>

        {fixedTrip ? (
          <div className="flight-modal-trip">{selectedTrip?.title || "Без названия"}</div>
        ) : (
          <label className="field-label">
            Поездка
            <select className="select" value={tripId} onChange={(e) => setTripId(e.target.value)} required>
              {trips.map((trip) => (
                <option key={trip.id} value={trip.id}>{trip.title || "Без названия"}</option>
              ))}
            </select>
          </label>
        )}

        <label className="field-label">
          Номер рейса
          <input
            className="input"
            placeholder="TK1723"
            value={flightNumber}
            onChange={(e) => setFlightNumber(e.target.value)}
            autoFocus
            required
          />
        </label>

        <label className="field-label">
          Дата рейса
          <input
            className="input"
            type="date"
            value={flightDate}
            onChange={(e) => setFlightDate(e.target.value)}
            required
          />
        </label>

        {error ? <div className="error">{error}</div> : null}

        <div className="btn-row">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>Отмена</button>
          <button type="submit" className="btn" disabled={submitting || !tripId}>{submitting ? "Добавляем..." : "Добавить"}</button>
        </div>
      </form>
    </div>
  );
}
