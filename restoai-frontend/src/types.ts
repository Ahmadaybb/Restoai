// ── ORDER TYPES (backend-aligned) ──────────────────────────────────────────

export type OrderState =
  | 'awaiting_dispatcher_review'
  | 'entered_in_pos'
  | 'cancelled'

export type Language = 'en' | 'ar_lb' | 'arabizi'

export interface OrderItem {
  menu_item_id: string
  name: string
  quantity: number
  price_usd: number
  customizations: Array<{
    kind: 'add' | 'remove' | 'cook_pref' | 'extra_side' | 'other'
    text: string
  }>
}

export interface OrderAddress {
  kind: 'text' | 'location'
  text_value?: string
  lat?: number
  lon?: number
  area_label?: string
  in_zone: boolean
}

export interface DispatcherAction {
  action: string
  dispatcher_name: string
  dispatcher_id: string
  created_at: string
  details?: Record<string, unknown>
}

export interface Order {
  id: string               // full UUID
  customer_name: string
  customer_phone: string   // E.164
  fulfillment: 'delivery' | 'pickup'
  language: Language
  estimated_total_usd: number
  flags: string[]          // may contain 'out_of_zone_warning'
  state: OrderState
  created_at: string       // ISO datetime
  // detail-only fields (absent in list responses)
  items?: OrderItem[]
  address?: OrderAddress
  transcript_url?: string
  entered_in_pos_at?: string
  dispatcher_actions?: DispatcherAction[]
}

// ── RESERVATION TYPES ──────────────────────────────────────────────────────

// Shape returned by GET /api/dispatcher/reservations
export interface ReservationFromAPI {
  id: string
  reference: string
  date: string           // "2026-06-19"
  time: string           // "20:30:00"
  party_size: number
  name: string
  phone: string
  seating_preference: 'indoor_smoking' | 'indoor_non_smoking' | 'outdoor_terrace' | 'outdoor_non_terrace'
  state: 'active' | 'cancelled'
  language: string
  created_at: string
  cancelled_at?: string | null
}

// Shape used by the ReservationsList UI (includes dispatcher-local status)
export interface Reservation {
  id: string
  customerName: string
  phone: string
  pax: number
  time: string   // e.g. "20:30"
  date: string   // e.g. "2026-06-19"
  section: string
  sectionName: string
  notes?: string
  status: 'Arrived' | 'No Show' | 'Pending' | 'Cancelled'
}

// ── ESCALATION TYPES (backend-aligned) ─────────────────────────────────────

export interface EscalationSummary {
  conversation_id: string
  customer_name: string
  customer_phone: string
  language: Language
  last_activity_at: string
  active_draft_summary?: string
  status?: "AI_HANDOFF" | "DISPATCHER_ACTIVE" | "RESOLVED"
}

export interface Turn {
  sender: 'customer' | 'bot' | 'dispatcher'
  text: string
  language: Language
  intent?: string
  created_at: string
}

export interface ActiveDraft {
  items: OrderItem[]
  fulfillment?: string
  address?: { text_value?: string }
  item_count: number
  estimated_total_usd?: number
}

export interface EscalationDetail extends EscalationSummary {
  assigned_dispatcher_id?: string
  transcript: Turn[]
  active_draft?: ActiveDraft
}

// ── NAVIGATION ─────────────────────────────────────────────────────────────

export type ActiveTab = 'Floor' | 'Bookings' | 'Admin'
