import React, { useState, useEffect, useCallback } from "react";
import { Reservation, ReservationFromAPI, ActiveTab } from "./types";
import { api } from "./api/client";
import OrdersQueue from "./components/OrdersQueue";
import OrderDetails from "./components/OrderDetails";
import ReservationsList from "./components/ReservationsList";
import NewReservation from "./components/NewReservation";
import EscalationsList from "./components/EscalationsList";
import ChatEscalation from "./components/ChatEscalation";

import {
  Calendar,
  ShieldAlert,
  Grid2X2,
  Settings,
  Plus,
} from "lucide-react";

const SEATING_SECTION: Record<string, { section: string; sectionName: string }> = {
  indoor_smoking:     { section: "IS", sectionName: "Indoor – Smoking" },
  indoor_non_smoking: { section: "IN", sectionName: "Indoor – Non-Smoking" },
  outdoor_terrace:    { section: "T",  sectionName: "Terrace" },
  outdoor_non_terrace:{ section: "O",  sectionName: "Outdoor" },
};

function mapAPIReservation(r: ReservationFromAPI): Reservation {
  const { section, sectionName } = SEATING_SECTION[r.seating_preference] ?? { section: "?", sectionName: r.seating_preference };
  return {
    id: r.id,
    customerName: r.name,
    phone: r.phone,
    pax: r.party_size,
    time: r.time.substring(0, 5),   // "20:30:00" → "20:30"
    date: r.date,
    section,
    sectionName,
    notes: `Ref: ${r.reference}`,
    status: r.state === "cancelled" ? "Cancelled" : "Pending",
  };
}

export default function App() {
  // Auth — derived from localStorage on init
  const [token, setToken] = useState(() => localStorage.getItem("restoai_bearer_token") || "");
  const [loginName, setLoginName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");

  // Navigation
  const [activeTab, setActiveTab] = useState<ActiveTab>("Floor");
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [showNewReservationForm, setShowNewReservationForm] = useState(false);
  const [selectedEscalationId, setSelectedEscalationId] = useState<string | null>(null);

  // Reservations — fetched from API, local mutations (Arrive/No Show) layered on top
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [reservationsLoading, setReservationsLoading] = useState(false);

  const fetchReservations = useCallback(async () => {
    if (!token) return;
    setReservationsLoading(true);
    try {
      const res = await api.getReservations();
      if (!res || !res.ok) return;
      const data: ReservationFromAPI[] = await res.json();
      setReservations((prev) => {
        // Preserve local dispatcher status (Arrived / No Show) for IDs already known
        const localStatus = new Map(prev.map((r) => [r.id, r.status]));
        return data.map((r) => {
          const mapped = mapAPIReservation(r);
          const existing = localStatus.get(r.id);
          if (existing === "Arrived" || existing === "No Show") {
            mapped.status = existing;
          }
          return mapped;
        });
      });
    } finally {
      setReservationsLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchReservations(); }, [fetchReservations]);

  // Escalation badge count reported up from EscalationsList
  const [escalationCount, setEscalationCount] = useState(0);

  // Bump this to tell OrdersQueue to re-fetch after a mutation
  const [ordersRefreshKey, setOrdersRefreshKey] = useState(0);

  const isExpired = new URLSearchParams(window.location.search).get("expired") === "1";

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginName.trim() || !loginPassword.trim()) {
      setLoginError("Both name and password are required.");
      return;
    }
    localStorage.setItem("restoai_dispatcher_name", loginName.trim());
    localStorage.setItem("restoai_bearer_token", loginPassword.trim());
    setToken(loginPassword.trim());
    if (window.location.search) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem("restoai_bearer_token");
    localStorage.removeItem("restoai_dispatcher_name");
    setToken("");
  };

  const handleUpdateReservation = (updated: Reservation) => {
    setReservations((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  };

  const handleCreateReservation = (newRes: Reservation) => {
    setReservations((prev) => [newRes, ...prev]);
    setShowNewReservationForm(false);
    setActiveTab("Bookings");
    // Re-fetch so the manually-added entry is confirmed from the source of truth
    fetchReservations();
  };

  const handleFloatingAction = () => {
    setShowNewReservationForm(true);
    setSelectedOrderId(null);
  };

  // ── Login Screen ────────────────────────────────────────────────────────────
  if (!token) {
    return (
      <div className="flex justify-center bg-zinc-900 min-h-screen">
        <div className="w-full max-w-md bg-farm-bg min-h-screen shadow-2xl flex flex-col relative border-x border-zinc-800">
          <div className="flex-1 flex flex-col items-center justify-center p-8">
            <div className="flex items-center gap-3 mb-10">
              <div className="w-10 h-10 rounded-xl bg-olive-50 border border-olive-100 flex items-center justify-center text-olive-700 shadow-xs">
                <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <div className="text-sm uppercase font-extrabold tracking-widest text-[#446137]">RESTOAI</div>
                <div className="text-xs font-medium text-zinc-400 uppercase tracking-tight font-sans">Dispatcher Portal</div>
              </div>
            </div>

            <div className="w-full bg-white border border-farm-border rounded-2xl p-6 shadow-sm">
              <h2 className="text-xl font-serif font-bold text-farm-text mb-1">Sign In</h2>
              <p className="text-sm text-farm-text-muted font-sans mb-6">Enter your dispatcher credentials to continue.</p>

              {isExpired && (
                <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800 font-sans">
                  Your session expired. Please sign in again.
                </div>
              )}
              {loginError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-sans">
                  {loginError}
                </div>
              )}

              <form onSubmit={handleLogin} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-farm-text-muted uppercase tracking-wider mb-1.5 font-sans">
                    Your Name
                  </label>
                  <input
                    type="text"
                    value={loginName}
                    onChange={(e) => { setLoginName(e.target.value); setLoginError(""); }}
                    placeholder="e.g. Ahmad"
                    className="w-full h-11 px-3 border border-zinc-200 rounded-lg text-sm font-sans bg-zinc-50 focus:outline-none focus:border-olive-600 focus:bg-white text-farm-text"
                    autoComplete="name"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-farm-text-muted uppercase tracking-wider mb-1.5 font-sans">
                    Password (API Token)
                  </label>
                  <input
                    type="password"
                    value={loginPassword}
                    onChange={(e) => { setLoginPassword(e.target.value); setLoginError(""); }}
                    placeholder="Bearer token from backend"
                    className="w-full h-11 px-3 border border-zinc-200 rounded-lg text-sm font-sans bg-zinc-50 focus:outline-none focus:border-olive-600 focus:bg-white text-farm-text"
                    autoComplete="current-password"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full h-11 bg-olive-700 hover:bg-olive-800 text-white font-bold text-sm rounded-lg transition-colors cursor-pointer mt-2"
                >
                  Sign In
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Main App ────────────────────────────────────────────────────────────────
  return (
    <div className="flex justify-center bg-zinc-900 min-h-screen">
      <div className="w-full max-w-md bg-farm-bg min-h-screen shadow-2xl flex flex-col relative border-x border-zinc-800">

        {!showNewReservationForm && (
          <header className="bg-white border-b border-farm-border px-4 py-3 flex items-center justify-between sticky top-0 z-40">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-olive-50 border border-olive-100 flex items-center justify-center text-olive-700 font-bold text-lg select-none shadow-xs">
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div className="flex flex-col">
                <span className="text-xs uppercase font-extrabold tracking-widest text-[#446137]">RESTOAI</span>
                <span className="text-[10px] font-medium text-zinc-400 uppercase tracking-tight font-sans leading-none mt-0.5">Lakkis Farm</span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {escalationCount > 0 && (
                <button
                  type="button"
                  onClick={() => { setActiveTab("Admin"); setSelectedOrderId(null); }}
                  className="flex items-center justify-center w-7 h-7 bg-red-100 hover:bg-red-200 border border-red-200 rounded-full text-red-600 relative cursor-pointer"
                  title="Active escalation!"
                >
                  <ShieldAlert className="w-4 h-4 animate-bounce text-red-600" />
                  <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-600 rounded-full border border-white"></span>
                </button>
              )}
              <button
                type="button"
                onClick={handleSignOut}
                className="text-xs font-bold text-olive-700 hover:text-olive-900 border border-olive-100 hover:bg-olive-50 px-2.5 py-1 rounded-md transition-all cursor-pointer"
              >
                Sign Out
              </button>
            </div>
          </header>
        )}

        {showNewReservationForm ? (
          <div className="flex-1 flex flex-col">
            <NewReservation
              onBack={() => setShowNewReservationForm(false)}
              onSubmit={handleCreateReservation}
            />
          </div>
        ) : (
          <main className="flex-1 flex flex-col relative overflow-hidden">

            {selectedOrderId !== null ? (
              <div className="absolute inset-0 bg-farm-bg z-30 animate-fade-in flex flex-col">
                <OrderDetails
                  orderId={selectedOrderId}
                  onBack={() => setSelectedOrderId(null)}
                  onOrderMutated={() => setOrdersRefreshKey((k) => k + 1)}
                />
              </div>
            ) : null}

            <div className="flex-1">
              {activeTab === "Floor" && (
                <OrdersQueue
                  refreshKey={ordersRefreshKey}
                  onSelectOrder={(id) => setSelectedOrderId(id)}
                />
              )}

              {activeTab === "Bookings" && (
                <ReservationsList
                  reservations={reservations}
                  loading={reservationsLoading}
                  onAddReservation={handleCreateReservation}
                  onUpdateReservation={handleUpdateReservation}
                  onTriggerNewReservationForm={handleFloatingAction}
                />
              )}

              {activeTab === "Admin" && (
                selectedEscalationId !== null
                  ? (
                    <ChatEscalation
                      conversationId={selectedEscalationId}
                      onBack={() => setSelectedEscalationId(null)}
                    />
                  ) : (
                    <EscalationsList
                      onSelectEscalation={setSelectedEscalationId}
                      onEscalationCountChange={setEscalationCount}
                    />
                  )
              )}
            </div>
          </main>
        )}

        {!showNewReservationForm && (
          <nav className="fixed bottom-0 left-0 right-0 max-w-md mx-auto h-16 bg-white border-t border-farm-border flex items-center justify-between px-5 z-40">
            <button
              type="button"
              onClick={() => { setActiveTab("Floor"); setSelectedOrderId(null); setSelectedEscalationId(null); }}
              className={`flex flex-col items-center justify-center p-2 cursor-pointer transition-colors ${activeTab === "Floor" ? "text-olive-700" : "text-zinc-400 hover:text-zinc-600"}`}
            >
              <Grid2X2 className="w-5 h-5" />
              <span className="text-[9px] font-bold tracking-wider uppercase mt-1">Floor</span>
            </button>

            <button
              type="button"
              onClick={() => { setActiveTab("Bookings"); setSelectedOrderId(null); setSelectedEscalationId(null); }}
              className={`flex flex-col items-center justify-center p-2 cursor-pointer transition-colors ${activeTab === "Bookings" ? "text-olive-700" : "text-zinc-400 hover:text-zinc-600"}`}
            >
              <Calendar className="w-5 h-5" />
              <span className="text-[9px] font-bold tracking-wider uppercase mt-1">Bookings</span>
            </button>

            <div className="relative -top-4">
              <button
                type="button"
                id="floating-new-res-action"
                onClick={handleFloatingAction}
                className="w-13 h-13 bg-olive-700 hover:bg-olive-800 text-white rounded-full flex items-center justify-center shadow-lg hover:shadow-xl transition-all select-none cursor-pointer transform hover:scale-105"
                title="Create a table reservation"
              >
                <Plus className="w-6 h-6 text-white" strokeWidth={3} />
              </button>
            </div>

            <button
              type="button"
              onClick={() => { setActiveTab("Admin"); setSelectedOrderId(null); }}
              className={`flex flex-col items-center justify-center p-2 cursor-pointer transition-colors relative ${activeTab === "Admin" ? "text-olive-700" : "text-zinc-400 hover:text-zinc-600"}`}
            >
              <Settings className="w-5 h-5" />
              <span className="text-[9px] font-bold tracking-wider uppercase mt-1">Admin</span>
              {escalationCount > 0 && (
                <span className="absolute top-1.5 right-1 w-2 h-2 bg-red-600 rounded-full border border-white"></span>
              )}
            </button>
          </nav>
        )}

      </div>
    </div>
  );
}
