import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { formatMoney, formatNet } from "../api/format";
import type { BalancesResponse, Trip } from "../api/types";
import { FrogHero } from "../components/FrogHero";

export function BalancesPage() {
  const { tripId } = useParams();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [data, setData] = useState<BalancesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tripId) return;
    (async () => {
      try {
        setTrip(await api<Trip>(`/api/trips/${tripId}`));
        setData(await api<BalancesResponse>(`/api/trips/${tripId}/balances`));
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [tripId]);

  if (error) return <div className="error">{error}</div>;
  if (!trip || !data) return <div className="hint">Загрузка…</div>;

  const nameOf = (uid: number) =>
    trip.members.find((m) => m.user_id === uid)?.display_name || `user_${uid}`;

  const netColor = (net: string | number) =>
    Number(net) >= 0 ? "#34d399" : "#f87171";

  return (
    <div>
      <Link to={`/trips/${trip.id}`} className="back-link">
        ← {trip.title}
      </Link>

      {/* Hero area with frog accountant mascot */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <FrogHero variant="accountant" size={40} />
        <h1 className="title" style={{ margin: 0 }}>Балансы</h1>
      </div>

      {/* Net balance card */}
      <div className="card">
        <div className="section-title">Чистый итог ({data.base_currency})</div>
        {data.balances.length === 0 && <div className="hint">Расходов нет</div>}
        {data.balances.map((b) => (
          <div key={b.user_id} className="list-item">
            <div>
              <div style={{ fontWeight: 600 }}>{nameOf(b.user_id)}</div>
              <div className="hint">
                Оплатил: {formatMoney(b.paid, data.base_currency)} · доля:{" "}
                {formatMoney(b.owes, data.base_currency)}
              </div>
            </div>
            <span style={{ color: netColor(b.net), fontWeight: 600 }}>
              {formatNet(b.net, data.base_currency)}
            </span>
          </div>
        ))}
      </div>

      {/* Settlement cards */}
      <div className="card">
        <div className="section-title">Кто кому должен</div>
        {data.transfers.length === 0 ? (
          <div className="hint">Все рассчитались.</div>
        ) : (
          data.transfers.map((t, i) => (
            <div key={i} className="settlement-card">
              <div className="settlement-flow">
                <span>{nameOf(t.from_user_id)}</span>
                <span style={{ margin: "0 8px" }}>→</span>
                <span>{nameOf(t.to_user_id)}</span>
              </div>
              <div className="settlement-amount">
                {formatMoney(t.amount, data.base_currency)}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
