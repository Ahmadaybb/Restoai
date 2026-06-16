import { Reservation } from "./types";

// Orders and escalations are fetched from the backend API.
// Only reservation mock data lives here while the reservations endpoint is in development.

export const INITIAL_RESERVATIONS: Reservation[] = [
  {
    id: "res-1",
    customerName: "Miller Corporate Group",
    phone: "+961 01 234 567",
    pax: 6,
    time: "20:30",
    date: "2026-06-18",
    section: "R1",
    sectionName: "Family",
    notes: "Special dietary requirements & high chair request for toddler.",
    status: "Pending"
  },
  {
    id: "res-2",
    customerName: "Sarah Jenkins",
    phone: "+961 70 889 900",
    pax: 2,
    time: "21:00",
    date: "2026-06-19",
    section: "T3",
    sectionName: "Terrace",
    notes: "Anniversary dinner, table near window if available please.",
    status: "Pending"
  },
  {
    id: "res-3",
    customerName: "David Chen",
    phone: "+961 71 556 677",
    pax: 4,
    time: "21:15",
    date: "2026-06-19",
    section: "R2",
    sectionName: "Lounge",
    notes: "No notes provided.",
    status: "Pending"
  },
  {
    id: "res-4",
    customerName: "Aline Tannous",
    phone: "+961 03 112 233",
    pax: 8,
    time: "19:00",
    date: "2026-06-18",
    section: "T4",
    sectionName: "Garden",
    notes: "Birthday party celebration.",
    status: "Arrived"
  }
];
