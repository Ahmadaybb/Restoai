import React, { useState } from "react";
import { Reservation } from "../types";
import { Phone, Calendar, Users, Check, X, ClipboardList, PlusCircle, CheckSquare, Plus, Ban, Loader2 } from "lucide-react";

interface ReservationsListProps {
  reservations: Reservation[];
  loading?: boolean;
  onAddReservation: (newRes: Reservation) => void;
  onUpdateReservation: (updatedRes: Reservation) => void;
  onTriggerNewReservationForm: () => void;
}

export default function ReservationsList({
  reservations,
  loading,
  onUpdateReservation,
  onTriggerNewReservationForm
}: ReservationsListProps) {
  const [selectedDayIndex, setSelectedDayIndex] = useState(0); // Default to today

  const dateChips = Array.from({ length: 5 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return {
      label: d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase(),
      num: d.getDate(),
      dateStr: `${y}-${m}-${day}`,
    };
  });

  const currentSelectedDate = dateChips[selectedDayIndex].dateStr;

  // Filter reservations based on selected day chip
  const filteredReservations = reservations.filter(
    (res) => res.date === currentSelectedDate
  );

  const handleArrive = (res: Reservation) => {
    onUpdateReservation({
      ...res,
      status: "Arrived"
    });
  };

  const handleNoShow = (res: Reservation) => {
    onUpdateReservation({
      ...res,
      status: "No Show"
    });
  };

  const todayStr = dateChips[0].dateStr;
  const todayReservations = reservations.filter(r => r.date === todayStr);
  const remainingCount = todayReservations.filter(r => r.status === "Pending").length;
  const paxExpected = todayReservations
    .filter(r => r.status === "Pending" || r.status === "Arrived")
    .reduce((acc, curr) => acc + curr.pax, 0);

  return (
    <div id="reservations-screen" className="flex flex-col w-full h-full pb-20">
      {/* Title block */}
      <div className="px-6 pt-5 pb-2">
        <div className="flex justify-between items-baseline mb-1">
          <h1 className="text-3xl font-serif font-semibold tracking-tight text-farm-text">
            Upcoming Reservations
          </h1>
        </div>

        {/* Dynamic Telemetry info */}
        <div className="flex justify-between items-center mb-3.5">
          <div className="flex items-center gap-3 text-xs font-sans text-farm-text-muted font-normal mt-0.5">
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5 text-olive-600" />
              <strong>{remainingCount} Remaining</strong>
            </span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <Users className="w-3.5 h-3.5 text-olive-600" />
              <strong>{paxExpected} Pax Expected</strong>
            </span>
          </div>

          <button
            type="button"
            id="btn-trigger-new-res"
            onClick={onTriggerNewReservationForm}
            className="flex items-center gap-1.5 bg-[#bae6fd] hover:bg-[#a0dbf8] transition-colors text-sky-950 font-bold text-xs px-3 py-1.5 rounded-lg border border-sky-300 cursor-pointer shadow-xs"
          >
            <Plus className="w-3.5 h-3.5" />
            New
          </button>
        </div>
      </div>

      {/* Date chips wrapper */}
      <div className="px-6 pb-3">
        <div className="flex gap-2 overflow-x-auto py-2 no-scrollbar">
          {dateChips.map((chip, index) => {
            const isSelected = selectedDayIndex === index;
            return (
              <button
                key={index}
                type="button"
                onClick={() => setSelectedDayIndex(index)}
                className={`flex-1 min-w-[62px] py-2.5 rounded-xl border flex flex-col items-center justify-center font-sans transition-all cursor-pointer ${
                  isSelected 
                    ? "bg-[#bae6fd] border-sky-300 text-sky-950 shadow-xs" 
                    : "bg-white border-farm-border text-farm-text-muted hover:border-zinc-300"
                }`}
              >
                <span className="text-[10px] font-bold tracking-wider uppercase mb-0.5">{chip.label}</span>
                <span className="text-lg font-extrabold leading-none">{chip.num}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Bookings Card list */}
      <div className="flex-1 px-4 overflow-y-auto space-y-4">
        {loading && reservations.length === 0 ? (
          <div className="py-12 flex items-center justify-center text-farm-text-muted font-sans text-sm">
            <Loader2 className="w-5 h-5 animate-spin mr-2 text-olive-600" />
            Loading reservations...
          </div>
        ) : filteredReservations.length === 0 ? (
          <div className="py-12 text-center text-sm font-sans text-farm-text-muted bg-white border border-farm-border rounded-xl">
            <ClipboardList className="w-8 h-8 mx-auto mb-2 text-zinc-300" />
            No reservations scheduled for this day.
          </div>
        ) : (
          filteredReservations.map((res) => (
            <div
              key={res.id}
              id={`res-card-${res.id}`}
              className="bg-white border border-farm-border rounded-2xl p-5 shadow-xs flex flex-col relative overflow-hidden"
            >
              {/* Header tags inside card */}
              <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-extrabold px-2 py-0.5 bg-zinc-800 text-white tracking-widest uppercase rounded">
                    RESERVED
                  </span>
                  <span className="text-[9px] font-bold px-2 py-0.5 bg-sky-50 text-sky-950 tracking-wider uppercase rounded border border-sky-200">
                    SECTION {res.section}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-xl font-bold text-farm-text font-sans block leading-none">
                    {res.time}
                  </span>
                  <span className="text-[10px] uppercase font-bold text-farm-text-muted mt-1 inline-flex items-center gap-1 font-sans">
                    👥 {res.pax} PAX
                  </span>
                </div>
              </div>

              {/* Customer Title */}
              <h3 className="text-lg font-serif font-bold text-zinc-900 pr-12 leading-snug">
                {res.customerName}
              </h3>

              {/* Phone number link with underline */}
              <div className="flex items-center gap-1.5 text-sm font-semibold text-olive-700 underline mt-1.5 mb-3 font-sans">
                <Phone className="w-3.5 h-3.5" />
                <span>{res.phone}</span>
              </div>

              {/* Description Notes list */}
              <div className="border-t border-zinc-100 pt-3 flex items-start gap-2.5 text-sm font-sans text-farm-text-muted">
                <ClipboardList className="w-4 h-4 text-zinc-400 shrink-0 mt-0.5" />
                <p className="leading-relaxed font-normal">{res.notes}</p>
              </div>

              {/* Actions Box */}
              <div className="mt-4 pt-3.5 border-t border-zinc-100 flex items-center justify-between gap-3 font-sans">
                {res.status === "Pending" ? (
                  <>
                    <button
                      type="button"
                      onClick={() => handleArrive(res)}
                      className="flex-1 h-10 border border-[#0d9488]/30 hover:bg-[#0d9488]/5 bg-[#0d9488] text-white font-bold text-xs rounded-lg flex items-center justify-center gap-1.5 cursor-pointer shadow-xs transition-colors"
                    >
                      <span>Arrive</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleNoShow(res)}
                      className="flex-1 h-10 border border-farm-border hover:bg-zinc-50 font-semibold text-zinc-700 text-xs rounded-lg flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
                    >
                      <Ban className="w-3.5 h-3.5 text-zinc-400" />
                      No Show
                    </button>
                  </>
                ) : res.status === "Arrived" ? (
                  <div className="flex-1 py-1.5 bg-emerald-50 text-emerald-800 font-bold text-xs text-center border border-emerald-200 rounded-lg flex items-center justify-center gap-1">
                    <CheckSquare className="w-4 h-4 text-emerald-600" />
                    Guest has Arrived
                  </div>
                ) : res.status === "Cancelled" ? (
                  <div className="flex-1 py-1.5 bg-red-50 text-red-600 font-bold text-xs text-center border border-red-200 rounded-lg flex items-center justify-center gap-1">
                    <X className="w-4 h-4 text-red-400" />
                    Cancelled by Customer
                  </div>
                ) : (
                  <div className="flex-1 py-1.5 bg-zinc-50 text-zinc-500 font-bold text-xs text-center border border-zinc-200 rounded-lg flex items-center justify-center gap-1">
                    <X className="w-4 h-4 text-zinc-400" />
                    No Show Logged
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
