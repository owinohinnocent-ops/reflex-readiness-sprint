# Reflex delivery management

Reflex coordinates deliveries for small retailers. The original FastAPI/SQLAlchemy backend remains unchanged; the new browser client lives in `frontend/` and is deliberately built around its existing API.

## Architecture

`Browser UI → frontend/server.mjs proxy → existing FastAPI API → SQLAlchemy database`

The local proxy makes the UI and API same-origin during development, so no backend CORS change is required. In production, serve `frontend/` from the same origin as the API or configure an equivalent reverse proxy.

## Start the frontend

1. Start the existing FastAPI backend on `http://127.0.0.1:8000` using the project’s established backend setup.
2. In another terminal, run `node frontend/server.mjs`.
3. Open `http://localhost:5173` and sign in with a user already present in the database.

If your terminal is not already inside this project folder, use either of these instead:

```powershell
node "C:\Users\chris\Desktop\Reflex gp 91\frontend\server.mjs"
```

Or double-click `start-reflex-frontend.cmd` in the project folder.

You may double-click the workspace `index.html` to preview the login interface. For working authentication and delivery data, use the local-server address above: browsers restrict direct `file://` pages from reliably calling the API.

The frontend sends requests to `/api`, which the development server forwards to the FastAPI process.

## Run from another device or a remote host

The frontend server now listens on all network interfaces. Start it normally, then open `http://YOUR-COMPUTER-IP:5173` from a phone or another computer on the same network. Allow Node.js through the Windows firewall if Windows asks.

When the FastAPI API runs somewhere other than the same computer, provide its public/internal origin before starting the frontend server:

```powershell
$env:REFLEX_API_ORIGIN = "https://your-api.example.com"
node frontend/server.mjs
```

For a hosting platform, run this server (or configure its reverse proxy equivalent) rather than uploading and opening `index.html` directly. It serves the browser files and forwards `/api/*` to the backend, avoiding browser cross-origin restrictions.

## Personas

- **Retailer**: creates delivery requests and sees only their deliveries, their assigned rider profile ID, state, and backend-provided status history/progress.
- **Dispatcher**: sees all deliveries and live status counts, then assigns `OPEN` or `FAILED` deliveries using an available rider *profile* ID.
- **Rider**: sees deliveries assigned to their linked Rider profile and can make only the next server-supported transition: `ASSIGNED → PICKED_UP → DELIVERED`.

## Existing API integrations

| Endpoint | Frontend use |
| --- | --- |
| `POST /auth/login` | Sign in with phone and password |
| `GET /auth/me` | Obtain backend-authorized identity and role |
| `GET /deliveries` | Role-scoped dashboard data and counts |
| `POST /deliveries` | Retailer delivery request creation |
| `POST /deliveries/{id}/assign` | Dispatcher assignment |
| `PATCH /deliveries/{id}/status` | Rider pickup/delivery confirmation |

## Status and synchronization

The backend defines the actual lifecycle as `OPEN → ASSIGNED → PICKED_UP → DELIVERED`; an assigned or picked-up delivery can instead become `FAILED`, and a failed delivery may be assigned again. The UI uses those exact values—there is no frontend-only `IN_TRANSIT` state.

The backend has no WebSocket or SSE route. While the user is logged in, the UI polls `GET /deliveries` every 20 seconds only when the tab is visible, and refreshes immediately after a successful mutation.

## Real API mode and Demo Mode

When the login screen opens, the frontend makes one `GET /health` request through its configured API base. A successful response displays **API Connected** and the normal phone/password login remains the only route into **Real API mode**.

When that check fails, the screen displays **API Offline — Demo Mode Available** without blocking the user. The Retailer Demo, Dispatcher Demo, and Rider Demo buttons create an in-memory session and a fresh, small set of Kenyan delivery examples. These demo buttons never call the API, and demo creation, assignment, status progression, and order confirmation never write to FastAPI or the database. Logging out clears the demo session and its temporary deliveries.

Demo-only status progression is `ASSIGNED → PICKED_UP → IN_TRANSIT → DELIVERED` so it can show the requested presentation workflow. Real API mode still uses the backend’s supported lifecycle and never sends `IN_TRANSIT`.

## Known backend limitations surfaced in the UI

- There is no API endpoint to list Rider records or their availability. The dispatcher interface therefore accepts a rider profile ID and lets the existing assignment endpoint validate availability.
- There is no QR/barcode scan or confirmation endpoint. The rider UI does not pretend that QR confirmation occurred; its scanner action explains that backend integration point is missing.
- The files supplied to this workspace use package imports such as `database`, `models`, `routes`, `schemas`, and `services`, while those package directories are not present in the supplied folder. The frontend has not altered this backend structure; its startup must use the existing package layout/environment from which these files originated (or that layout must be restored separately).
