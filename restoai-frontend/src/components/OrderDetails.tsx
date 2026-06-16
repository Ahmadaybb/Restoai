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
} from "lucide-react";

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

  const [posLoading, setPosLoading] = useState(false);
  const [posError, setPosError] = useState<string | null>(null);

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

  const handleEnterPOS = async () => {
    if (!api.dispatcherName()) {
      setPosError("Dispatcher name missing. Please sign out and sign in again.");
      return;
    }
    setPosLoading(true);
    setPosError(null);
    try {
      const res = await api.enterInPos(orderId);
      if (!res) return;
      if (res.status === 409) { setPosError("This order can no longer be edited."); return; }
      if (res.status === 400) { setPosError("Dispatcher name required."); return; }
      if (!res.ok) { setPosError(`Error entering POS (${res.status})`); return; }
      onOrderMutated();
      await fetchOrder();
    } catch {
      setPosError("Network error.");
    } finally {
      setPosLoading(false);
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
    <div id="order-details-screen" className="flex flex-col w-full h-full pb-24 overflow-y-auto">
      {/* Top Nav */}
      <div className="flex items-center justify-between border-b border-farm-border bg-white px-4 py-3 sticky top-0 z-50">
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

      {/* Loading */}
      {loading && (
        <div className="flex-1 flex items-center justify-center text-farm-text-muted font-sans text-sm py-16">
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
                  <span className="text-xs font-extrabold text-[#0284c7] tracking-wider uppercase">
                    {order.state === "awaiting_dispatcher_review"
                      ? "Awaiting Review"
                      : order.state === "entered_in_pos"
                      ? "Entered in POS"
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
              <span className="text-xs font-semibold text-farm-text-muted uppercase tracking-wider block mb-1">
                {order.fulfillment === "delivery" ? "Delivery Address" : "Pickup Location"}
              </span>

              {order.address ? (
                <>
                  <p className="text-sm text-farm-text leading-relaxed font-sans font-normal mb-2">
                    {order.address.text_value ||
                      order.address.area_label ||
                      (order.address.lat != null ? `${order.address.lat}, ${order.address.lon}` : "Location provided")}
                  </p>
                  {!order.address.in_zone && (
                    <div className="mb-3 flex items-center gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 font-sans">
                      <AlertCircle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                      Address is outside the delivery zone.
                    </div>
                  )}
                </>
              ) : (
                <p className="text-sm text-farm-text-muted font-sans italic mb-4">No address provided.</p>
              )}

              {/* Static Beirut map decoration */}
              <div className="relative w-full h-[155px] bg-[#dfded8] border border-farm-border rounded-lg overflow-hidden flex items-center justify-center">
                <svg className="absolute inset-0 w-full h-full text-zinc-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 155" preserveAspectRatio="none">
                  <path d="M 0 0 L 120 0 Q 140 30 150 45 T 180 75 Q 195 90 190 110 T 160 155 L 0 155 Z" fill="#ebeced" />
                  <path d="M120 0 L150 155 M150 0 L180 155 M190 0 L210 155" stroke="#fcfcfc" strokeWidth="4" strokeLinecap="round" />
                  <path d="M0 45 L400 45 M0 75 L400 75 M0 110 L400 110" stroke="#fcfcfc" strokeWidth="4" strokeLinecap="round" />
                  <rect x="230" y="10" width="30" height="25" rx="3" fill="#eeeeeb" />
                  <rect x="280" y="10" width="45" height="25" rx="3" fill="#eeeeeb" />
                  <rect x="340" y="10" width="45" height="24" rx="3" fill="#eeeeeb" />
                  <rect x="210" y="52" width="40" height="48" rx="3" fill="#eeeeeb" />
                  <rect x="260" y="52" width="60" height="20" rx="3" fill="#eeeeeb" />
                  <rect x="330" y="52" width="55" height="20" rx="3" fill="#eeeeeb" />
                  <rect x="260" y="80" width="60" height="24" rx="3" fill="#eeeeeb" />
                  <rect x="330" y="80" width="55" height="24" rx="3" fill="#eeeeeb" />
                  <circle cx="195" cy="78" r="8" fill="#0284c7" fillOpacity="0.2" className="animate-pulse" />
                  <circle cx="195" cy="78" r="4" fill="#0284c7" />
                  <path d="M195 62 L198 67 L192 67 Z" fill="#0284c7" />
                  <rect x="194" y="67" width="2" height="11" fill="#0284c7" />
                  <text x="290" y="65" fontFamily="Inter" fontSize="7" fontWeight="bold" fill="#7d7e82" letterSpacing="0.1em">BEIRUT PORT</text>
                  <text x="135" y="135" fontFamily="Inter" fontSize="6" fill="#1e293b" opacity="0.6">MEDITERRANEAN SEA</text>
                </svg>
                <div className="absolute top-[68px] left-[184px] transform -translate-x-1/2 -translate-y-full flex flex-col items-center">
                  <div className="animate-bounce">
                    <span className="text-3xl filter drop-shadow">📍</span>
                  </div>
                </div>
              </div>
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

          {/* POS action error */}
          {posError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-sans">
              {posError}
            </div>
          )}
        </div>
      )}

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

      {/* Sticky Bottom Actions */}
      {!loading && order && (
        <div className="fixed bottom-0 left-0 right-0 max-w-md mx-auto h-18 bg-white border-t border-farm-border flex items-center justify-around px-4 gap-2 z-50">
          <button
            type="button"
            id="btn-cancel"
            onClick={() => { setShowCancelModal(true); setCancelReason(""); setCancelError(null); }}
            disabled={order.state !== "awaiting_dispatcher_review"}
            className="flex-1 max-w-[110px] h-11 border border-red-200 hover:bg-red-50 font-semibold text-xs rounded-lg flex items-center justify-center gap-1.5 text-red-600 cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <XCircle className="w-3.5 h-3.5" />
            Cancel
          </button>

          <button
            type="button"
            id="btn-pos-enter"
            onClick={handleEnterPOS}
            disabled={order.state !== "awaiting_dispatcher_review" || posLoading}
            style={{
              backgroundColor:
                order.state === "entered_in_pos" ? "#446137" : "#0284c7",
            }}
            className="flex-1 h-11 hover:opacity-90 font-bold text-xs text-white rounded-lg flex items-center justify-center gap-1.5 cursor-pointer shadow-xs transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {posLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Saving...
              </>
            ) : order.state === "entered_in_pos" ? (
              <>
                <CheckCircle className="w-4 h-4 text-white" /> Synced in POS
              </>
            ) : (
              <>
                <Check className="w-4 h-4 text-white" /> Enter in POS
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
