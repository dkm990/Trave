import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { formatMoney } from "../api/format";
import type { AnalyticsResponse } from "../api/types";

type Period = "trip" | "today";

export function AnalyticsPage() {
  const { tripId } = useParams();
  const [period, setPeriod] = useState<Period>("trip");
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!tripId) return;
    setLoading(true);
    try {
      const r = await api<AnalyticsResponse>(
        `/api/trips/${tripId}/analytics?period=${period}`,
      );
      setData(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId, period]);

  if (error) return <div className="error">{error}</div>;

  const display = data?.display_currency || "RUB";
  const maxCat = data ? Math.max(...data.by_category.map((c) => Number(c.amount_display)), 0) : 0;
  const maxPayer = data ? Math.max(...data.by_payer.map((p) => Number(p.amount_display ?? 0)), 0) : 0;
  const maxPart = data ? Math.max(...data.by_participant.map((p) => Number(p.share_display ?? 0)), 0) : 0;
  const maxDay = data ? Math.max(...data.by_day.map((d) => Number(d.amount_display)), 0) : 0;

  const localCurrency = data?.local_currency;
  const localTotal = localCurrency
    ? data.totals_by_original_currency.find((c) => c.currency === localCurrency)
    : null;

  return (
    <div>
      <Link to={`/trips/${tripId}`} className="back-link">← Дашборд</Link>
      <h1 className="title">Аналитика</h1>

      <div className="toggle-row">
        <button className={period === "trip" ? "active" : ""} onClick={() => setPeriod("trip")}>
          За поездку
        </button>
        <button className={period === "today" ? "active" : ""} onClick={() => setPeriod("today")}>
          Сегодня
        </button>
      </div>

      {loading && !data ? (
        <>
          <div className="skeleton" />
          <div className="skeleton" />
        </>
      ) : data ? (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <div className="k-label">Всего расходов</div>
              <div className="k-value">{formatMoney(data.total_display, display)}</div>
              <div className="hint">{data.count} {data.count === 1 ? "расход" : data.count >= 2 && data.count <= 4 ? "расхода" : "расходов"}</div>
            </div>
            <div className="kpi">
              <div className="k-label">{localCurrency ? `В ${localCurrency}` : "Местная валюта"}</div>
              <div className="k-value">
                {localTotal ? formatMoney(localTotal.amount, localTotal.currency) : (localCurrency || "—")}
              </div>
              <div className="hint">↕ {display}</div>
            </div>
          </div>

          <div className="card">
            <div className="section-title">По исходным валютам</div>
            {data.totals_by_original_currency.length === 0 ? (
              <div className="empty">Нет данных.</div>
            ) : (
              data.totals_by_original_currency.map((c) => (
                <div key={c.currency} className="list-item">
                  <span>{c.currency}</span>
                  <span>{formatMoney(c.amount, c.currency)}</span>
                </div>
              ))
            )}
          </div>

          <div className="card">
            <div className="section-title">По категориям ({display})</div>
            {data.by_category.length === 0 ? (
              <div className="empty">Нет данных.</div>
            ) : (
              data.by_category.map((c) => {
                const v = Number(c.amount_display);
                const orig = c.original
                  .map((o) => `${formatMoney(o.amount, o.currency)}`)
                  .join(", ");
                return (
                  <div key={c.category} style={{ marginBottom: 4 }}>
                    <div className="bar">
                      <div className="bar-label">{c.category}</div>
                      <div className="bar-track">
                        <div className="bar-fill" style={{ width: `${maxCat ? (v / maxCat) * 100 : 0}%` }} />
                      </div>
                      <div className="bar-value">{formatMoney(v, display)}</div>
                    </div>
                    {orig && c.original.length > 1 && (
                      <div className="hint" style={{ paddingLeft: 95 }}>{orig}</div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          <div className="card">
            <div className="section-title">Кто сколько оплатил</div>
            {data.by_payer.length === 0 ? (
              <div className="empty">Нет данных.</div>
            ) : (
              data.by_payer.map((p) => {
                const v = Number(p.amount_display ?? 0);
                return (
                  <div key={p.user_id} className="bar">
                    <div className="bar-label">{p.name}</div>
                    <div className="bar-track">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${maxPayer ? (v / maxPayer) * 100 : 0}%`,
                          background: "var(--accent-green)",
                        }}
                      />
                    </div>
                    <div className="bar-value">{formatMoney(v, display)}</div>
                  </div>
                );
              })
            )}
          </div>

          <div className="card">
            <div className="section-title">Кто сколько потратил (по долям)</div>
            {data.by_participant.length === 0 ? (
              <div className="empty">Нет данных.</div>
            ) : (
              data.by_participant.map((p) => {
                const v = Number(p.share_display ?? 0);
                return (
                  <div key={p.user_id} className="bar">
                    <div className="bar-label">{p.name}</div>
                    <div className="bar-track">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${maxPart ? (v / maxPart) * 100 : 0}%`,
                          background: "var(--accent-blue)",
                        }}
                      />
                    </div>
                    <div className="bar-value">{formatMoney(v, display)}</div>
                  </div>
                );
              })
            )}
          </div>

          <div className="card">
            <div className="section-title">По дням</div>
            {data.by_day.length === 0 ? (
              <div className="empty">Нет данных.</div>
            ) : (
              data.by_day.map((d) => {
                const v = Number(d.amount_display);
                return (
                  <div key={d.date} className="day-bar">
                    <div className="bar-label" style={{ flex: "0 0 65px" }}>{d.date.slice(5)}</div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${maxDay ? (v / maxDay) * 100 : 0}%` }} />
                    </div>
                    <div className="bar-value">{formatMoney(v, display)}</div>
                  </div>
                );
              })
            )}
          </div>

          <div className="card">
            <div className="section-title">Долги</div>
            {data.debts.length === 0 ? (
              <div className="empty">Все рассчитались.</div>
            ) : (
              data.debts.map((t, i) => (
                <div key={i} className="settlement-card">
                  <span className="settlement-flow">{t.from_name} → {t.to_name}</span>
                  <span className="settlement-amount">{formatMoney(t.amount, display)}</span>
                </div>
              ))
            )}
          </div>

          {/* TODO: budget per trip, daily limit, export CSV/Excel, AI analytics questions */}
        </>
      ) : null}
    </div>
  );
}
