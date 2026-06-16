import React, { useState, useEffect, useCallback } from "react";
import { Order, Language } from "../types";
import { api } from "../api/client";
import { RefreshCw, Smartphone, AlertCircle, ArrowRight, Loader2 } from "lucide-react";

interface OrdersQueueProps {
  refreshKey: number;
  onSelectOrder: (id: string) => void;
}

function langLabel(lang: Language): string {
  if (lang === "en") return "🇬🇧 EN";
  if (lang === "arabizi") return "🇱🇧 Arabizi";
  return "🇱🇧 AR";
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function OrdersQueue({ refreshKey, onSelectOrder }: OrdersQueueProps) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterOutOfZone, setFilterOutOfZone] = useState(false);
  const [countdown, setCountdown] = useState(30);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const flag = filterOutOfZone ? "out_of_zone_warning" : undefined;
      const res = await api.getOrders(flag);
      if (!res) return; // 401 handled — redirect in progress
      if (!res.ok) {
        setError(`Failed to load orders (${res.status})`);
        return;
      }
      const data: Order[] = await res.json();
      setOrders(data);
      setCountdown(30);
    } catch {
      setError("Network error — could not reach server.");
    } finally {
      setLoading(false);
    }
  }, [filterOutOfZone]);

  // Fetch on mount, filter change, or after a mutation (refreshKey bump)
  useEffect(() => {
    fetchOrders();
  }, [fetchOrders, refreshKey]);

  // Auto-refresh countdown; fires a real fetch when it hits zero
  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          fetchOrders();
          return 30;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [fetchOrders]);

  return (
    <div id="orders-queue-screen" className="flex flex-col w-full h-full pb-16">
      <div className="px-6 pt-5 pb-3">
        <h1 className="text-3xl font-serif font-semibold tracking-tight text-farm-text mb-1">
          Orders Queue
        </h1>
        <div className="flex items-center gap-2 text-farm-text-muted text-sm font-sans mb-3">
          <RefreshCw className="w-3.5 h-3.5 animate-spin-slow text-olive-600" />
          <span>
            Live dispatch dashboard. Refreshing in{" "}
            <span className="font-semibold text-olive-700 min-w-[20px] inline-block">{countdown}s</span>
          </span>
        </div>

        {/* System status widget */}
        <div className="flex items-center justify-between bg-white border border-farm-border rounded-lg px-4 py-3 shadow-xs mt-4">
          <div className="flex flex-col">
            <span className="text-xs font-semibold uppercase tracking-wider text-farm-text-muted">SYSTEM</span>
            <span className="text-sm font-bold text-farm-text">{error ? "OFFLINE" : "ONLINE"}</span>
          </div>
          <span className="relative flex h-3 w-3">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${error ? "bg-red-400" : "bg-blue-400"} opacity-75`}></span>
            <span className={`relative inline-flex rounded-full h-3 w-3 ${error ? "bg-red-500" : "bg-blue-500"}`}></span>
          </span>
        </div>

        {/* Out-of-zone filter toggle */}
        <div className="flex items-center gap-2 mt-3">
          <button
            type="button"
            onClick={() => setFilterOutOfZone(!filterOutOfZone)}
            className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border transition-colors cursor-pointer ${
              filterOutOfZone
                ? "bg-amber-100 border-amber-300 text-amber-800"
                : "bg-white border-farm-border text-farm-text-muted hover:border-zinc-300"
            }`}
          >
            <AlertCircle className="w-3.5 h-3.5" />
            Out of Zone Only
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-4 mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between gap-3 text-sm font-sans text-amber-800">
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchOrders}
            className="text-xs font-bold underline cursor-pointer shrink-0"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading (initial) */}
      {loading && orders.length === 0 && (
        <div className="flex-1 flex items-center justify-center text-farm-text-muted font-sans text-sm">
          <Loader2 className="w-5 h-5 animate-spin mr-2 text-olive-600" />
          Loading orders...
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && orders.length === 0 && (
        <div className="flex-1 flex items-center justify-center text-farm-text-muted font-sans text-sm">
          No orders to display.
        </div>
      )}

      {/* Orders list */}
      <div className="flex-1 px-4 overflow-y-auto space-y-3">
        {orders.map((order) => {
          const isDelivery = order.fulfillment === "delivery";
          const typeBadgeBg = isDelivery
            ? "bg-amber-50 text-amber-800 border-amber-200"
            : "bg-zinc-100 text-zinc-700 border-zinc-200";
          const isOutOfZone = order.flags.includes("out_of_zone_warning");
          const displayId = order.id.slice(0, 8);

          return (
            <div
              key={order.id}
              id={`order-card-${displayId}`}
              onClick={() => onSelectOrder(order.id)}
              className="bg-white border border-farm-border rounded-lg p-4 cursor-pointer hover:border-olive-600 hover:shadow-sm transition-all relative group"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex flex-col">
                  <span className="text-xs font-mono text-farm-text-muted">{formatTime(order.created_at)}</span>
                  <h3 className="text-lg font-semibold text-farm-text font-sans group-hover:text-olive-700 transition-colors">
                    {order.customer_name}
                  </h3>
                  <span className="text-xs font-mono text-farm-text-muted">#{displayId}</span>
                </div>
                <div className="text-right">
                  <span className="text-lg font-bold text-farm-text block">
                    ${order.estimated_total_usd.toFixed(2)}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1.5 text-sm text-farm-text font-semibold mb-3">
                <Smartphone className="w-3.5 h-3.5 text-farm-text-muted" />
                <span>{order.customer_phone}</span>
              </div>

              <div className="flex justify-between items-center pt-2 border-t border-zinc-100">
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${typeBadgeBg} font-medium`}>
                    {isDelivery ? "🚚 Delivery" : "📦 Pickup"}
                  </span>
                  <span className="text-sm" title={`Language: ${order.language}`}>
                    {langLabel(order.language)}
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {isOutOfZone && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 text-xs font-semibold">
                      <AlertCircle className="w-3 h-3 text-amber-600" />
                      Out of zone
                    </span>
                  )}
                  {order.state === "awaiting_dispatcher_review" && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200 text-xs font-semibold">
                      Pending
                    </span>
                  )}
                  {order.state === "entered_in_pos" && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold">
                      In POS
                    </span>
                  )}
                  {order.state === "cancelled" && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-zinc-100 text-zinc-600 border border-zinc-200 text-xs font-semibold">
                      Cancelled
                    </span>
                  )}
                </div>
              </div>

              <div className="absolute top-1/2 right-3 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-1 bg-olive-50 rounded-full">
                <ArrowRight className="w-4 h-4 text-olive-600" />
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="px-6 py-4 flex items-center justify-between border-t border-farm-border bg-white mt-auto">
        <span className="text-sm font-sans text-farm-text-muted">
          Showing {orders.length} order{orders.length !== 1 ? "s" : ""}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            className="p-1 px-2 bg-white hover:bg-zinc-50 border border-farm-border rounded text-farm-text-muted disabled:opacity-50 cursor-pointer"
            disabled
          >
            &lt;
          </button>
          <button
            type="button"
            className="p-1 px-2 bg-white hover:bg-zinc-50 border border-farm-border rounded text-farm-text-muted disabled:opacity-50 cursor-pointer"
            disabled
          >
            &gt;
          </button>
        </div>
      </div>
    </div>
  );
}
