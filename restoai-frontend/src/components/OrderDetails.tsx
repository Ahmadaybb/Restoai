import React, { useState, useEffect } from "react";
import { Order } from "../types";
import { api } from "../api/client";
import {
  ArrowLeft,
  User,
  Phone,
  MapPin,
  Check,
  XCircle,
  CheckCircle,
  AlertCircle,
  Loader2,
  ExternalLink,
} from "lucide-react";
import { OrderAddress } from "../types";

function mapsUrl(address: OrderAddress): string | null {
  if (address.lat != null && address.lon != null) {
    return `https://www.google.com/maps?q=${address.lat},${address.lon}`;
  }
  if (address.text_value && /^https?:\/\//i.test(address.text_value)) {
    return address.text_value;
  }
  return null;
}

function AddressBlock({ address }: { address: OrderAddress }) {
  const url = mapsUrl(address);
  const label =
    address.text_value ||
    address.area_label ||
    (address.lat != null ? `${address.lat}, ${address.lon}` : "Location shared");

  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-start gap-2 mb-2 text-sm font-semibold text-[#0284c7] underline underline-offset-2 hover:text-[#0369a1] transition-colors font-sans"
      >
        <MapPin className="w-4 h-4 mt-0.5 shrink-0" />
        <span className="break-all">{label}</span>
        <ExternalLink className="w-3.5 h-3.5 mt-0.5 shrink-0 opacity-60" />
      </a>
    );
  }

  return (
    <p className="text-sm text-farm-text leading-relaxed font-sans font-normal mb-2 flex items-start gap-2">
      <MapPin className="w-4 h-4 mt-0.5 shrink-0 text-farm-text-muted" />
      {label}
    </p>
  );
}

interface OrderDetailsProps {
  orderId: string;
  onBack: () => void;
  onOrderMutated: () => void;
}

function langLabel(lang: string): string {
  if (lang === "en") return "🇬🇧 EN";
  if (lang === "arabizi") return "🇱🇧 Arabizi";
  return "🇱🇧 AR";
}

export default function OrderDetails({ orderId, onBack, onOrderMutated }: OrderDetailsProps) {
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelLoading, setCancelLoading] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const fetchOrder = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getOrder(orderId);
      if (!res) return;
      if (res.status === 404) { setError("Order not found."); return; }
      if (!res.ok) { setError(`Failed to load order (${res.status})`); return; }
      const data: Order = await res.json();
      setOrder(data);
    } catch {
      setError("Network error — could not load order.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchOrder(); }, [orderId]);

  const handleAdvanceState = async () => {
    if (!order) return;
    if (!api.dispatcherName()) {
      setActionError("Dispatcher name missing. Please sign out and sign in again.");
      return;
    }
    setActionLoading(true);
    setActionError(null);
    try {
      // Pickup orders skip "On the Way" — go directly from Being Made → Delivered
      const res = order.state === "awaiting_dispatcher_review"
        ? await api.enterInPos(orderId)
        : order.state === "entered_in_pos" && order.fulfillment === "delivery"
        ? await api.markOutForDelivery(orderId)
        : await api.markDelivered(orderId);
      if (!res) return;
      if (res.status === 409) { setActionError("This order can no longer be edited."); return; }
      if (res.status === 400) { setActionError("Dispatcher name required."); return; }
      if (!res.ok) { setActionError(`Error updating order (${res.status})`); return; }
      onOrderMutated();
      await fetchOrder();
    } catch {
      setActionError("Network error.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirmCancel = async () => {
    if (!cancelReason.trim()) {
      setCancelError("A reason is required to cancel.");
      return;
    }
    if (!api.dispatcherName()) {
      setCancelError("Dispatcher name missing. Please sign out and sign in again.");
      return;
    }
    setCancelLoading(true);
    setCancelError(null);
    try {
      const res = await api.cancelOrder(orderId, cancelReason.trim());
      if (!res) return;
      if (res.status === 409) { setCancelError("This order can no longer be edited."); return; }
      if (res.status === 400) { setCancelError("Dispatcher name required."); return; }
      if (!res.ok) { setCancelError(`Error cancelling order (${res.status})`); return; }
      onOrderMutated();
      onBack();
    } catch {
      setCancelError("Network error.");
    } finally {
      setCancelLoading(false);
    }
  };

  const displayId = orderId.slice(0, 8);

  return (
    <div id="order-details-screen" className="flex flex-col w-full h-full">
      {/* Top Nav */}
      <div className="flex items-center justify-between border-b border-farm-border bg-white px-4 py-3 shrink-0">
        <button
          type="button"
          onClick={onBack}
          className="p-1 hover:bg-zinc-100 rounded-full text-farm-text-muted transition-colors cursor-pointer flex items-center justify-center"
        >
          <ArrowLeft className="w-5 h-5 text-farm-text" />
        </button>
        <div className="flex flex-col items-center">
          <span className="text-[10px] font-mono tracking-wider uppercase text-zinc-400">ORDER DISPATCHER</span>
          <span className="text-sm font-bold text-farm-text font-mono">#{displayId}</span>
        </div>
        <div className="w-5" />
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto">

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center text-farm-text-muted font-sans text-sm py-16">
          <Loader2 className="w-5 h-5 animate-spin mr-2 text-olive-600" />
          Loading order...
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="p-6">
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800 font-sans flex items-center justify-between">
            <span>{error}</span>
            <button
              type="button"
              onClick={fetchOrder}
              className="text-xs font-bold underline cursor-pointer shrink-0 ml-3"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Order content */}
      {!loading && order && (
        <div className="p-4 space-y-4">
          {/* Customer Details */}
          <div className="bg-white border border-farm-border rounded-xl p-5 shadow-xs">
            <div className="flex justify-between items-start mb-4">
              <h2 className="text-base font-semibold text-olive-700 font-sans">Customer Details</h2>
              {order.flags.includes("out_of_zone_warning") && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-50 text-amber-800 border border-amber-200 text-xs font-semibold rounded">
                  <AlertCircle className="w-3 h-3" /> Out of Zone
                </span>
              )}
            </div>

            <div className="space-y-3 font-sans pb-4 border-b border-zinc-100">
              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-zinc-50 rounded-lg text-farm-text-muted">
                  <User className="w-4 h-4" />
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest leading-none mb-1">Name</span>
                  <span className="text-sm font-semibold text-farm-text">{order.customer_name}</span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-zinc-50 rounded-lg text-farm-text-muted">
                  <Phone className="w-4 h-4" />
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest leading-none mb-1">Phone</span>
                  <span className="text-sm font-semibold text-farm-text">{order.customer_phone}</span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-zinc-50 rounded-lg text-farm-text-muted">
                  <MapPin className="w-4 h-4" />
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest leading-none mb-1">Status</span>
                  <span className="text-xs font-extrabold tracking-wider uppercase"
                    style={{ color: order.state === "awaiting_dispatcher_review" ? "#0284c7" : order.state === "entered_in_pos" ? "#d97706" : order.state === "out_for_delivery" ? "#059669" : order.state === "delivered" ? "#7c3aed" : "#71717a" }}>
                    {order.state === "awaiting_dispatcher_review" ? "Pending"
                      : order.state === "entered_in_pos" ? "Being Made"
                      : order.state === "out_for_delivery" ? "On the Way"
                      : order.state === "delivered" ? "Delivered"
                      : "Cancelled"}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-zinc-50 rounded-lg text-farm-text-muted">
                  <span className="text-base leading-none">{order.fulfillment === "delivery" ? "🚚" : "📦"}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest leading-none mb-1">Type</span>
                  <span className="text-sm font-semibold text-farm-text capitalize">
                    {order.fulfillment} · {langLabel(order.language)}
                  </span>
                </div>
              </div>
            </div>

            {/* Delivery Address */}
            <div className="pt-4">
              <span className="text-xs font-semibold text-farm-text-muted uppercase tracking-wider block mb-2">
                {order.fulfillment === "delivery" ? "Delivery Address" : "Pickup Location"}
              </span>

              {order.address ? (
                <>
                  <AddressBlock address={order.address} />
                  {!order.address.in_zone && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 font-sans">
                      <AlertCircle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                      Address is outside the delivery zone.
                    </div>
                  )}
                </>
              ) : (
                <p className="text-sm text-farm-text-muted font-sans italic mb-2">No address provided.</p>
              )}
            </div>
          </div>

          {/* Order Items */}
          {order.items && order.items.length > 0 && (
            <div className="bg-white border border-farm-border rounded-xl overflow-hidden shadow-xs">
              <div className="flex justify-between items-center px-5 py-4 bg-zinc-50 border-b border-zinc-100">
                <h3 className="text-sm font-semibold text-olive-700 font-sans">Order Items</h3>
                <span className="text-xs font-sans text-farm-text-muted font-medium">{order.items.length} Items</span>
              </div>

              <div className="divide-y divide-zinc-100 px-5">
                {order.items.map((item, idx) => (
                  <div key={`${item.menu_item_id}-${idx}`} className="py-4 font-sans">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="flex items-baseline gap-1.5">
                          <span className="text-sm font-bold text-farm-text font-serif">{item.quantity}x</span>
                          <span className="text-sm font-medium text-farm-text">{item.name}</span>
                        </div>
                        {item.customizations.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {item.customizations.map((c, ci) => (
                              <span
                                key={ci}
                                className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded ${
                                  c.kind === "remove"
                                    ? "bg-red-50 text-red-600"
                                    : "bg-zinc-100 text-zinc-600"
                                }`}
                              >
                                {c.kind === "add" ? "+" : c.kind === "remove" ? "−" : ""} {c.text}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <span className="text-sm font-semibold text-farm-text">${item.price_usd.toFixed(2)}</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="bg-zinc-50 p-5 border-t border-zinc-100 text-sm font-sans">
                <div className="flex justify-between font-bold text-farm-text text-base">
                  <span className="font-serif font-extrabold text-farm-text-muted">Estimated Total</span>
                  <span className="text-olive-700">${order.estimated_total_usd.toFixed(2)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Action error */}
          {actionError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-sans">
              {actionError}
            </div>
          )}
        </div>
      )}

      </div>{/* end scrollable body */}

      {/* Cancel Confirmation Modal */}
      {showCancelModal && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "rgba(0,0,0,0.4)" }}
        >
          <div className="w-full max-w-md bg-white rounded-t-2xl p-6 shadow-2xl">
            <h3 className="text-base font-bold text-farm-text font-sans mb-1">Cancel Order</h3>
            <p className="text-sm text-farm-text-muted font-sans mb-4">
              Provide a reason for cancelling this order.
            </p>
            <textarea
              value={cancelReason}
              onChange={(e) => { setCancelReason(e.target.value); setCancelError(null); }}
              placeholder="e.g. Customer requested cancellation"
              rows={3}
              className="w-full border border-zinc-200 rounded-lg p-3 text-sm font-sans bg-zinc-50 focus:outline-none focus:border-olive-600 focus:bg-white text-farm-text mb-3"
            />
            {cancelError && (
              <div className="mb-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-2 font-sans">
                {cancelError}
              </div>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setShowCancelModal(false); setCancelReason(""); setCancelError(null); }}
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

      {/* Bottom Actions */}
      {!loading && order && (
        <div className="bg-white border-t border-farm-border px-4 py-3 flex items-center gap-2 shrink-0">
          {/* Cancel X — visible and active for ALL active states */}
          {(order.state === "awaiting_dispatcher_review" ||
            order.state === "entered_in_pos" ||
            order.state === "out_for_delivery") && (
            <button
              type="button"
              id="btn-cancel"
              onClick={() => { setShowCancelModal(true); setCancelReason(""); setCancelError(null); }}
              className="w-10 h-10 border border-red-200 hover:bg-red-50 rounded-lg flex items-center justify-center text-red-500 cursor-pointer transition-colors shrink-0"
              title="Cancel order"
            >
              <XCircle className="w-4 h-4" />
            </button>
          )}

          {/* Pending → Start Making */}
          {order.state === "awaiting_dispatcher_review" && (
            <button
              type="button"
              id="btn-start-making"
              onClick={handleAdvanceState}
              disabled={actionLoading}
              className="flex-1 h-10 bg-amber-500 hover:bg-amber-600 font-bold text-xs text-white rounded-lg flex items-center justify-center gap-1.5 cursor-pointer shadow-xs transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              {actionLoading ? "Saving..." : "Start Making"}
            </button>
          )}

          {/* Being Made + DELIVERY → On the Way */}
          {order.state === "entered_in_pos" && order.fulfillment === "delivery" && (
            <button
              type="button"
              id="btn-out-for-delivery"
              onClick={handleAdvanceState}
              disabled={actionLoading}
              className="flex-1 h-10 bg-sky-600 hover:bg-sky-700 font-bold text-xs text-white rounded-lg flex items-center justify-center gap-1.5 cursor-pointer shadow-xs transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
              {actionLoading ? "Saving..." : "On the Way"}
            </button>
          )}

          {/* Being Made + PICKUP → Finish (skip On the Way) */}
          {order.state === "entered_in_pos" && order.fulfillment === "pickup" && (
            <button
              type="button"
              id="btn-finish-pickup"
              onClick={handleAdvanceState}
              disabled={actionLoading}
              className="flex-1 h-10 bg-emerald-600 hover:bg-emerald-700 font-bold text-xs text-white rounded-lg flex items-center justify-center gap-1.5 cursor-pointer shadow-xs transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
              {actionLoading ? "Saving..." : "Finish"}
            </button>
          )}

          {/* On the Way → Finish (delivery only) */}
          {order.state === "out_for_delivery" && (
            <button
              type="button"
              id="btn-finish"
              onClick={handleAdvanceState}
              disabled={actionLoading}
              className="flex-1 h-10 bg-emerald-600 hover:bg-emerald-700 font-bold text-xs text-white rounded-lg flex items-center justify-center gap-1.5 cursor-pointer shadow-xs transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
              {actionLoading ? "Saving..." : "Finish"}
            </button>
          )}

          {/* Final states */}
          {order.state === "delivered" && (
            <div className="flex-1 h-10 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center justify-center gap-1.5 text-emerald-700 font-bold text-xs">
              <CheckCircle className="w-4 h-4" /> Done
            </div>
          )}

          {order.state === "cancelled" && (
            <div className="flex-1 h-10 bg-zinc-100 border border-zinc-200 rounded-lg flex items-center justify-center gap-1.5 text-zinc-500 font-bold text-xs">
              <XCircle className="w-4 h-4" /> Cancelled
            </div>
          )}
        </div>
      )}
    </div>
  );
}
