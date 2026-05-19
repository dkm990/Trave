import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Expense, Trip } from "../api/types";

const CATEGORIES = ["food", "taxi", "hotel", "shopping", "tickets", "other"];

interface Props {
  trip: Trip;
  expense: Expense;
  onClose: () => void;
  onSaved: () => void;
}

export function ExpenseEditModal({ trip, expense, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(expense.title);
  const [amount, setAmount] = useState(expense.amount_original);
  const [currency, setCurrency] = useState(expense.currency_original);
  const [category, setCategory] = useState(expense.category || "");
  const [payer, setPayer] = useState<number>(expense.payer_user_id);
  const [participants, setParticipants] = useState<number[]>(
    expense.shares.map((s) => s.user_id),
  );
  const [note, setNote] = useState(expense.note || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Split mode
  const [splitMode, setSplitMode] = useState<"equal" | "by_amount">("equal");
  const [customShares, setCustomShares] = useState<Record<number, string>>({});

  // Detect if expense was originally split unequally
  useEffect(() => {
    if (expense.shares.length > 1) {
      const amounts = expense.shares.map((s) => Number(s.share_amount_base));
      const allEqual = amounts.every((a) => Math.abs(a - amounts[0]) < 0.02);
      if (!allEqual) {
        setSplitMode("by_amount");
        const shares: Record<number, string> = {};
        expense.shares.forEach((s) => {
          shares[s.user_id] = String(Number(s.share_amount_base));
        });
        setCustomShares(shares);
      }
    }
  }, [expense]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function toggleParticipant(uid: number) {
    setParticipants((cur) => {
      const next = cur.includes(uid) ? cur.filter((x) => x !== uid) : [...cur, uid];
      if (splitMode === "by_amount") {
        const newShares = { ...customShares };
        if (!cur.includes(uid)) {
          newShares[uid] = "";
        } else {
          delete newShares[uid];
        }
        setCustomShares(newShares);
      }
      return next;
    });
  }

  function handleSplitModeChange(mode: "equal" | "by_amount") {
    setSplitMode(mode);
    if (mode === "by_amount" && Object.keys(customShares).length === 0) {
      const perPerson = (Number(amount) / participants.length).toFixed(2);
      const shares: Record<number, string> = {};
      participants.forEach((uid) => {
        shares[uid] = perPerson;
      });
      setCustomShares(shares);
    }
  }

  function distributeEqually() {
    const perPerson = (Number(amount) / participants.length).toFixed(2);
    const shares: Record<number, string> = {};
    participants.forEach((uid) => {
      shares[uid] = perPerson;
    });
    setCustomShares(shares);
  }

  function getSharesTotal(): number {
    return Object.values(customShares).reduce((sum, v) => sum + (Number(v) || 0), 0);
  }

  function getSharesDiff(): number {
    return Number(amount) - getSharesTotal();
  }

  async function save() {
    if (!title.trim() || !amount || participants.length === 0) {
      setError("Заполни название, сумму и хотя бы одного участника");
      return;
    }

    if (splitMode === "by_amount") {
      const diff = getSharesDiff();
      if (Math.abs(diff) > 1) {
        setError(`Сумма долей не совпадает с общей суммой (разница: ${diff.toFixed(2)})`);
        return;
      }
    }

    setBusy(true);
    setError(null);
    try {
      const payload: any = {
        title: title.trim(),
        amount,
        currency: currency.toUpperCase(),
        category: category || undefined,
        payer_user_id: payer,
        participant_user_ids: participants,
        note: note.trim() || undefined,
        split_mode: splitMode,
      };

      if (splitMode === "by_amount") {
        const shares: Record<number, number> = {};
        participants.forEach((uid) => {
          shares[uid] = Number(customShares[uid]) || 0;
        });
        payload.custom_shares = shares;
      }

      await api(`/api/trips/${trip.id}/expenses/${expense.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function cancelExpense() {
    if (!confirm("Отменить расход? Он не будет учитываться в балансе и аналитике.")) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/api/trips/${trip.id}/expenses/${expense.id}/cancel`, {
        method: "POST",
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const currencyOptions = Array.from(
    new Set([
      currency,
      trip.local_currency || "",
      trip.default_currency,
      "USD",
      "EUR",
      "TRY",
      "RUB",
    ].filter(Boolean)),
  );

  const isCanceled = expense.status === "canceled";
  const memberName = (uid: number) =>
    trip.members.find((m) => m.user_id === uid)?.display_name || `user_${uid}`;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            {isCanceled ? "Расход (отменён)" : "Редактирование расхода"}
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Закрыть">×</button>
        </div>

        <div className="section-title">Название</div>
        <input
          className="input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="ужин, такси..."
        />

        <div className="row">
          <div style={{ flex: 1 }}>
            <div className="section-title">Сумма</div>
            <input
              className="input"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div style={{ flex: 1 }}>
            <div className="section-title">Валюта</div>
            <select className="select" value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {currencyOptions.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="section-title">Категория</div>
        <div className="chip-row">
          <span
            className={`chip ${!category ? "active" : ""}`}
            onClick={() => setCategory("")}
          >
            не задана
          </span>
          {CATEGORIES.map((c) => (
            <span
              key={c}
              className={`chip ${category === c ? "active" : ""}`}
              onClick={() => setCategory(c)}
            >
              {c}
            </span>
          ))}
        </div>

        <div className="section-title">Кто оплатил</div>
        <select className="select" value={payer} onChange={(e) => setPayer(Number(e.target.value))}>
          {trip.members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.display_name || `user_${m.user_id}`}
            </option>
          ))}
        </select>

        <div className="section-title">За кого делим</div>
        {trip.members.map((m) => (
          <label key={m.user_id} className="list-item" style={{ cursor: "pointer" }}>
            <span>{m.display_name || `user_${m.user_id}`}</span>
            <input
              type="checkbox"
              checked={participants.includes(m.user_id)}
              onChange={() => toggleParticipant(m.user_id)}
            />
          </label>
        ))}

        {/* Split mode toggle */}
        <div className="section-title">Как делим</div>
        <div className="toggle-row">
          <button
            className={splitMode === "equal" ? "active" : ""}
            onClick={() => handleSplitModeChange("equal")}
          >
            Поровну
          </button>
          <button
            className={splitMode === "by_amount" ? "active" : ""}
            onClick={() => handleSplitModeChange("by_amount")}
          >
            Вручную
          </button>
        </div>

        {/* Custom shares inputs */}
        {splitMode === "by_amount" && participants.length > 0 && (
          <div className="split-custom">
            <div className="split-header">
              <span className="hint">
                Итого: {getSharesTotal().toFixed(2)} / {Number(amount).toFixed(2)}
                {Math.abs(getSharesDiff()) > 0.01 && (
                  <span style={{ color: "var(--danger)" }}>
                    {" "}(разница: {getSharesDiff().toFixed(2)})
                  </span>
                )}
              </span>
              <button className="btn-sm" onClick={distributeEqually}>
                Поровну
              </button>
            </div>
            {participants.map((uid) => (
              <div key={uid} className="split-row">
                <span className="split-name">{memberName(uid)}</span>
                <input
                  className="split-input"
                  inputMode="decimal"
                  value={customShares[uid] || ""}
                  onChange={(e) =>
                    setCustomShares((prev) => ({ ...prev, [uid]: e.target.value }))
                  }
                  placeholder="0.00"
                />
              </div>
            ))}
          </div>
        )}

        <div className="section-title">Заметка</div>
        <input
          className="input"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="опционально"
        />

        {error && <div className="error">{error}</div>}

        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={save}>
            {busy ? "..." : "Сохранить"}
          </button>
          <button className="btn-secondary" disabled={busy} onClick={onClose}>
            Отмена
          </button>
        </div>

        {!isCanceled && (
          <button
            className="btn-danger"
            disabled={busy}
            onClick={cancelExpense}
            style={{ marginTop: 12, width: "100%" }}
          >
            Отменить расход
          </button>
        )}
        {isCanceled && (
          <div className="hint" style={{ marginTop: 12 }}>
            Этот расход уже отменён.
          </div>
        )}
      </div>
    </div>
  );
}
