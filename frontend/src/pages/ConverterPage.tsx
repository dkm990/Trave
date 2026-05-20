import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useParams } from "react-router-dom";
import { FrogHero } from "../components/FrogHero";
import { api, ApiError } from "../api/client";
import type { CurrencyConvert, QuickCurrenciesResponse, Trip } from "../api/types";

const FALLBACK_QUICK = ["RUB", "USD", "EUR", "VND", "TRY"];

const ALL_CURRENCIES = [
  "RUB", "USD", "EUR", "VND", "TRY", "KGS", "GBP", "JPY", "CNY", "KRW",
  "THB", "GEL", "AED", "IDR", "INR", "KZT", "UZS", "BRL", "AUD", "CAD",
  "CHF", "PLN", "CZK", "HUF", "SEK", "NOK", "DKK", "SGD", "HKD", "MXN",
  "PHP", "MYR", "ZAR", "ILS", "EGP", "NGN", "PKR", "BDT", "UAH", "AMD",
];

const FLAGS: Record<string, string> = {
  RUB: "🇷🇺", USD: "🇺🇸", EUR: "🇪🇺", VND: "🇻🇳", TRY: "🇹🇷",
  KGS: "🇰🇬", GBP: "🇬🇧", JPY: "🇯🇵", CNY: "🇨🇳", KRW: "🇰🇷",
  THB: "🇹🇭", GEL: "🇬🇪", AED: "🇦🇪", IDR: "🇮🇩", INR: "🇮🇳",
  KZT: "🇰🇿", UZS: "🇺🇿", BRL: "🇧🇷", AUD: "🇦🇺", CAD: "🇨🇦",
  CHF: "🇨🇭", PLN: "🇵🇱", CZK: "🇨🇿", HUF: "🇭🇺", SEK: "🇸🇪",
  NOK: "🇳🇴", DKK: "🇩🇰", SGD: "🇸🇬", HKD: "🇭🇰", MXN: "🇲🇽",
  PHP: "🇵🇭", MYR: "🇲🇾", ZAR: "🇿🇦", ILS: "🇮🇱", EGP: "🇪🇬",
  NGN: "🇳🇬", PKR: "🇵🇰", BDT: "🇧🇩", UAH: "🇺🇦", AMD: "🇦🇲",
};

const SYMBOLS: Record<string, string> = {
  RUB: "₽", USD: "$", EUR: "€", VND: "₫", TRY: "₺",
  KGS: "лв", GBP: "£", JPY: "¥", CNY: "¥", KRW: "₩",
  THB: "฿", GEL: "₾", AED: "د.إ", IDR: "Rp", INR: "₹",
  KZT: "₸", UZS: "сўм", BRL: "R$", AUD: "A$", CAD: "C$",
  CHF: "Fr", PLN: "zł", CZK: "Kč", HUF: "Ft", SEK: "kr",
  NOK: "kr", DKK: "kr", SGD: "S$", HKD: "HK$", MXN: "Mex$",
  PHP: "₱", MYR: "RM", ZAR: "R", ILS: "₪", EGP: "E£",
  NGN: "₦", PKR: "Rs", BDT: "৳", UAH: "₴", AMD: "֏",
};

interface RateCache {
  [key: string]: { rate: number; timestamp: number };
}

export function ConverterPage() {
  const { tripId } = useParams();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [currencies, setCurrencies] = useState<string[]>(FALLBACK_QUICK);
  const [amounts, setAmounts] = useState<Record<string, string>>({ RUB: "1000" });
  const [activeCurrency, setActiveCurrency] = useState("RUB");
  const [rates, setRates] = useState<RateCache>({});
  const [busy, setBusy] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [addSearch, setAddSearch] = useState("");
  const [showNumpad, setShowNumpad] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [staleData, setStaleData] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  function toUserError(err: unknown): string {
    if (err instanceof ApiError) {
      if (err.status === 503) return "Источник курсов временно недоступен. Попробуйте позже.";
      if (err.status >= 500) return "Ошибка сервера при обновлении курсов.";
      return "Не удалось обновить курсы.";
    }
    return "Ошибка сети. Проверьте соединение и попробуйте снова.";
  }

  useEffect(() => {
    (async () => {
      if (!tripId) return;
      try {
        const t = await api<Trip>(`/api/trips/${tripId}`);
        setTrip(t);
        const base = t.local_currency || t.default_currency || "RUB";
        setActiveCurrency(base);
        setAmounts({ [base]: "1000" });
        const q = await api<QuickCurrenciesResponse>(`/api/currency/trip/${tripId}/quick`);
        if (q.currencies?.length) setCurrencies(q.currencies);
      } catch {
        // dev fallback
      }
    })();
  }, [tripId]);

  const fetchRates = useCallback(async (base: string, amount: string) => {
    if (!amount || Number(amount) === 0) {
      const cleared: Record<string, string> = {};
      currencies.forEach((c) => {
        cleared[c] = c === base ? amount : "";
      });
      setAmounts(cleared);
      return;
    }

    setBusy(true);
    setErrorMessage(null);
    try {
      const targets = currencies.filter((c) => c !== base);
      const promises = targets.map(async (q) => {
        try {
          const params = new URLSearchParams({ amount, base, quote: q });
          const r = await api<CurrencyConvert>(`/api/currency/convert?${params}`);
          const converted = Number(r.converted);
          const rate = Number(r.rate?.rate);
          if (!Number.isFinite(converted) || !Number.isFinite(rate) || converted <= 0 || rate <= 0) {
            throw new Error("Invalid converter response");
          }
          return { quote: q, converted, rate, ok: true as const };
        } catch (err) {
          return { quote: q, ok: false as const, err };
        }
      });

      const results = await Promise.all(promises);
      const newAmounts: Record<string, string> = { ...amounts, [base]: amount };
      const newRates: RateCache = { ...rates };
      let successCount = 0;
      let failedCount = 0;
      let firstError: unknown = null;

      results.forEach((res) => {
        if (res.ok) {
          newAmounts[res.quote] = res.converted.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
            useGrouping: false,
          });
          newRates[`${base}_${res.quote}`] = { rate: res.rate, timestamp: Date.now() };
          successCount += 1;
        } else {
          failedCount += 1;
          if (!firstError) firstError = res.err;
          if (!newAmounts[res.quote]) newAmounts[res.quote] = "—";
        }
      });

      if (successCount > 0) {
        setAmounts(newAmounts);
        setRates(newRates);
        setLastUpdated(
          new Date().toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          }),
        );
        setStaleData(failedCount > 0);
        if (failedCount > 0) {
          setErrorMessage("Часть курсов не обновилась. Показаны последние доступные данные.");
        }
      } else {
        setStaleData(true);
        setErrorMessage(toUserError(firstError));
      }
    } finally {
      setBusy(false);
    }
  }, [amounts, currencies, rates]);

  useEffect(() => {
    fetchRates(activeCurrency, amounts[activeCurrency] || "1000");
  }, [currencies.length]); // eslint-disable-line react-hooks/exhaustive-deps

  function triggerConvert(currency: string, value: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (value) fetchRates(currency, value);
    }, 500);
  }

  function handleAmountChange(currency: string, value: string) {
    const cleaned = value.replace(/[^0-9.]/g, "");
    setActiveCurrency(currency);
    setAmounts((prev) => ({ ...prev, [currency]: cleaned }));
    triggerConvert(currency, cleaned);
  }

  function handleFocus(currency: string) {
    setActiveCurrency(currency);
  }

  function handleNumpadKey(key: string) {
    const current = amounts[activeCurrency] || "";
    let newValue: string;
    if (key === "⌫") newValue = current.slice(0, -1);
    else if (key === ".") {
      if (current.includes(".")) return;
      newValue = current + ".";
    } else if (key === "C") newValue = "";
    else newValue = current + key;

    setAmounts((prev) => ({ ...prev, [activeCurrency]: newValue }));
    triggerConvert(activeCurrency, newValue);
  }

  function removeCurrency(currency: string) {
    if (currencies.length <= 2) return;
    setCurrencies((prev) => prev.filter((c) => c !== currency));
    if (activeCurrency === currency) {
      const remaining = currencies.filter((c) => c !== currency);
      setActiveCurrency(remaining[0]);
    }
  }

  function addCurrency(currency: string) {
    if (!currencies.includes(currency)) setCurrencies((prev) => [...prev, currency]);
    setShowAddModal(false);
    setAddSearch("");
  }

  const availableToAdd = useMemo(() => {
    const search = addSearch.toUpperCase();
    return ALL_CURRENCIES.filter((c) => !currencies.includes(c)).filter((c) => !search || c.includes(search));
  }, [currencies, addSearch]);

  function getRateHint(currency: string): string {
    if (currency === activeCurrency) return "Исходная валюта";
    const key = `${activeCurrency}_${currency}`;
    const cached = rates[key];
    if (cached) return `1 ${activeCurrency} = ${cached.rate} ${currency}`;
    return "";
  }

  return (
    <div className="converter-page">
      <div className="converter-header">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <FrogHero variant="cashier" size={36} />
          <h1 className="converter-title">Конвертер</h1>
        </div>
        <div className="converter-header-right">
          <span className="converter-updated">
            {lastUpdated ? `${lastUpdated}` : ""}
            {busy && " ⟳"}
          </span>
          <button
            className={`converter-numpad-toggle ${showNumpad ? "active" : ""}`}
            onClick={() => setShowNumpad(!showNumpad)}
            title={showNumpad ? "Скрыть клавиатуру" : "Показать клавиатуру"}
          >
            ⌨
          </button>
        </div>
      </div>

      <div className="converter-rows">
        {currencies.map((currency) => (
          <div
            key={currency}
            className={`converter-row ${currency === activeCurrency ? "converter-row-active" : ""}`}
            onClick={() => handleFocus(currency)}
          >
            <div className="converter-row-left">
              <span className="converter-flag">{FLAGS[currency] || "🏳️"}</span>
              <div className="converter-row-info">
                <span className="converter-row-code">{currency}</span>
                <span className="converter-row-rate">{getRateHint(currency)}</span>
              </div>
            </div>
            <div className="converter-row-right">
              <span className="converter-row-symbol">{SYMBOLS[currency] || ""}</span>
              <input
                ref={(el) => {
                  inputRefs.current[currency] = el;
                }}
                className="converter-row-input"
                inputMode={showNumpad ? "none" : "decimal"}
                readOnly={showNumpad}
                value={amounts[currency] || ""}
                onChange={(e) => handleAmountChange(currency, e.target.value)}
                onFocus={() => handleFocus(currency)}
                placeholder="0.00"
              />
              <button
                className="converter-row-remove"
                onClick={(e) => {
                  e.stopPropagation();
                  removeCurrency(currency);
                }}
                title="Убрать"
              >
                ×
              </button>
            </div>
          </div>
        ))}
      </div>

      <button className="converter-add-btn" onClick={() => setShowAddModal(true)}>
        + Добавить валюту
      </button>

      <div className="converter-footer">
        <span className="converter-midmarket">Среднерыночные курсы</span>
      </div>

      {errorMessage && (
        <div className="card" style={{ marginTop: 12, padding: 12 }}>
          <div style={{ marginBottom: 8 }}>{errorMessage}</div>
          {staleData && <div style={{ marginBottom: 8, opacity: 0.8 }}>Данные могут быть не обновлены.</div>}
          <button
            className="btn"
            onClick={() => fetchRates(activeCurrency, amounts[activeCurrency] || "1000")}
            disabled={busy}
          >
            Повторить
          </button>
        </div>
      )}

      {showNumpad && (
        <div className="numpad">
          <div className="numpad-grid">
            {["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "⌫"].map((key) => (
              <button
                key={key}
                className={`numpad-key ${key === "⌫" ? "numpad-key-action" : ""}`}
                onClick={() => handleNumpadKey(key)}
              >
                {key}
              </button>
            ))}
          </div>
        </div>
      )}

      {showAddModal && (
        <div className="modal-backdrop" onClick={() => setShowAddModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">Добавить валюту</span>
              <button className="modal-close" onClick={() => setShowAddModal(false)}>×</button>
            </div>
            <input
              className="input"
              placeholder="Поиск (USD, EUR...)"
              value={addSearch}
              onChange={(e) => setAddSearch(e.target.value)}
              autoFocus
            />
            <div className="converter-add-list">
              {availableToAdd.map((c) => (
                <button key={c} className="converter-add-item" onClick={() => addCurrency(c)}>
                  <span className="converter-flag">{FLAGS[c] || "🏳️"}</span>
                  <span className="converter-add-item-code">{c}</span>
                </button>
              ))}
              {availableToAdd.length === 0 && <div className="empty">Ничего не найдено</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
