import React, { useState } from "react";
import { Reservation } from "../types";
import { ArrowLeft, Calendar, MapPin, CircleCheck } from "lucide-react";
import { api } from "../api/client";

interface NewReservationProps {
  onBack: () => void;
  onSubmit: (newRes: Reservation) => void;
}

export default function NewReservation({ onBack, onSubmit }: NewReservationProps) {
  const [customerName, setCustomerName] = useState("");
  const [phone, setPhone] = useState("+961 ");
  const [reservationDate, setReservationDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [timeHour, setTimeHour] = useState(8);
  const [timeMinute, setTimeMinute] = useState(0);
  const [timePeriod, setTimePeriod] = useState<'AM' | 'PM'>('PM');
  const [timeError, setTimeError] = useState("");
  const [pax, setPax] = useState(2);
  const [selectedSeating, setSelectedSeating] = useState("indoor_non_smoking");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  function to24h(h: number, m: number, period: 'AM' | 'PM') {
    let hour = h;
    if (period === 'PM' && h !== 12) hour += 12;
    if (period === 'AM' && h === 12) hour = 0;
    return { hour, minute: m };
  }

  const seatingSections = [
    { value: "indoor_non_smoking", label: "Indoor Non-Smoking" },
    { value: "indoor_smoking",     label: "Indoor Smoking" },
    { value: "outdoor_terrace",    label: "Outdoor Terrace" },
    { value: "outdoor_non_terrace",label: "Outdoor" },
  ];

  const handlePaxIncrement = () => {
    setPax(prev => prev + 1);
  };

  const handlePaxDecrement = () => {
    if (pax > 1) {
      setPax(prev => prev - 1);
    }
  };

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerName.trim()) {
      alert("Please provide a guest name.");
      return;
    }

    // Reject past times when booking for today
    const today = new Date().toISOString().slice(0, 10);
    const { hour, minute } = to24h(timeHour, timeMinute, timePeriod);
    if (reservationDate === today) {
      const picked = new Date();
      picked.setHours(hour, minute, 0, 0);
      if (picked <= new Date()) {
        setTimeError("This time has already passed — please choose a future time.");
        return;
      }
    }
    setTimeError("");
    setSubmitError("");
    setSubmitting(true);

    const time24 = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

    try {
      const res = await api.createReservation({
        name: customerName.trim(),
        phone: phone.trim(),
        date: reservationDate,
        time: time24,
        party_size: pax,
        seating_preference: selectedSeating,
        notes: notes.trim(),
      });

      if (!res || !res.ok) {
        const errText = res ? await res.text() : "Network error";
        setSubmitError(`Failed to create reservation: ${errText}`);
        setSubmitting(false);
        return;
      }

      const data = await res.json();
      const seatingLabels: Record<string, string> = {
        indoor_non_smoking: "Indoor Non-Smoking",
        indoor_smoking: "Indoor Smoking",
        outdoor_terrace: "Outdoor Terrace",
        outdoor_non_terrace: "Outdoor",
      };
      const newRes: Reservation = {
        id: data.id,
        customerName: data.name,
        phone: data.phone,
        pax: data.party_size,
        time: data.time.substring(0, 5),
        date: data.date,
        section: data.seating_preference.substring(0, 2).toUpperCase(),
        sectionName: seatingLabels[data.seating_preference] ?? data.seating_preference,
        notes: `Ref: ${data.reference}`,
        status: "Pending",
      };
      onSubmit(newRes);
    } catch {
      setSubmitError("Network error — could not reach the server.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div id="new-reservation-screen" className="flex flex-col w-full h-full pb-20 overflow-y-auto bg-farm-bg">
      {/* Top details bar */}
      <div className="flex items-center justify-between border-b border-farm-border bg-white px-4 py-3 sticky top-0 z-50">
        <button 
          type="button" 
          onClick={onBack}
          className="p-1 hover:bg-zinc-100 rounded-full text-farm-text-muted transition-colors cursor-pointer flex items-center justify-center"
        >
          <ArrowLeft className="w-5 h-5 text-farm-text" />
        </button>
        <div className="flex flex-col items-center">
          <span className="text-[10px] font-mono tracking-wider uppercase text-zinc-400">BOOKING TABLE</span>
          <span className="text-sm font-bold text-farm-text font-serif">New Reservation</span>
        </div>
        <div className="text-xs font-semibold text-olive-700">
          Lakkis Farm
        </div>
      </div>

      <form onSubmit={handleConfirm} className="p-4 space-y-4">
        {/* Hero image header banner with gorgeous generated landscape */}
        <div className="relative w-full h-44 rounded-2xl overflow-hidden bg-zinc-800 flex items-end">
          <img 
            src="/src/assets/images/lebanon_farm_sunset_1781562689048.jpg" 
            alt="Baalbek Green Vineyards in Lebanon" 
            className="absolute inset-0 w-full h-full object-cover opacity-85"
            referrerPolicy="no-referrer"
          />
          {/* Fading overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/25 to-transparent"></div>
          
          <div className="relative p-5 z-10 w-full">
            <h2 className="text-xl md:text-2xl font-serif font-bold text-white tracking-normal leading-tight max-w-[85%]">
              Reserve your table at the heart of nature.
            </h2>
          </div>
        </div>

        {/* Guest Details */}
        <div className="bg-white border border-farm-border rounded-xl p-5 shadow-xs">
          <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest block mb-4">
            GUEST DETAILS
          </span>
          <div className="space-y-4 font-sans text-sm">
            <div className="flex flex-col">
              <label className="text-farm-text-muted font-semibold mb-1">Customer Name</label>
              <input
                type="text"
                required
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                placeholder="e.g. Salim Lakkis"
                className="h-11 px-3 bg-zinc-50 border border-zinc-200 rounded-lg focus:outline-none focus:border-olive-600 focus:bg-white text-farm-text font-medium"
              />
            </div>
            
            <div className="flex flex-col">
              <label className="text-farm-text-muted font-semibold mb-1">Phone Number</label>
              <input
                type="tel"
                required
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+961 03 123 456"
                className="h-11 px-3 bg-zinc-50 border border-zinc-200 rounded-lg focus:outline-none focus:border-olive-600 focus:bg-white text-farm-text font-medium"
              />
            </div>
          </div>
        </div>

        {/* Schedule & Size */}
        <div className="bg-white border border-farm-border rounded-xl p-5 shadow-xs">
          <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest block mb-4">
            SCHEDULE & SIZE
          </span>
          <div className="space-y-4 font-sans text-sm">
            <div className="flex flex-col">
              <label className="text-farm-text-muted font-semibold mb-1">Reservation Date</label>
              <div className="relative flex items-center">
                <input
                  type="date"
                  value={reservationDate}
                  onChange={(e) => { setReservationDate(e.target.value); setTimeError(""); }}
                  className="w-full h-11 pl-3 pr-10 bg-zinc-50 border border-zinc-200 rounded-lg focus:outline-none focus:border-olive-600 focus:bg-white text-farm-text font-medium"
                />
                <Calendar className="w-4 h-4 text-zinc-400 absolute right-3 pointer-events-none" />
              </div>
            </div>

            <div className="flex flex-col">
              <label className="text-farm-text-muted font-semibold mb-1">Reservation Time</label>
              <div className="flex items-center gap-2">
                {/* Hour */}
                <div className="flex flex-col items-center">
                  <input
                    type="number"
                    min={1}
                    max={12}
                    value={timeHour}
                    onChange={(e) => {
                      const v = parseInt(e.target.value);
                      if (!isNaN(v)) setTimeHour(Math.min(12, Math.max(1, v)));
                    }}
                    className="w-16 h-11 text-center border border-zinc-200 rounded-lg bg-zinc-50 text-farm-text font-bold text-base focus:outline-none focus:border-olive-600 focus:bg-white"
                  />
                  <span className="text-[9px] text-zinc-400 mt-0.5 uppercase tracking-wider">Hour</span>
                </div>
                <span className="font-bold text-farm-text text-2xl pb-4">:</span>
                {/* Minute */}
                <div className="flex flex-col items-center">
                  <input
                    type="number"
                    min={0}
                    max={59}
                    value={timeMinute.toString().padStart(2, '0')}
                    onChange={(e) => {
                      const v = parseInt(e.target.value);
                      if (!isNaN(v)) setTimeMinute(Math.min(59, Math.max(0, v)));
                    }}
                    className="w-16 h-11 text-center border border-zinc-200 rounded-lg bg-zinc-50 text-farm-text font-bold text-base focus:outline-none focus:border-olive-600 focus:bg-white"
                  />
                  <span className="text-[9px] text-zinc-400 mt-0.5 uppercase tracking-wider">Min</span>
                </div>
                {/* AM / PM toggle */}
                <div className="flex flex-col items-center pb-4">
                  <div className="flex border border-zinc-200 rounded-lg overflow-hidden bg-zinc-50">
                    {(['AM', 'PM'] as const).map((p) => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => { setTimePeriod(p); setTimeError(""); }}
                        className={`w-12 h-11 font-bold text-sm transition-colors cursor-pointer ${
                          timePeriod === p
                            ? 'bg-olive-700 text-white'
                            : 'text-farm-text-muted hover:bg-zinc-100'
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {timeError && (
                <p className="text-xs text-red-600 mt-1 font-sans">{timeError}</p>
              )}
            </div>

            <div className="flex items-center justify-between pt-2">
              <span className="text-farm-text-muted font-semibold">Number of Guests (PAX)</span>
              <div className="flex items-center border border-zinc-200 rounded-lg overflow-hidden bg-zinc-50">
                <button
                  type="button"
                  onClick={handlePaxDecrement}
                  className="w-10 h-10 flex items-center justify-center hover:bg-zinc-200 text-farm-text font-bold transition-colors select-none cursor-pointer"
                >
                  —
                </button>
                <span className="w-11 text-center font-bold text-farm-text text-sm">
                  {pax}
                </span>
                <button
                  type="button"
                  onClick={handlePaxIncrement}
                  className="w-10 h-10 flex items-center justify-center hover:bg-zinc-200 text-farm-text font-bold transition-colors select-none cursor-pointer"
                >
                  +
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Section Selection */}
        <div className="bg-white border border-farm-border rounded-xl p-5 shadow-xs">
          <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest block mb-4">
            SECTION SELECTION
          </span>
          <div className="grid grid-cols-2 gap-2 font-sans text-xs">
            {seatingSections.map((sec) => (
              <button
                key={sec.value}
                type="button"
                onClick={() => setSelectedSeating(sec.value)}
                className={`py-3 rounded-lg font-bold border flex items-center justify-center transition-all cursor-pointer ${
                  selectedSeating === sec.value
                    ? "bg-[#bae6fd] border-sky-300 text-sky-950 font-extrabold shadow-sm"
                    : "bg-zinc-50 border-zinc-200 text-farm-text-muted hover:border-zinc-300"
                }`}
              >
                {sec.label}
              </button>
            ))}
          </div>
        </div>

        {/* Special Notes Card */}
        <div className="bg-white border border-farm-border rounded-xl p-5 shadow-xs">
          <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest block mb-4">
            SPECIAL NOTES
          </span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Any dietary restrictions or special occasions?"
            className="w-full h-24 p-3 bg-zinc-50 border border-zinc-200 rounded-lg focus:outline-none focus:border-olive-600 focus:bg-white text-sm text-farm-text font-sans resize-none"
          />
        </div>

        {/* Summary Card */}
        <div className="bg-white border border-farm-border rounded-xl p-5 shadow-xs font-sans text-sm space-y-3">
          <h3 className="text-xl font-serif font-bold text-farm-text mb-4">Summary</h3>
          
          <div className="flex justify-between py-1 border-b border-dashed border-zinc-100">
            <span className="text-farm-text-muted">Reservation Type</span>
            <span className="font-semibold text-farm-text">Standard</span>
          </div>
          <div className="flex justify-between py-1 border-b border-dashed border-zinc-100">
            <span className="text-farm-text-muted">Estimated Duration</span>
            <span className="font-semibold text-farm-text">120 min</span>
          </div>
          <div className="flex justify-between py-1 pt-2">
            <span className="text-farm-text-muted">Confirmation Status</span>
            <span className="font-bold text-sky-700 uppercase tracking-widest text-xs">Pending</span>
          </div>

          {submitError && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 font-sans">{submitError}</p>
          )}

          {/* Large Sky blue Confirm button */}
          <button
            type="submit"
            id="btn-confirm-reservation"
            disabled={submitting}
            className="w-full mt-4 h-12 bg-[#bae6fd] hover:bg-[#a0dbf8] disabled:opacity-75 text-sky-950 font-bold rounded-lg border border-sky-300 flex items-center justify-center gap-2 cursor-pointer transition-colors shadow-sm select-none"
          >
            <span>{submitting ? "Processing..." : "Confirm Reservation"}</span>
            <CircleCheck className="w-5 h-5 text-sky-900" />
          </button>
          
          <p className="text-[10px] text-center text-farm-text-muted mt-2">
            By confirming, you agree to our booking policy and farm rules.
          </p>
        </div>

        {/* Location footnote */}
        <div className="bg-white border border-farm-border rounded-xl p-4 flex items-center gap-3">
          <div className="p-2.5 bg-sky-50 rounded-lg text-sky-700">
            <MapPin className="w-5 h-5" />
          </div>
          <div className="flex flex-col">
            <span className="font-mono text-xs font-bold text-zinc-800">Lakkis Farm Main Hall</span>
            <span className="text-[11px] text-zinc-400 uppercase tracking-wider mt-0.5">Baalbek, Lebanon</span>
          </div>
        </div>
      </form>
    </div>
  );
}
