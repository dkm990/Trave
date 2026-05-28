import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ExpenseEditModal } from "../components/ExpenseEditModal";
import { FrogEmptyState } from "../components/FrogEmptyState";
import { formatDate, formatDual } from "../api/format";
import { getCurrentUser } from "../telegram/webapp";
import type { Expense, Trip } from "../api/types";

const CATEGORIES = ["food", "taxi", "hotel", "shopping", "tickets", "other"];

interface Filters {
  search: string;
  category: string;
  payer: string;
  participant: string;
  currency: string;
  dateFrom: string;
  dateTo: string;
  status: string;
  onlyMine: boolean;
}

const EMPTY_FILTERS: Filters = {
  search: "",
  category: "",
  payer: "",
  participant: "",
  currency: "",
  dateFrom: "",
  dateTo: "",
  status: "",
  onlyMine: false,
};

export function ExpensesPage() {
  const { tripId } = useParams();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<Expense | null>(null);
  const [error, setError] = useState<string | null>(null);

  // add form state
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("RUB");
  const [payer, setPayer] = useState<number | "">("");
  const [participants, setParticipants] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [splitMode, setSplitMode] = useState<"equal" | "by_amount">("equal");
  const [customShares, setCustomShares] = useState<Record<number, string>>({});

  const memberById = useMemo(() => {
    const map = new Map<number, string>();
    if (trip) {
      for (const m of trip.members) {
        map.set(m.user_id, m.display_name || `user_${m.user_id}`);
      }
    }
    return map;
  }, [trip]);

  async function loadTrip() {
    if (!tripId) return;
    const t = await api<Trip>(`/api/trips/${tripId}`);
    setTrip(t);
    setCurrency(t.local_currency || t.default_currency);
    if (t.members.length && payer === "") setPayer(t.members[0].user_id);
    if (!participants.length) setParticipants(t.members.map((m) => m.user_id));
  }

  async function loadExpenses() {
    if (!tripId) return;
    const params = new URLSearchParams();
    if (filters.search.trim()) params.set("search", filters.search.trim());
    if (filters.category) params.set("category", filters.category);
    if (filters.payer) params.set("payer_id", filters.payer);
    if (filters.participant) params.set("participant_id", filters.participant);
    if (filters.currency) params.set("currency", filters.currency);
    if (filters.dateFrom) params.set("date_from", filters.dateFrom);
    if (filters.dateTo) params.set("date_to", filters.dateTo);
    if (filters.status) params.set("status", filters.status);
    if (filters.onlyMine) params.set("only_mine", "true");
    const url = `/api/trips/${tripId}/expenses${params.toString() ? `?${params}` : ""}`;
    const e = await api<Expense[]>(url);
    setExpenses(e);
  }

  useEffect(() => {
    loadTrip().catch((e) => setError((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  useEffect(() => {
    loadExpenses().catch((e) => setError((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId, filters]);

  function toggleParticipant(uid: number) {
    setParticipants((cur) =>
      cur.includes(uid) ? cur.filter((x) => x !== uid) : [...cur, uid],
    );
  }

  async function addExpense(e: React.FormEvent) {
    e.preventDefault();
    if (!tripId || !payer || !amount || !title.trim() || !participants.length) return;

    const effectiveCurrency = currency || trip?.default_currency || "RUB";
    if (!effectiveCurrency) {
      setError("Валюта не выбрана");
      return;
    }

    if (splitMode === "by_amount") {
      const total = Object.values(customShares).reduce((s, v) => s + (Number(v) || 0), 0);
      if (Math.abs(total - Number(amount)) > 1) {
        setError(`Сумма долей (${total.toFixed(2)}) не совпадает с общей суммой (${amount})`);
        return;
      }
    }

    setBusy(true);
    setError(null);
    try {
      const body: any = {
        payer_user_id: payer,
        title: title.trim(),
        amount: Number(amount),
        currency: effectiveCurrency,
        participant_user_ids: participants,
        split_mode: splitMode,
      };
      if (splitMode === "by_amount") {
        const shares: Record<number, number> = {};
        participants.forEach((uid) => {
          shares[uid] = Number(customShares[uid]) || 0;
        });
        body.custom_shares = shares;
      }
      await api(`/api/trips/${tripId}/expenses`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setTitle("");
      setAmount("");
      setSplitMode("equal");
      setCustomShares({});
      setShowAdd(false);
      await loadExpenses();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!trip) return <div className="hint">Загрузка…</div>;

  const tgUser = getCurrentUser();
  const meName = tgUser?.first_name || tgUser?.username || "";
  const activeFilters = Object.entries(filters).filter(
    ([, v]) => (typeof v === "boolean" ? v : !!v),
  ).length;

  return (
    <div>
      {/* ── Back link ── */}
      <Link to={`/trips/${trip.id}`} className="back-link">← {trip.title}</Link>

      {/* ── Hero area ── */}
      <div className="expenses-hero">
        <h1 className="title">Расходы</h1>
        <p className="hero-subtitle">
          Управляйте тратами{meName ? `, ${meName}` : ""}
        </p>
      </div>

      {/* ── Action buttons ── */}
      <div className="row" style={{ marginBottom: 10 }}>
        <button className="btn" onClick={() => setShowAdd((v) => !v)}>
          {showAdd ? "Скрыть форму" : "+ Расход"}
        </button>
        <button className="btn secondary" onClick={() => setShowFilters((v) => !v)}>
          Фильтры{activeFilters ? ` · ${activeFilters}` : ""}
        </button>
      </div>

      {/* ── Add expense form ── */}
      {showAdd && (
        <form onSubmit={addExpense} className="card expense-add-form">
          <div className="section-title">Новый расход</div>
          <input className="input" placeholder="На что (ужин, такси)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <div className="row">
            <input className="input" inputMode="decimal" placeholder="Сумма" value={amount} onChange={(e) => setAmount(e.target.value)} />
            <select className="select" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {[trip.local_currency || "", trip.default_currency, "RUB", "USD", "EUR", "TRY", "GEL", "THB", "VND"]
                .filter((v, i, a) => v && a.indexOf(v) === i)
                .map((c) => (<option key={c} value={c}>{c}</option>))}
            </select>
          </div>

          <div className="section-title">Кто оплатил</div>
          <select className="select" value={payer} onChange={(e) => setPayer(Number(e.target.value))}>
            {trip.members.map((m) => (
              <option key={m.user_id} value={m.user_id}>{m.display_name || `user_${m.user_id}`}</option>
            ))}
          </select>

          <div className="section-title">За кого</div>
          {trip.members.map((m) => (
            <label key={m.user_id} className="list-item" style={{ cursor: "pointer" }}>
              <span>{m.display_name || `user_${m.user_id}`}</span>
              <input type="checkbox" checked={participants.includes(m.user_id)} onChange={() => toggleParticipant(m.user_id)} />
            </label>
          ))}

          {/* Split mode */}
          <div className="section-title">Как делим</div>
          <div className="toggle-row">
            <button type="button" className={splitMode === "equal" ? "active" : ""} onClick={() => setSplitMode("equal")}>
              Поровну
            </button>
            <button type="button" className={splitMode === "by_amount" ? "active" : ""} onClick={() => {
              setSplitMode("by_amount");
              if (Object.keys(customShares).length === 0 && participants.length && amount) {
                const perPerson = (Number(amount) / participants.length).toFixed(2);
                const shares: Record<number, string> = {};
                participants.forEach((uid) => { shares[uid] = perPerson; });
                setCustomShares(shares);
              }
            }}>
              Вручную
            </button>
          </div>

          {splitMode === "by_amount" && participants.length > 0 && (
            <div className="split-custom">
              <div className="split-header">
                <span className="hint">
                  Итого: {Object.values(customShares).reduce((s, v) => s + (Number(v) || 0), 0).toFixed(2)} / {Number(amount || 0).toFixed(2)}
                </span>
                <button type="button" className="btn-sm" onClick={() => {
                  const perPerson = (Number(amount) / participants.length).toFixed(2);
                  const shares: Record<number, string> = {};
                  participants.forEach((uid) => { shares[uid] = perPerson; });
                  setCustomShares(shares);
                }}>Поровну</button>
              </div>
              {participants.map((uid) => (
                <div key={uid} className="split-row">
                  <span className="split-name">{memberById.get(uid) || `user_${uid}`}</span>
                  <input
                    className="split-input"
                    inputMode="decimal"
                    value={customShares[uid] || ""}
                    onChange={(e) => setCustomShares((prev) => ({ ...prev, [uid]: e.target.value }))}
                    placeholder="0.00"
                  />
                </div>
              ))}
            </div>
          )}

          {error && <div className="error">{error}</div>}
          <button className="btn" disabled={busy}>{busy ? "..." : "Добавить расход"}</button>
        </form>
      )}

      {/* ── Filters ── */}
      {showFilters && (
        <div className="card expense-filters">
          <div className="section-title">Поиск и фильтры</div>
          <input
            className="input"
            placeholder="Поиск по названию"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
          />

          <div className="section-title" style={{ marginTop: 4 }}>Категория</div>
          <div className="chip-row">
            <span
              className={`chip ${!filters.category ? "active" : ""}`}
              onClick={() => setFilters({ ...filters, category: "" })}
            >все</span>
            {CATEGORIES.map((c) => (
              <span
                key={c}
                className={`chip ${filters.category === c ? "active" : ""}`}
                onClick={() => setFilters({ ...filters, category: c })}
              >
                {c}
              </span>
            ))}
          </div>

          <div className="row">
            <div style={{ flex: 1 }}>
              <div className="section-title">Кто оплатил</div>
              <select
                className="select"
                value={filters.payer}
                onChange={(e) => setFilters({ ...filters, payer: e.target.value })}
              >
                <option value="">все</option>
                {trip.members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>{m.display_name || `user_${m.user_id}`}</option>
                ))}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <div className="section-title">Участник</div>
              <select
                className="select"
                value={filters.participant}
                onChange={(e) => setFilters({ ...filters, participant: e.target.value })}
              >
                <option value="">все</option>
                {trip.members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>{m.display_name || `user_${m.user_id}`}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="row">
            <div style={{ flex: 1 }}>
              <div className="section-title">Валюта</div>
              <select
                className="select"
                value={filters.currency}
                onChange={(e) => setFilters({ ...filters, currency: e.target.value })}
              >
                <option value="">все</option>
                {[trip.local_currency || "", trip.default_currency, "RUB", "USD", "EUR", "TRY"]
                  .filter((v, i, a) => v && a.indexOf(v) === i)
                  .map((c) => (<option key={c} value={c}>{c}</option>))}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <div className="section-title">Статус</div>
              <select
                className="select"
                value={filters.status}
                onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              >
                <option value="">активные</option>
                <option value="canceled">отменённые</option>
                <option value="confirmed">подтверждённые</option>
              </select>
            </div>
          </div>

          <div className="row">
            <div style={{ flex: 1 }}>
              <div className="section-title">С</div>
              <input
                className="input"
                type="date"
                value={filters.dateFrom}
                onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })}
              />
            </div>
            <div style={{ flex: 1 }}>
              <div className="section-title">По</div>
              <input
                className="input"
                type="date"
                value={filters.dateTo}
                onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })}
              />
            </div>
          </div>

          <label className="list-item" style={{ cursor: "pointer" }}>
            <span>Только мои (где я участник или плательщик)</span>
            <input
              type="checkbox"
              checked={filters.onlyMine}
              onChange={(e) => setFilters({ ...filters, onlyMine: e.target.checked })}
            />
          </label>

          <button className="btn-sm" style={{ marginTop: 8 }} onClick={() => setFilters(EMPTY_FILTERS)}>
            Сбросить фильтры
          </button>
        </div>
      )}

      {error && <div className="error">{error}</div>}

      {/* ── Expense list / empty state ── */}
      {expenses.length === 0 ? (
        <FrogEmptyState
          variant="backpack"
          title="Расходов пока нет"
          subtitle="Добавьте первый расход"
        />
      ) : (
        <>
          {expenses.map((e) => {
            const isCanceled = e.status === "canceled";
            return (
              <div key={e.id} className={`expense-card ${isCanceled ? "canceled" : ""}`}>
                <div className="ec-row">
                  <div style={{ flex: 1 }}>
                    <div className="ec-title">{e.title}</div>
                    <div className="ec-meta">
                      {formatDate(e.created_at)}
                      {e.category ? ` · ${e.category}` : ""}
                      {e.source ? ` · ${e.source}` : ""}
                      {e.edited_count ? ` · ✎ ${e.edited_count}` : ""}
                      {isCanceled ? " · отменён" : ""}
                    </div>
                    <div className="ec-meta">
                      Оплатил: {memberById.get(e.payer_user_id) || `user_${e.payer_user_id}`}
                      {e.shares.length > 0 && (
                        <>
                          {" · за: "}
                          {e.shares
                            .map((s) => memberById.get(s.user_id) || `user_${s.user_id}`)
                            .join(", ")}
                        </>
                      )}
                    </div>
                    {e.note && <div className="ec-meta">📝 {e.note}</div>}
                  </div>
                  <div className="ec-amount">
                    {formatDual(e.amount_original, e.currency_original, e.amount_base, e.base_currency)}
                  </div>
                </div>
                <div className="ec-actions">
                  <button className="btn-sm primary" onClick={() => setEditing(e)}>Редактировать</button>
                </div>
              </div>
            );
          })}
        </>
      )}

      {editing && trip && (
        <ExpenseEditModal
          trip={trip}
          expense={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await loadExpenses();
          }}
        />
      )}
    </div>
  );
}
