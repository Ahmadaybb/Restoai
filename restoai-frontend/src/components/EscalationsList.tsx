import React, { useState, useEffect, useCallback } from "react";
import { EscalationSummary, Language } from "../types";
import { api } from "../api/client";
import { Loader2, ArrowRight } from "lucide-react";

interface EscalationsListProps {
  onSelectEscalation: (id: string) => void;
  onEscalationCountChange: (count: number) => void;
}

function langLabel(lang: Language): string {
  if (lang === "en") return "🇬🇧 EN";
  if (lang === "arabizi") return "🇱🇧 Arabizi";
  return "🇱🇧 AR";
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin === 1) return "1 min ago";
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr === 1) return "1 hr ago";
  if (diffHr < 24) return `${diffHr} hr ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}

export default function EscalationsList({ onSelectEscalation, onEscalationCountChange }: EscalationsListProps) {
  const [escalations, setEscalations] = useState<EscalationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getEscalations();
      if (!res) return;
      if (!res.ok) { setError(`Error loading escalations (${res.status})`); return; }
      const data: EscalationSummary[] = await res.json();
      setEscalations(data);
      onEscalationCountChange(data.length);
    } catch {
      setError("Network error — could not load escalations.");
    } finally {
      setLoading(false);
    }
  }, [onEscalationCountChange]);

  useEffect(() => { fetchList(); }, [fetchList]);

  return (
    <div id="escalations-list-screen" className="flex flex-col w-full h-full pb-16">
      <div className="px-6 pt-5 pb-3">
        <h1 className="text-3xl font-serif font-semibold tracking-tight text-farm-text mb-1">
          Active Escalations
        </h1>
        <p className="text-farm-text-muted text-sm font-sans mb-3">
          Conversations waiting for a human handler.
        </p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12 text-farm-text-muted font-sans text-sm">
          <Loader2 className="w-5 h-5 animate-spin mr-2 text-olive-600" />
          Loading escalations...
        </div>
      )}

      {error && (
        <div className="mx-4 mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between gap-3 text-sm text-amber-800 font-sans">
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchList}
            className="text-xs font-bold underline cursor-pointer shrink-0"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && escalations.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center text-farm-text-muted font-sans py-12 gap-3">
          <span className="text-4xl">🤝</span>
          <div className="text-center">
            <p className="font-semibold text-farm-text text-base">No escalations</p>
            <p className="text-sm mt-1">No conversations are waiting for a human handler.</p>
          </div>
        </div>
      )}

      <div className="flex-1 px-4 overflow-y-auto space-y-3">
        {escalations.map((esc) => {
          const isUnresolved = esc.status !== "RESOLVED";
          return (
            <div
              key={esc.conversation_id}
              onClick={() => onSelectEscalation(esc.conversation_id)}
              className="bg-white border border-farm-border rounded-lg p-4 cursor-pointer hover:border-olive-600 hover:shadow-sm transition-all relative group"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex flex-col flex-1 min-w-0">
                  {isUnresolved && (
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="relative flex h-2 w-2 shrink-0">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-red-600"></span>
                      </span>
                      <span className="text-[10px] font-bold text-red-700 uppercase tracking-wider">Needs Help</span>
                    </div>
                  )}
                  <h3 className="text-lg font-serif font-semibold text-farm-text group-hover:text-olive-700 transition-colors truncate">
                    {esc.customer_name}
                  </h3>
                  <div className="flex items-center gap-1 text-xs font-mono text-farm-text-muted mt-0.5">
                    <span>📞</span>
                    <span>{esc.customer_phone}</span>
                  </div>
                </div>

                <div className="flex flex-col items-end gap-1 shrink-0 ml-3">
                  <span className="text-xs font-mono text-farm-text-muted">
                    {langLabel(esc.language)}
                  </span>
                  <span className="text-[10px] font-mono text-zinc-400">
                    {relativeTime(esc.last_activity_at)}
                  </span>
                </div>
              </div>

              {esc.active_draft_summary && (
                <p className="text-xs bg-zinc-100 text-zinc-600 px-3 py-1 rounded-lg mt-1 line-clamp-1">
                  📋 {esc.active_draft_summary}
                </p>
              )}

              <div className="absolute top-1/2 right-3 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-1 bg-olive-50 rounded-full">
                <ArrowRight className="w-4 h-4 text-olive-600" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
