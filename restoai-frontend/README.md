# RestoAI Dispatcher UI

Mobile-first dispatcher portal for the RestoAI Telegram ordering bot. Built with React + Vite + Tailwind CSS.

## What it does

Dispatchers use this app on their phone to:
- Monitor incoming Telegram orders in real time (auto-refresh every 30 s)
- Advance orders through the kitchen/delivery workflow with one tap
- Cancel orders with a reason that is logged
- Manage table reservations
- Handle escalated Telegram conversations that the bot couldn't resolve
- View customer feedback

## Tabs

| Tab | Icon | Description |
|-----|------|-------------|
| **Floor** | Grid | Live order queue split into 🚚 Delivery and 📦 Pickup sections. Each card shows customer name, order total, status badge, and inline action buttons. |
| **Bookings** | Calendar | Table reservation list. Tap a reservation to mark Arrived or No Show. Use the + button to create a new reservation. |
| **Escalations** | Shield | Telegram conversations the bot handed off to a human. A red dot in the header alerts the dispatcher when a new escalation arrives. |
| **Settings** | Gear | Dispatcher profile, API health check, restaurant details, and links to the full menu and customer feedback. |

## Order flow

### Delivery
`Pending` → **Start Making** → `Being Made` → **On the Way** → `On the Way` → **Finish** → `Done`

### Pickup
`Pending` → **Start Making** → `Being Made` → **Finish** → `Done`

Cancel (✕) is available at every active state. A reason is required.

## Running locally

```bash
npm install
npm run dev        # http://localhost:5173
```

Create `.env.local` and set:

```
VITE_API_BASE_URL=http://localhost:8000
```

The API token (bearer) is entered on the login screen — it matches `DISPATCHER_API_TOKEN` in the backend `.env`.

## Stack

| | |
|-|-|
| Framework | React 18 + TypeScript |
| Build tool | Vite |
| Styling | Tailwind CSS v4 |
| Icons | Lucide React |
| API | Fetch against the RestoAI FastAPI backend |
