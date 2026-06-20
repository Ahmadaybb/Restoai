import React, { useState, useEffect } from "react";
import {
  User,
  Shield,
  Wifi,
  WifiOff,
  Phone,
  MapPin,
  Clock,
  ChevronRight,
  LogOut,
  MessageCircle,
} from "lucide-react";
import { api } from "../api/client";

interface SettingsPanelProps {
  onSignOut: () => void;
  onViewFeedback?: () => void;
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-zinc-100 last:border-0">
      <div className="p-1.5 bg-zinc-50 rounded-lg text-farm-text-muted shrink-0">{icon}</div>
      <div className="flex flex-col min-w-0">
        <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest leading-none mb-0.5">{label}</span>
        <span className="text-sm font-semibold text-farm-text truncate">{value}</span>
      </div>
    </div>
  );
}

export default function SettingsPanel({ onSignOut, onViewFeedback }: SettingsPanelProps) {
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [checkingApi, setCheckingApi] = useState(false);

  const dispatcherName = api.dispatcherName() || "—";
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dateStr = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });

  const checkApiStatus = async () => {
    setCheckingApi(true);
    try {
      const res = await api.getOrders();
      setApiOnline(res !== null && res.ok);
    } catch {
      setApiOnline(false);
    } finally {
      setCheckingApi(false);
    }
  };

  useEffect(() => {
    checkApiStatus();
  }, []);

  return (
    <div className="flex flex-col w-full h-full pb-16 overflow-y-auto">
      {/* Header */}
      <div className="px-4 pt-5 pb-4 border-b border-farm-border bg-white">
        <h1 className="text-xl font-serif font-bold text-farm-text">Settings</h1>
        <p className="text-xs text-farm-text-muted font-sans mt-0.5">{dateStr} · {timeStr}</p>
      </div>

      <div className="px-4 pt-4 space-y-4">

        {/* Dispatcher profile */}
        <div className="bg-white border border-farm-border rounded-xl overflow-hidden shadow-xs">
          <div className="px-4 py-3 bg-zinc-50 border-b border-zinc-100">
            <span className="text-[10px] font-extrabold uppercase tracking-widest text-farm-text-muted">Dispatcher</span>
          </div>
          <div className="px-4">
            <InfoRow
              icon={<User className="w-4 h-4" />}
              label="Signed in as"
              value={dispatcherName}
            />
            <InfoRow
              icon={<Shield className="w-4 h-4" />}
              label="Role"
              value="Dispatcher"
            />
          </div>
        </div>

        {/* System status */}
        <div className="bg-white border border-farm-border rounded-xl overflow-hidden shadow-xs">
          <div className="px-4 py-3 bg-zinc-50 border-b border-zinc-100">
            <span className="text-[10px] font-extrabold uppercase tracking-widest text-farm-text-muted">System</span>
          </div>
          <div className="px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-1.5 bg-zinc-50 rounded-lg shrink-0">
                {apiOnline === null || checkingApi
                  ? <Wifi className="w-4 h-4 text-zinc-300" />
                  : apiOnline
                    ? <Wifi className="w-4 h-4 text-emerald-600" />
                    : <WifiOff className="w-4 h-4 text-red-500" />
                }
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest leading-none mb-0.5">API Server</span>
                <span className={`text-sm font-bold ${apiOnline === null || checkingApi ? "text-zinc-400"
                    : apiOnline ? "text-emerald-600"
                      : "text-red-600"
                  }`}>
                  {checkingApi ? "Checking…" : apiOnline === null ? "—" : apiOnline ? "Online ●" : "Offline ●"}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={checkApiStatus}
              disabled={checkingApi}
              className="text-xs font-bold text-olive-700 hover:text-olive-900 border border-olive-100 hover:bg-olive-50 px-2.5 py-1.5 rounded-lg transition-all cursor-pointer disabled:opacity-50"
            >
              Refresh
            </button>
          </div>

          <div className="px-4 border-t border-zinc-100 py-3 flex items-center gap-3">
            <div className="p-1.5 bg-zinc-50 rounded-lg shrink-0">
              <Clock className="w-4 h-4 text-farm-text-muted" />
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest leading-none mb-0.5">Queue refresh</span>
              <span className="text-sm font-semibold text-farm-text">Every 30 seconds</span>
            </div>
          </div>
        </div>

        {/* Restaurant info */}
        <div className="bg-white border border-farm-border rounded-xl overflow-hidden shadow-xs">
          <div className="px-4 py-3 bg-zinc-50 border-b border-zinc-100">
            <span className="text-[10px] font-extrabold uppercase tracking-widest text-farm-text-muted">Restaurant</span>
          </div>
          <div className="px-4">
            <InfoRow
              icon={<span className="text-base leading-none">🌿</span>}
              label="Name"
              value="Lakkis Farm"
            />
            <InfoRow
              icon={<MapPin className="w-4 h-4" />}
              label="Location"
              value="Beirut, Lebanon"
            />
            <InfoRow
              icon={<Phone className="w-4 h-4" />}
              label="Telegram Bot"
              value="@restoai_bot"
            />
          </div>
        </div>

        {/* Quick links */}
        <div className="bg-white border border-farm-border rounded-xl overflow-hidden shadow-xs">
          <div className="px-4 py-3 bg-zinc-50 border-b border-zinc-100">
            <span className="text-[10px] font-extrabold uppercase tracking-widest text-farm-text-muted">Quick Links</span>
          </div>
          <a
            href="https://menu.omegasoftware.ca/mlmksal"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between px-4 py-3.5 hover:bg-zinc-50 transition-colors cursor-pointer border-b border-zinc-100"
          >
            <div className="flex items-center gap-3">
              <div className="p-1.5 bg-zinc-50 rounded-lg">
                <span className="text-base leading-none">🍽️</span>
              </div>
              <span className="text-sm font-semibold text-farm-text">View Full Menu</span>
            </div>
            <ChevronRight className="w-4 h-4 text-zinc-400" />
          </a>
          {onViewFeedback && (
            <button
              type="button"
              onClick={onViewFeedback}
              className="w-full flex items-center justify-between px-4 py-3.5 hover:bg-zinc-50 transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-zinc-50 rounded-lg">
                  <MessageCircle className="w-4 h-4 text-farm-text-muted" />
                </div>
                <span className="text-sm font-semibold text-farm-text">Customer Feedback</span>
              </div>
              <ChevronRight className="w-4 h-4 text-zinc-400" />
            </button>
          )}
        </div>

        {/* App info */}
        <div className="bg-white border border-farm-border rounded-xl overflow-hidden shadow-xs">
          <div className="px-4 py-3 bg-zinc-50 border-b border-zinc-100">
            <span className="text-[10px] font-extrabold uppercase tracking-widest text-farm-text-muted">About</span>
          </div>
          <div className="px-4">
            <InfoRow
              icon={<span className="text-base leading-none">🤖</span>}
              label="Platform"
              value="RestoAI Dispatcher v1.0"
            />
            <InfoRow
              icon={<span className="text-base leading-none">⚡</span>}
              label="Powered by"
              value=" Telegram"
            />
          </div>
        </div>

        {/* Sign out */}
        <button
          type="button"
          onClick={onSignOut}
          className="w-full flex items-center justify-center gap-2 h-11 border border-red-200 text-red-600 hover:bg-red-50 font-bold text-sm rounded-xl cursor-pointer transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>

        <div className="pb-2 text-center text-[10px] text-zinc-300 font-mono">
          RestoAI · Lakkis Farm · {new Date().getFullYear()}
        </div>
      </div>
    </div>
  );
}
