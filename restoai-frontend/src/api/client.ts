const BASE = import.meta.env.VITE_API_BASE_URL || ''

function token(): string {
  return localStorage.getItem('restoai_bearer_token') || ''
}

function dispatcherName(): string {
  return localStorage.getItem('restoai_dispatcher_name') || ''
}

async function req(path: string, opts: RequestInit = {}): Promise<Response | null> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token()}`,
      ...(opts.headers || {}),
    },
  })
  if (res.status === 401) {
    localStorage.removeItem('restoai_bearer_token')
    localStorage.removeItem('restoai_dispatcher_name')
    window.location.href = '/?expired=1'
    return null
  }
  return res
}

export const api = {
  dispatcherName,

  // Orders
  getOrders: (flag?: string) =>
    req(`/api/dispatcher/orders${flag ? `?flag=${flag}` : ''}`),
  getOrder: (id: string) =>
    req(`/api/dispatcher/orders/${id}`),
  enterInPos: (id: string) =>
    req(`/api/dispatcher/orders/${id}/entered-in-pos`, {
      method: 'POST',
      body: JSON.stringify({ dispatcher_name: dispatcherName() }),
    }),
  cancelOrder: (id: string, reason: string) =>
    req(`/api/dispatcher/orders/${id}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ dispatcher_name: dispatcherName(), reason }),
    }),

  // Reservations
  getReservations: (params?: { date?: string; state?: string }) => {
    const q = new URLSearchParams()
    if (params?.date) q.set('date', params.date)
    if (params?.state) q.set('state', params.state)
    const qs = q.toString()
    return req(`/api/dispatcher/reservations${qs ? `?${qs}` : ''}`)
  },

  // Escalations
  getEscalations: () =>
    req('/api/dispatcher/escalations'),
  getEscalation: (id: string) =>
    req(`/api/dispatcher/escalations/${id}`),
  takeOver: (id: string) =>
    req(`/api/dispatcher/escalations/${id}/take-over`, {
      method: 'POST',
      body: JSON.stringify({ dispatcher_name: dispatcherName() }),
    }),
  sendMessage: (id: string, text: string) =>
    req(`/api/dispatcher/escalations/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ dispatcher_name: dispatcherName(), text }),
    }),
  closeHandoff: (id: string) =>
    req(`/api/dispatcher/escalations/${id}/close-handoff`, {
      method: 'POST',
      body: JSON.stringify({ dispatcher_name: dispatcherName() }),
    }),
}
