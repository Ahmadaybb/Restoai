import React, { useState, useEffect, useCallback } from "react";
import { Order, Language } from "../types";
import { api } from "../api/client";
import {
  RefreshCw,
  Smartphone,
  AlertCircle,
  Loader2,
  X,
  Check,
  Truck,
  CheckCircle,
} from "lucide-react";

interface OrdersQueueProps {
  refreshKey: number;
  onSelectOrder: (id: string) => void;
  onOrderMutated: () => void;
}

function langLabel(lang: Language): string {
  if (lang === "en") return "🇬🇧";
  if (lang === "arabizi") return "🇱🇧";
  return "🇱🇧";
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function stateBadge(order: Order) {
  if (order.state === "awaiting_dispatcher_review")
    return <span className="text-[10px] font-bold uppercase tracking-wider text-blue-600 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">Pending</span>;
  if (order.state === "entered_in_pos")
    return <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">Being Made</span>;
  if (order.state === "out_for_delivery")
    return <span className="text-[10px] font-bold uppercase tracking-wider text-sky-700 bg-sky-50 border border-sky-200 px-2 py-0.5 rounded-full">On the Way</span>;
  if (order.state === "delivered")
    return <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">✓ Done</span>;
  if (order.state === "cancelled")
    return <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 bg-zinc-100 border border-zinc-200 px-2 py-0.5 rounded-full">Cancelled</span>;
  return null;
}

function advanceLabel(order: Order): string {
  if (order.state === "awaiting_dispatcher_review") return "Start Making";
  if (order.state === "entered_in_pos" && order.fulfillment === "delivery") return "On the Way";
  return "Finish";
}

function advanceBtnClass(order: Order): string {
  if (order.state === "awaiting_dispatcher_review") return "bg-amber-500 hover:bg-amber-600 active:bg-amber-700";
  if (order.state === "entered_in_pos" && order.fulfillment === "delivery") return "bg-sky-600 hover:bg-sky-700 active:bg-sky-800";
  return "bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800";
}

function AdvanceIcon({ order }: { order: Order }) {
  if (order.state === "awaiting_dispatcher_review") return <Check className="w-3.5 h-3.5" />;
  if (order.state === "entered_in_pos" && order.fulfillment === "delivery") return <Truck className="w-3.5 h-3.5" />;
  return <CheckCircle className="w-3.5 h-3.5" />;
}

const isActiveState = (state: string) =>
  state === "awaiting_dispatcher_review" ||
  state === "entered_in_pos" ||
  state === "out_for_delivery";

export default function OrdersQueue({ refreshKey, onSelectOrder, onOrderMutated }: OrdersQueueProps) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(30);

  // Per-card action loading
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  // Cancel modal
  const [cancelModal, setCancelModal] = useState<{ id: string; name: string } | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelLoading, setCancelLoading] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getOrders();
      if (!res) return;
      if (!res.ok) { setError(`Failed to load orders (${res.status})`); return; }
      const json = await res.json() as { orders: Order[] };
      setOrders(json.orders ?? []);
      setCountdown(30);
    } catch {
      setError("Network error — could not reach server.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchOrders(); }, [fetchOrders, refreshKey]);

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) { fetchOrders(); return 30; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [fetchOrders]);

  const handleAdvance = async (e: React.MouseEvent, order: Order) => {
    e.stopPropagation();
    if (!api.dispatcherName()) return;
    setActionLoadingId(order.id);
    try {
      const res =
        order.state === "awaiting_dispatcher_review"
          ? await api.enterInPos(order.id)
          : order.state === "entered_in_pos" && order.fulfillment === "delivery"
          ? await api.markOutForDelivery(order.id)
          : await api.markDelivered(order.id);
      if (res?.ok) { onOrderMutated(); await fetchOrders(); }
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleCancelClick = (e: React.MouseEvent, order: Order) => {
    e.stopPropagation();
    setCancelModal({ id: order.id, name: order.customer_name });
    setCancelReason("");
    setCancelError(null);
  };

  const handleConfirmCancel = async () => {
    if (!cancelReason.trim() || !cancelModal) { setCancelError("A reason is required."); return; }
    if (!api.dispatcherName()) { setCancelError("Sign out and sign in again."); return; }
    setCancelLoading(true);
    setCancelError(null);
    try {
      const res = await api.cancelOrder(cancelModal.id, cancelReason.trim());
      if (res?.ok) { setCancelModal(null); onOrderMutated(); await fetchOrders(); }
      else setCancelError(`Error (${res?.status})`);
    } catch { setCancelError("Network error."); }
    finally { setCancelLoading(false); }
  };

  // Split into delivery vs pickup, active orders first then done
  const activeOrders = orders.filter((o) => isActiveState(o.state));
  const doneOrders = orders.filter((o) => !isActiveState(o.state));
  const deliveryActive = activeOrders.filter((o) => o.fulfillment === "delivery");
  const pickupActive = activeOrders.filter((o) => o.fulfillment === "pickup");
  const deliveryDone = doneOrders.filter((o) => o.fulfillment === "delivery");
  const pickupDone = doneOrders.filter((o) => o.fulfillment === "pickup");

  const renderCard = (order: Order) => {
    const displayId = order.id.slice(0, 8);
    const isActive = isActiveState(order.state);
    const isLoadingThis = actionLoadingId === order.id;

    return (
      <div
        key={order.id}
        onClick={() => onSelectOrder(order.id)}
        className="bg-white border border-farm-border rounded-xl p-4 cursor-pointer hover:border-olive-400 transition-all shadow-xs group"
      >
        {/* Header row */}
        <div className="flex justify-between items-start mb-2">
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-farm-text leading-tight truncate group-hover:text-olive-700">
              {order.customer_name}
            </h3>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="text-[10px] font-mono text-zinc-400">#{displayId}</span>
              <span className="text-zinc-300">·</span>
              <span className="text-[10px] font-mono text-zinc-400">{formatTime(order.created_at)}</span>
              <span className="text-zinc-300">·</span>
              <span className="text-[10px]">{langLabel(order.language)}</span>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0 ml-2">
            <span className="text-sm font-bold text-farm-text">${order.estimated_total_usd.toFixed(2)}</span>
            {stateBadge(order)}
          </div>
        </div>

        {/* Phone */}
        <div className="flex items-center gap-1.5 text-xs text-farm-text-muted mb-3">
          <Smartphone className="w-3 h-3 shrink-0" />
          <span className="font-mono">{order.customer_phone}</span>
          {order.flags.includes("out_of_zone_warning") && (
            <span className="ml-1 flex items-center gap-0.5 text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full">
              <AlertCircle className="w-2.5 h-2.5" /> Out of zone
            </span>
          )}
        </div>

        {/* Action buttons for active orders */}
        {isActive && (
          <div
            className="flex items-center gap-2 pt-3 border-t border-zinc-100"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={(e) => handleAdvance(e, order)}
              disabled={isLoadingThis}
              className={`flex-1 h-9 rounded-lg font-bold text-xs text-white flex items-center justify-center gap-1.5 transition-all cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed ${advanceBtnClass(order)}`}
            >
              {isLoadingThis
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : <AdvanceIcon order={order} />
              }
              {isLoadingThis ? "Saving..." : advanceLabel(order)}
            </button>
            <button
              type="button"
              onClick={(e) => handleCancelClick(e, order)}
              disabled={isLoadingThis}
              title="Cancel order"
              className="w-9 h-9 flex items-center justify-center rounded-lg border border-red-200 text-red-400 hover:bg-red-50 hover:text-red-600 cursor-pointer transition-colors disabled:opacity-40"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    );
  };

  const renderSection = (title: string, emoji: string, active: Order[], done: Order[]) => {
    if (active.length === 0 && done.length === 0) return null;
    return (
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="text-base">{emoji}</span>
          <span className="text-xs font-extrabold uppercase tracking-widest text-farm-text-muted">{title}</span>
          <span className="text-xs font-bold text-zinc-400 bg-zinc-100 rounded-full px-1.5 py-0.5">
            {active.length + done.length}
          </span>
        </div>
        <div className="space-y-2.5">
          {active.map(renderCard)}
          {done.map(renderCard)}
        </div>
      </div>
    );
  };

  return (
    <div id="orders-queue-screen" className="flex flex-col w-full h-full pb-16">
      {/* Header */}
      <div className="px-4 pt-4 pb-3 border-b border-farm-border bg-white">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-xl font-serif font-bold text-farm-text">Orders</h1>
          <button
            type="button"
            onClick={fetchOrders}
            disabled={loading}
            className="p-1.5 text-farm-text-muted hover:text-olive-700 cursor-pointer transition-colors disabled:opacity-40"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-olive-600" : ""}`} />
          </button>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-farm-text-muted font-sans">
            {error
              ? <span className="text-red-600 font-semibold">● Offline</span>
              : <span><span className="text-emerald-600 font-semibold">● Live</span> · refreshing in {countdown}s</span>
            }
          </span>
          <span className="text-xs text-farm-text-muted font-mono">{orders.length} order{orders.length !== 1 ? "s" : ""}</span>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-4 mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between gap-3 text-sm font-sans text-amber-800">
          <span>{error}</span>
          <button type="button" onClick={fetchOrders} className="text-xs font-bold underline cursor-pointer shrink-0">Retry</button>
        </div>
      )}

      {/* Loading */}
      {loading && orders.length === 0 && (
        <div className="flex-1 flex items-center justify-center text-farm-text-muted font-sans text-sm">
          <Loader2 className="w-5 h-5 animate-spin mr-2 text-olive-600" />
          Loading orders...
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && orders.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center text-farm-text-muted font-sans text-sm gap-2">
          <CheckCircle className="w-8 h-8 text-zinc-300" />
          <span>No orders to display</span>
        </div>
      )}

      {/* Orders grouped by type */}
      <div className="flex-1 px-4 pt-4 overflow-y-auto">
        {renderSection("Delivery", "🚚", deliveryActive, deliveryDone)}
        {renderSection("Pickup", "📦", pickupActive, pickupDone)}
      </div>

      {/* Cancel modal */}
      {cancelModal && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "rgba(0,0,0,0.45)" }}
          onClick={() => setCancelModal(null)}
        >
          <div
            className="w-full max-w-md bg-white rounded-t-2xl p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-bold text-farm-text font-sans mb-1">Cancel Order</h3>
            <p className="text-sm text-farm-text-muted font-sans mb-4">
              Cancelling order for <strong>{cancelModal.name}</strong>. Provide a reason.
            </p>
            <textarea
              value={cancelReason}
              onChange={(e) => { setCancelReason(e.target.value); setCancelError(null); }}
              placeholder="e.g. Customer requested cancellation"
              rows={3}
              className="w-full border border-zinc-200 rounded-lg p-3 text-sm font-sans bg-zinc-50 focus:outline-none focus:border-olive-600 focus:bg-white text-farm-text mb-3"
            />
            {cancelError && (
              <div className="mb-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-2 font-sans">{cancelError}</div>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setCancelModal(null); setCancelReason(""); setCancelError(null); }}
                disabled={cancelLoading}
                className="flex-1 h-11 border border-farm-border font-semibold text-sm rounded-lg text-farm-text cursor-pointer hover:bg-zinc-50 disabled:opacity-60"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleConfirmCancel}
                disabled={cancelLoading}
                className="flex-1 h-11 bg-red-600 hover:bg-red-700 text-white font-bold text-sm rounded-lg cursor-pointer transition-colors disabled:opacity-60"
              >
                {cancelLoading ? "Cancelling..." : "Confirm Cancel"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
