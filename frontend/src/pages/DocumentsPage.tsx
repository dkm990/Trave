import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { TravelDocument, Trip } from "../api/types";
import { FrogHero } from "../components/FrogHero";
import { FrogEmptyState } from "../components/FrogEmptyState";
import { getInitData, getCurrentUser } from "../telegram/webapp";

const TYPES = [
  { code: "", label: "Все" },
  { code: "ticket", label: "Билет" },
  { code: "hotel_booking", label: "Отель" },
  { code: "insurance", label: "Страховка" },
  { code: "itinerary", label: "Маршрут" },
  { code: "voucher", label: "Ваучер" },
  { code: "other", label: "Другое" },
];

const DOC_EMOJI: Record<string, string> = {
  ticket: "🎫",
  hotel_booking: "🏨",
  insurance: "🛡",
  itinerary: "🗺",
  voucher: "📋",
  other: "📄",
};

const DOC_LABELS: Record<string, string> = {
  ticket: "Билет",
  hotel_booking: "Отель",
  insurance: "Страховка",
  itinerary: "Маршрут",
  voucher: "Ваучер",
  other: "Другое",
};

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

function buildAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const initData = getInitData();
  if (initData) headers["X-Telegram-Init-Data"] = initData;
  const user = getCurrentUser();
  if (!initData) {
    const devId = localStorage.getItem("dev_user_id");
    if (devId) headers["X-Telegram-User-Id"] = devId;
    else if (user?.id) headers["X-Telegram-User-Id"] = String(user.id);
    else headers["X-Telegram-User-Id"] = "1";
  }
  return headers;
}

async function openDocument(doc: TravelDocument) {
  try {
    const resp = await fetch(`${BASE_URL}/api/documents/${doc.id}/download`, {
      headers: buildAuthHeaders(),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);

    if (doc.mime_type?.startsWith("image/")) {
      window.open(url, "_blank");
    } else {
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.title || `document-${doc.id}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }
  } catch (err) {
    alert(`Не удалось скачать документ: ${(err as Error).message}`);
  }
}

export function DocumentsPage() {
  const { tripId } = useParams();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [docs, setDocs] = useState<TravelDocument[]>([]);
  const [docType, setDocType] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!tripId) return;
    setTrip(await api<Trip>(`/api/trips/${tripId}`));
    const params = new URLSearchParams();
    if (docType) params.set("doc_type", docType);
    if (search.trim()) params.set("q", search.trim());
    const url = `/api/trips/${tripId}/documents${params.toString() ? `?${params}` : ""}`;
    setDocs(await api<TravelDocument[]>(url));
  }

  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId, docType]);

  if (!trip) return <div className="hint">Загрузка…</div>;

  return (
    <div>
      <Link to={`/trips/${trip.id}`} className="back-link">{trip.title}</Link>

      {/* Hero card */}
      <div className="hero-card">
        <div className="hero-card-content">
          <FrogHero variant="passport" size={40} />
          <div className="hero-card-text">
            <h1 className="hero-card-title">Документы</h1>
            <p className="hero-card-subtitle">
              Отправь билеты, брони или PDF в чат с ботом — они появятся здесь
            </p>
          </div>
        </div>
      </div>

      {/* Search / filter row */}
      <div className="row" style={{ marginBottom: 16 }}>
        <input
          className="input"
          placeholder="Поиск по документам…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") load(); }}
        />
        <select
          className="select"
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
        >
          {TYPES.map((t) => (
            <option key={t.code} value={t.code}>{t.label}</option>
          ))}
        </select>
        <button className="btn btn-secondary" onClick={() => load()}>
          Найти
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {docs.length === 0 ? (
        <FrogEmptyState
          variant="passport"
          title="Документов пока нет"
          subtitle="Отправь файлы в чат с ботом"
        />
      ) : (
        <>
          <h2 className="section-title">Найдено: {docs.length}</h2>
          {docs.map((d) => (
            <div
              key={d.id}
              className="doc-card"
              onClick={() => openDocument(d)}
              style={{ cursor: "pointer" }}
            >
              <div className="doc-icon">
                {DOC_EMOJI[d.doc_type] || "📄"}
              </div>
              <div className="doc-info">
                <div className="doc-title">{d.title}</div>
                <div className="doc-meta">
                  {DOC_LABELS[d.doc_type] || d.doc_type}
                  {" · "}
                  {d.visibility === "private" ? "🔒 Приватный" : "🌐 Публичный"}
                </div>
              </div>
              <span className="doc-badge">id {d.id}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
