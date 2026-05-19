import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { TripsPage } from "./pages/TripsPage";
import { TripDashboardPage } from "./pages/TripDashboardPage";
import { ExpensesPage } from "./pages/ExpensesPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { BalancesPage } from "./pages/BalancesPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ConverterPage } from "./pages/ConverterPage";
import { FlightsPage } from "./pages/FlightsPage";
import { TripFlightsPage } from "./pages/TripFlightsPage";

export function App() {
  return (
    <div className="app-container">
      <Routes>
        <Route path="/" element={<Navigate to="/trips" replace />} />
        <Route path="/trips" element={<TripsPage />} />
        <Route path="/trips/:tripId" element={<TripDashboardPage />} />
        <Route path="/trips/:tripId/expenses" element={<ExpensesPage />} />
        <Route path="/trips/:tripId/analytics" element={<AnalyticsPage />} />
        <Route path="/trips/:tripId/balances" element={<BalancesPage />} />
        <Route path="/trips/:tripId/documents" element={<DocumentsPage />} />
        <Route path="/trips/:tripId/flights" element={<TripFlightsPage />} />
        <Route path="/converter" element={<ConverterPage />} />
        <Route path="/flights" element={<FlightsPage />} />
        <Route path="/trips/:tripId/converter" element={<ConverterPage />} />
        <Route path="*" element={<Navigate to="/trips" replace />} />
      </Routes>
      <BottomBar />
    </div>
  );
}

/** Compact pill-style bottom navigation. */
function BottomBar() {
  return (
    <nav className="tab-bar">
      <NavLink
        to="/trips"
        className={({ isActive }) => isActive ? "active" : ""}
      >
        🏠 Поездки
      </NavLink>
      <NavLink
        to="/flights"
        className={({ isActive }) => isActive ? "active" : ""}
      >
        ✈️ Рейсы
      </NavLink>
      <NavLink
        to="/converter"
        className={({ isActive }) => isActive ? "active" : ""}
      >
        💱 Валюта
      </NavLink>
      <a href="https://t.me/Trave0Bot" target="_blank" rel="noreferrer">
        🤖 Бот
      </a>
    </nav>
  );
}
