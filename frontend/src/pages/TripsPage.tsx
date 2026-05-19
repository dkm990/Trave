import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Trip } from "../api/types";
import { FrogHero } from "../components/FrogHero";
import { FrogEmptyState } from "../components/FrogEmptyState";

/** Map a trip title to a representative emoji, or fall back to 🌍. */
function tripEmoji(title: string): string {
  const t = title.toLowerCase();
  if (t.includes("грузи") || t.includes("georgia") || t.includes("тбилис")) return "🍷";
  if (t.includes("таи") || t.includes("thai") || t.includes("пхукет") || t.includes("банкг")) return "🏝️";
  if (t.includes("турци") || t.includes("turkey") || t.includes("стамбул")) return "🕌";
  if (t.includes("европ") || t.includes("europe")) return "🏰";
  if (t.includes("казах") || t.includes("алмат") || t.includes("астан")) return "🏔️";
  if (t.includes("море") || t.includes("пляж") || t.includes("beach")) return "🏖️";
  if (t.includes("гор") || t.includes("mountain") || t.includes("поход")) return "⛰️";
  if (t.includes("отпуск") || t.includes("vacation")) return "✈️";
  if (t.includes("команд") || t.includes("рабо")) return "💼";
  if (t.includes("фестив") || t.includes("fest")) return "🎪";
  if (t.includes("свадьб") || t.includes("wedding")) return "💒";
  if (t.includes("лыж") || t.includes("ski") || t.includes("сноуборд")) return "🎿";
  return "🌍";
}

export function TripsPage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [title, setTitle] = useState("");
  const [currency, setCurrency] = useState("RUB");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const data = await api<Trip[]>("/api/trips");
      setTrips(data);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createTrip(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api<Trip>("/api/trips", {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), default_currency: currency }),
      });
      setTitle("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {/* ── Hero card ── */}
      <div className="hero-card">
        <div className="hero-card-content">
          <FrogHero variant="travel" size={56} />
          <div className="hero-card-text">
            <h2 className="hero-card-title">Куда едем?</h2>
            <p className="hero-card-subtitle">Создай поездку и считай расходы вместе</p>
          </div>
        </div>
      </div>

      {/* ── Create trip form ── */}
      <form onSubmit={createTrip} className="card">
        <input
          className="input"
          placeholder="Название (например: Грузия 2025)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="row">
          <select
            className="select"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            <option value="RUB">₽ RUB</option>
            <option value="USD">$ USD</option>
            <option value="EUR">€ EUR</option>
            <option value="GEL">₾ GEL</option>
            <option value="THB">฿ THB</option>
            <option value="KZT">₸ KZT</option>
          </select>
          <button className="btn" disabled={busy || !title.trim()}>
            {busy ? "Создаём..." : "Создать"}
          </button>
        </div>
        {error && <div className="hint" style={{ color: "var(--danger)", marginTop: 8 }}>{error}</div>}
      </form>

      {/* ── Trip list ── */}
      <div className="section-title">Мои поездки</div>
      {trips.length === 0 ? (
        <FrogEmptyState
          variant="backpack"
          title="Поездок пока нет"
          subtitle="Создай первую поездку выше"
        />
      ) : (
        trips.map((t) => (
          <Link key={t.id} to={`/trips/${t.id}`} className="trip-card">
            <span className="trip-card-emoji">{tripEmoji(t.title)}</span>
            <div className="trip-card-info">
              <div className="trip-card-name">{t.title}</div>
              <div className="trip-card-meta">
                <span>{t.default_currency}</span>
                <span>·</span>
                <span>участников: {t.members.length}</span>
              </div>
            </div>
            <div className="trip-card-arrow">→</div>
          </Link>
        ))
      )}
    </div>
  );
}
