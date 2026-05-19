import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api } from "../api/client";
import { formatMoney, formatNet } from "../api/format";
import type { DashboardResponse } from "../api/types";
import { FrogHero } from "../components/FrogHero";

export function TripDashboardPage() {
  const { tripId } = useParams();
  const { pathname } = useLocation();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!tripId) return;
    const d = await api<DashboardResponse>(`/api/trips/${tripId}/dashboard`);
    setData(d);
  }

  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  if (error) return <div className="error">{error}</div>;
  if (!data) {
    return (
      <div>
        <div className="skeleton" style={{ width: "60%", height: 22 }} />
        <div className="skeleton" />
        <div className="skeleton" />
      </div>
    );
  }

  const { trip, today, trip_total, balances, transfers } = data;
  const todayCurrency = today.base_currency || trip.default_currency;
  const tripCurrency = trip_total.display_currency || trip.default_currency;

  const todayCats = Object.entries(today.by_category)
    .map(([k, v]) => ({ k, v: Number(v) }))
    .sort((a, b) => b.v - a.v);
  const tripCats = Object.entries(trip_total.by_category)
    .map(([k, v]) => ({ k, v: Number(v) }))
    .sort((a, b) => b.v - a.v);

  const isActive = (suffix: string) => pathname.endsWith(suffix);

  return (
    <div>
      <Link to="/trips" className="back-link">← К поездкам</Link>

      {/* ── Summary card ── */}
      <div className="summary-card">
        <div className="summary-card-header">
          <div>
            <div className="summary-trip-name">{trip.title}</div>
            <div className="summary-currency">
              {trip.local_currency
                ? `${trip.local_currency} → ${trip.default_currency}`
                : trip.default_currency}
            </div>
          </div>
          <FrogHero variant="travel" size={48} />
        </div>
        <div className="summary-kpi-row">
          <div className="summary-kpi">
            <div className="summary-kpi-label">Сегодня</div>
            <div className="summary-kpi-value">
              {formatMoney(today.total ?? "0", todayCurrency)}
            </div>
            <div className="summary-kpi-sub">{today.count} расходов</div>
          </div>
          <div className="summary-kpi">
            <div className="summary-kpi-label">За поездку</div>
            <div className="summary-kpi-value">
              {formatMoney(trip_total.total_display ?? "0", tripCurrency)}
            </div>
            <div className="summary-kpi-sub">{trip_total.count} расходов</div>
          </div>
        </div>
      </div>

      {/* ── Segmented tabs ── */}
      <div className="segmented-tabs">
        <Link
          to={`/trips/${trip.id}/expenses`}
          className={`segmented-tab${isActive("/expenses") ? " active" : ""}`}
        >
          Расходы
        </Link>
        <Link
          to={`/trips/${trip.id}/analytics`}
          className={`segmented-tab${isActive("/analytics") ? " active" : ""}`}
        >
          Аналитика
        </Link>
        <Link
          to={`/trips/${trip.id}/balances`}
          className={`segmented-tab${isActive("/balances") ? " active" : ""}`}
        >
          Балансы
        </Link>
        <Link
          to={`/trips/${trip.id}/documents`}
          className={`segmented-tab${isActive("/documents") ? " active" : ""}`}
        >
          Документы
        </Link>
        <Link
          to={`/trips/${trip.id}/flights`}
          className={`segmented-tab${isActive("/flights") ? " active" : ""}`}
        >
          Рейсы
        </Link>
      </div>

      {/* ── Today categories ── */}
      <div className="card">
        <div className="section-title" style={{ marginTop: 0 }}>Сегодня по категориям</div>
        {todayCats.length === 0 ? (
          <div className="empty">Сегодня пусто.</div>
        ) : (
          todayCats.map(({ k, v }) => {
            const max = todayCats[0].v || 1;
            return (
              <div key={k} className="bar">
                <div className="bar-label">{k}</div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(v / max) * 100}%` }} />
                </div>
                <div className="bar-value">{formatMoney(v, todayCurrency)}</div>
              </div>
            );
          })
        )}
      </div>

      {/* ── Trip categories ── */}
      <div className="card">
        <div className="section-title" style={{ marginTop: 0 }}>Топ категорий за поездку</div>
        {tripCats.length === 0 ? (
          <div className="empty">Расходов нет.</div>
        ) : (
          tripCats.slice(0, 6).map(({ k, v }) => {
            const max = tripCats[0].v || 1;
            return (
              <div key={k} className="bar">
                <div className="bar-label">{k}</div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(v / max) * 100}%` }} />
                </div>
                <div className="bar-value">{formatMoney(v, tripCurrency)}</div>
              </div>
            );
          })
        )}
      </div>

      {/* ── Balances ── */}
      <div className="card">
        <div className="section-title" style={{ marginTop: 0 }}>Балансы ({tripCurrency})</div>
        {balances.length === 0 ? (
          <div className="empty">Расходов нет.</div>
        ) : (
          balances.map((b) => (
            <div key={b.user_id} className="list-item">
              <div>{b.name}</div>
              <div style={{ color: Number(b.net) >= 0 ? "#34d399" : "#f87171" }}>
                {formatNet(b.net, tripCurrency)}
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── Transfers ── */}
      <div className="card">
        <div className="section-title" style={{ marginTop: 0 }}>Кто кому должен</div>
        {transfers.length === 0 ? (
          <div className="empty">Все рассчитались.</div>
        ) : (
          transfers.map((t, i) => (
            <div key={i} className="list-item">
              <span>{t.from_name} → {t.to_name}</span>
              <span>{formatMoney(t.amount, tripCurrency)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
