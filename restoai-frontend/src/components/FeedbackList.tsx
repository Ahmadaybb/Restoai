import React, { useState, useEffect, useCallback } from "react";
import { FeedbackEntry, FeedbackSummary, FeedbackResponse } from "../types";
import { api } from "../api/client";
import { RefreshCw, Loader2, MessageCircle } from "lucide-react";

type FilterKey = 'all' | 'good' | 'neutral' | 'bad' | 'pending' | 'no_response';

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all",         label: "All" },
  { key: "good",        label: "✅ Good" },
  { key: "neutral",     label: "😐 Neutral" },
  { key: "bad",         label: "❌ Bad" },
  { key: "pending",     label: "⏳ Pending" },
  { key: "no_response", label: "🔇 No Response" },
];

function Stars({ rating }: { rating: number | null }) {
  if (rating === null) return <span className="text-zinc-400 text-sm">—</span>;
  const filled = Math.max(0, Math.min(5, rating));
  return (
    <span className="text-base leading-none">
      {"⭐".repeat(filled)}{"☆".repeat(5 - filled)}
    </span>
  );
}

function SentimentBadge({ sentiment, status }: { sentiment: FeedbackEntry["sentiment"]; status: FeedbackEntry["status"] }) {
  if (status === "no_response") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs border bg-zinc-100 text-zinc-400 border-zinc-200">
        No Response
      </span>
    );
  }
  if (sentiment === null || status === "pending") {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs border bg-zinc-100 text-zinc-500 border-zinc-200">
        Awaiting
      </span>
    );
  }
  const styles = {
    good:    "bg-emerald-50 text-emerald-700 border-emerald-200",
    neutral: "bg-amber-50 text-amber-700 border-amber-200",
    bad:     "bg-red-50 text-red-700 border-red-200",
  } as const;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs border font-medium ${styles[sentiment]}`}>
      {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
    </span>
  );
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex-1 bg-white border border-farm-border rounded-lg px-3 py-3 shadow-xs">
      <span className={`text-xl font-bold ${color}`}>{value}</span>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-farm-text-muted mt-0.5">{label}</p>
    </div>
  );
}

export default function FeedbackList() {
  const [entries, setEntries] = useState<FeedbackEntry[]>([]);
  const [summary, setSummary] = useState<FeedbackSummary>({ good: 0, bad: 0, neutral: 0, no_response: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");
  const [countdown, setCountdown] = useState(60);

  const fetchFeedback = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const isSentimentFilter = activeFilter === "good" || activeFilter === "bad" || activeFilter === "neutral";
      const isStatusFilter = activeFilter === "pending" || activeFilter === "no_response";
      const sentiment = isSentimentFilter ? activeFilter : undefined;
      const status = isStatusFilter ? activeFilter : undefined;

      const res = await api.getFeedback(sentiment, status);
      if (!res) return;
      if (!res.ok) {
        setError(`Failed to load feedback (${res.status})`);
        return;
      }
      const data: FeedbackResponse = await res.json();
      setEntries(data.feedback);
      setSummary(data.summary);
      setCountdown(60);
    } catch {
      setError("Network error — could not reach server.");
    } finally {
      setLoading(false);
    }
  }, [activeFilter]);

  useEffect(() => {
    fetchFeedback();
  }, [fetchFeedback]);

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          fetchFeedback();
          return 60;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [fetchFeedback]);

  return (
    <div className="flex flex-col w-full h-full pb-16">
      <div className="px-6 pt-5 pb-3">
        <h1 className="text-3xl font-serif font-semibold tracking-tight text-farm-text mb-1">
          Customer Feedback
        </h1>
        <div className="flex items-center gap-2 text-farm-text-muted text-sm font-sans mb-4">
          <RefreshCw className="w-3.5 h-3.5 animate-spin-slow text-olive-600" />
          <span>
            Live dispatch dashboard. Refreshing in{" "}
            <span className="font-semibold text-olive-700 min-w-[20px] inline-block">{countdown}s</span>
          </span>
        </div>

        {/* Summary bar */}
        <div className="flex gap-2 mb-4">
          <StatCard label="Good" value={summary.good} color="text-emerald-600" />
          <StatCard label="Neutral" value={summary.neutral} color="text-amber-600" />
          <StatCard label="Bad" value={summary.bad} color="text-red-600" />
        </div>

        {/* Filter chips */}
        <div className="flex gap-2 overflow-x-auto pb-1 hide-scrollbar">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setActiveFilter(f.key)}
              className={`shrink-0 text-xs font-semibold px-3 py-1.5 rounded-full border transition-colors cursor-pointer whitespace-nowrap ${
                activeFilter === f.key
                  ? "bg-olive-700 text-white border-olive-700"
                  : "bg-white text-farm-text-muted border-farm-border hover:border-zinc-300"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-4 mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between gap-3 text-sm font-sans text-amber-800">
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchFeedback}
            className="text-xs font-bold underline cursor-pointer shrink-0"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && entries.length === 0 && (
        <div className="flex-1 flex items-center justify-center text-farm-text-muted font-sans text-sm">
          <Loader2 className="w-5 h-5 animate-spin mr-2 text-olive-600" />
          Loading feedback...
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && entries.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-farm-text-muted font-sans">
          <MessageCircle className="w-12 h-12 text-zinc-300" />
          <p className="text-base font-semibold text-farm-text">No feedback yet</p>
          <p className="text-sm text-center px-8">
            Feedback will appear here after customers rate their orders.
          </p>
        </div>
      )}

      {/* Feedback cards */}
      <div className="flex-1 px-4 overflow-y-auto space-y-3">
        {entries.map((entry) => (
          <div
            key={entry.id}
            className="bg-white border border-farm-border rounded-lg p-4"
          >
            {/* Row 1: time + stars */}
            <div className="flex justify-between items-start mb-1.5">
              <span className="text-xs font-mono text-farm-text-muted">
                {formatTime(entry.feedback_requested_at)}
              </span>
              <Stars rating={entry.star_rating} />
            </div>

            {/* Row 2: name + sentiment badge */}
            <div className="flex justify-between items-center mb-1">
              <h3 className="text-base font-semibold text-farm-text font-sans">
                {entry.customer_name}
              </h3>
              <SentimentBadge sentiment={entry.sentiment} status={entry.status} />
            </div>

            {/* Phone */}
            <p className="text-xs text-farm-text-muted font-sans mb-3">
              📞 {entry.customer_phone || "—"}
            </p>

            {/* Order summary */}
            {entry.items_summary && (
              <div className="border-t border-zinc-100 pt-2 pb-2">
                <p className="text-xs font-sans text-farm-text-muted">
                  <span className="font-semibold text-farm-text">Order:</span>{" "}
                  {entry.items_summary}
                </p>
              </div>
            )}

            {/* Comment */}
            <div className="border-t border-zinc-100 pt-2">
              {entry.comment ? (
                <p className="text-sm font-sans text-farm-text italic">
                  "{entry.comment}"
                </p>
              ) : (
                <p className="text-xs font-sans text-farm-text-muted italic">
                  No comment provided.
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
