import React, { useState, useEffect, useRef, useCallback } from "react";
import { EscalationDetail, Turn } from "../types";
import { api } from "../api/client";
import {
  Send,
  Cpu,
  UserCheck,
  Bot,
  Loader2,
  ArrowLeft,
  Smartphone,
} from "lucide-react";

interface ChatEscalationProps {
  conversationId: string;
  onBack: () => void;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function ChatEscalation({ conversationId, onBack }: ChatEscalationProps) {
  const [detail, setDetail] = useState<EscalationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [messageText, setMessageText] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDetail = useCallback(async () => {
    try {
      const res = await api.getEscalation(conversationId);
      if (!res) return;
      if (res.status === 404) { setDetailError("Escalation not found."); return; }
      if (!res.ok) { setDetailError(`Error loading detail (${res.status})`); return; }
      const data: EscalationDetail = await res.json();
      setDetail(data);
      setDetailError(null);
    } catch {
      setDetailError("Network error.");
    }
  }, [conversationId]);

  useEffect(() => {
    setDetailLoading(true);
    fetchDetail().finally(() => setDetailLoading(false));
  }, [fetchDetail]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [detail?.transcript]);

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(fetchDetail, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchDetail]);

  const handleTakeOver = async () => {
    if (!api.dispatcherName()) {
      setSendError("Dispatcher name missing — please sign out and sign in again.");
      return;
    }
    setActionLoading(true);
    setSendError(null);
    try {
      const res = await api.takeOver(conversationId);
      if (!res) return;
      if (!res.ok) { setSendError(`Error taking over (${res.status})`); return; }
      await fetchDetail();
    } catch {
      setSendError("Network error.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!messageText.trim()) return;
    if (!api.dispatcherName()) {
      setSendError("Dispatcher name missing — please sign out and sign in again.");
      return;
    }
    const text = messageText.trim();
    setMessageText("");
    setSendError(null);

    if (detail) {
      const optimistic: Turn = {
        sender: "dispatcher",
        text,
        language: "en",
        created_at: new Date().toISOString(),
      };
      setDetail({ ...detail, transcript: [...detail.transcript, optimistic] });
    }

    try {
      const res = await api.sendMessage(conversationId, text);
      if (!res) return;
      if (!res.ok) setSendError(`Error sending message (${res.status})`);
      await fetchDetail();
    } catch {
      setSendError("Network error.");
    }
  };

  const handleCloseHandoff = async () => {
    if (!api.dispatcherName()) {
      setSendError("Dispatcher name missing — please sign out and sign in again.");
      return;
    }
    setActionLoading(true);
    setSendError(null);
    try {
      const res = await api.closeHandoff(conversationId);
      if (!res) return;
      if (!res.ok) { setSendError(`Error closing handoff (${res.status})`); return; }
      onBack();
    } catch {
      setSendError("Network error.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div id="escalation-chat-screen" className="flex flex-col w-full h-full pb-16">
      {/* Header */}
      <div className="px-4 pt-4 pb-3 flex items-center gap-3 border-b border-farm-border bg-white sticky top-0 z-10">
        <button
          type="button"
          onClick={onBack}
          className="p-1 hover:bg-zinc-100 rounded-full text-farm-text-muted transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-5 h-5 text-farm-text" />
        </button>
        <div>
          <div className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider">Escalation</div>
          <div className="text-sm font-bold text-farm-text">{detail?.customer_name ?? "..."}</div>
          {detail?.customer_phone && (
            <div className="flex items-center gap-1 text-xs text-farm-text-muted font-sans mt-0.5">
              <Smartphone className="w-3 h-3" />
              {detail.customer_phone}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 px-4 py-4 overflow-y-auto space-y-4">
        {detailLoading && (
          <div className="flex items-center justify-center py-12 text-farm-text-muted font-sans text-sm">
            <Loader2 className="w-5 h-5 animate-spin mr-2 text-olive-600" />
            Loading...
          </div>
        )}

        {detailError && (
          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800 font-sans">
            {detailError}
          </div>
        )}

        {detail && (
          <>
            {/* Customer info card */}
            <div className="bg-white border border-farm-border rounded-xl p-4 shadow-xs font-sans text-sm">
              <div className="flex justify-between py-1">
                <span className="text-farm-text-muted">Contact</span>
                <span className="font-semibold text-farm-text">{detail.customer_phone}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-farm-text-muted">Language</span>
                <span className="font-semibold text-farm-text">{detail.language}</span>
              </div>
              {detail.active_draft_summary && (
                <div className="mt-3 bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-800">
                  <strong>Draft:</strong> {detail.active_draft_summary}
                </div>
              )}
            </div>

            {/* Chat panel */}
            <div
              className="bg-white border border-farm-border rounded-xl overflow-hidden flex flex-col shadow-sm"
              style={{ height: "380px" }}
            >
              {/* Panel header */}
              <div className="px-4 py-3 bg-zinc-50 border-b border-zinc-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-600"></span>
                  </span>
                  <span className="text-sm font-bold text-farm-text leading-none">Live Chat</span>
                </div>

                <div className="flex gap-2">
                  {!detail.assigned_dispatcher_id ? (
                    <button
                      type="button"
                      id="btn-take-over"
                      onClick={handleTakeOver}
                      disabled={actionLoading}
                      className="bg-farm-text hover:bg-zinc-800 text-white font-bold text-xs uppercase tracking-wider px-3 py-1.5 rounded flex items-center gap-1.5 select-none transition-all cursor-pointer shadow-xs disabled:opacity-60"
                    >
                      ✋ Take Over
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleCloseHandoff}
                      disabled={actionLoading}
                      className="bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-emerald-800 font-bold text-[10px] px-2.5 py-1 rounded cursor-pointer disabled:opacity-60"
                    >
                      Close Handoff
                    </button>
                  )}
                </div>
              </div>

              {/* Messages */}
              <div ref={scrollRef} className="flex-1 p-4 bg-zinc-50/50 overflow-y-auto space-y-3 font-sans">
                {detail.transcript.map((turn, idx) => {
                  const isCustomer = turn.sender === "customer";
                  const isBot = turn.sender === "bot";

                  let bubbleStyle =
                    "bg-white text-farm-text border border-zinc-100 rounded-2xl rounded-tr-xs ml-auto";
                  if (isCustomer)
                    bubbleStyle = "bg-zinc-200/70 text-zinc-800 rounded-2xl rounded-tl-xs mr-auto";
                  else if (isBot)
                    bubbleStyle = "bg-[#bae6fd] text-sky-950 rounded-2xl rounded-tl-xs mr-auto";

                  const senderLabel = isCustomer
                    ? detail.customer_name
                    : isBot
                    ? "Bot"
                    : "Dispatcher";

                  return (
                    <div key={idx} className="max-w-[85%] flex flex-col">
                      <span
                        className={`text-[10px] font-mono text-zinc-400 mb-1 flex items-center gap-1 ${
                          isCustomer ? "mr-auto self-start" : "ml-auto self-end"
                        }`}
                      >
                        {isBot && <Cpu className="w-2.5 h-2.5 text-sky-700" />}
                        {!isCustomer && !isBot && <UserCheck className="w-2.5 h-2.5 text-olive-600" />}
                        {senderLabel} · {formatTime(turn.created_at)}
                      </span>
                      <div className={`p-3 text-sm leading-relaxed ${bubbleStyle}`}>
                        <p className="font-normal">{turn.text}</p>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Input area */}
              {detail.assigned_dispatcher_id ? (
                <form
                  onSubmit={handleSendMessage}
                  className="p-3 bg-white border-t border-zinc-100 flex items-center gap-2"
                >
                  <input
                    type="text"
                    value={messageText}
                    onChange={(e) => setMessageText(e.target.value)}
                    placeholder="Type your message..."
                    className="flex-1 h-10 px-3 bg-zinc-50 border border-zinc-200 text-sm rounded-lg focus:outline-none focus:border-olive-600 focus:bg-white text-farm-text"
                  />
                  <button
                    type="submit"
                    className="w-10 h-10 p-0 bg-olive-700 hover:bg-olive-800 text-white rounded-lg flex items-center justify-center cursor-pointer transition-colors"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </form>
              ) : (
                <div className="p-4 bg-[#f4f6f1] border-t border-zinc-100 text-center flex items-center justify-center gap-2">
                  <Bot className="w-4 h-4 text-olive-600" />
                  <p className="text-xs font-semibold text-olive-800">
                    Bot is active. Click "Take Over" to chat manually.
                  </p>
                </div>
              )}
            </div>

            {sendError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-sans">
                {sendError}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
