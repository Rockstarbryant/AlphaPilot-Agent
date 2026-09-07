# AlphaPilot Deployment

## Services

Four separate deployables, defined in `render.yaml` and `backend/render.yaml`:

1. **FastAPI web service** (`alphapilot-backend` or similar) — the REST API
   the frontend calls. `backend/Dockerfile`.
2. **AlphaPilot MCP server** (`alphapilot-mcp-server`) — a *separate* service
   from #1, on its own URL/port (9000 by default). This is what an
   allowlisted AI client (Claude, ChatGPT, etc.) connects to alongside
   Binance Agent OS MCP. `backend/Dockerfile.mcp`.
3. **Scheduler worker** (`alphapilot-scheduler`) — runs `app/jobs/scheduler.py`
   continuously; no public URL needed. Market scans (hourly, spot+futures)
   and position monitoring (every 60s) both live here. `backend/Dockerfile.scheduler`.
4. **Next.js frontend** — deployed separately (e.g. Vercel).

PostgreSQL is the persistent database, shared by all three backend services.

**These are three distinct running processes, not three routes on one
service.** If you only see one backend service in your hosting dashboard,
the MCP server and/or scheduler were never actually deployed — see
"Finding your AlphaPilot MCP URL" below.

## Environment variables

Backend (all three services read the same `DATABASE_URL`; see `.env.example`
for the full annotated list):

```text
DATABASE_URL
JWT_SECRET
APP_ENV
AI_PROVIDER=openrouter
OPENROUTER_API_KEY
OPENROUTER_MODEL          # a real ":free"-suffixed model id — see .env.example
BINANCE_PUBLIC_REST_BASE=https://api.binance.com
BINANCE_MCP_ENDPOINT=https://agent.binance.com/mcp/agentic   # documentation only
BINANCE_EARN_API_KEY      # optional, read-only
MCP_CLIENT_NAME=AlphaPilot Agent
MCP_SERVER_HOST=0.0.0.0   # MCP service only
MCP_SERVER_PORT=9000      # MCP service only
PUBLIC_BASE_URL
FRONTEND_PUBLIC_URL
```

No OAuth variables exist anymore — AlphaPilot never authenticates to
Binance (see `docs/ADVISORY_REFACTOR.md`).

Frontend:

```text
NEXT_PUBLIC_API_URL=https://YOUR-BACKEND-WEB-SERVICE
```

Note this points at service #1 (the REST API), not the MCP server (#2) —
the frontend never talks MCP directly.

## Render

`render.yaml` (repo root) defines all three backend services plus the free
PostgreSQL instance. Set every `sync: false` variable in the Render
dashboard yourself after the first deploy.

### Finding your AlphaPilot MCP URL

1. In the Render dashboard, look for a service separate from your main
   backend — named `alphapilot-mcp-server` per `render.yaml`, running
   `Dockerfile.mcp`, listening on port 9000.
2. If it exists: open it, copy its public URL. The MCP endpoint path is
   `/mcp` (Streamable HTTP) — e.g. `https://alphapilot-mcp-server-xxxx.onrender.com/mcp`.
3. If it doesn't exist: it was never deployed as its own service. Add it
   from `render.yaml` (Render → New → Blueprint, pointing at this repo, or
   manually create a Web Service using `backend/Dockerfile.mcp`).
4. Confirm it's actually running — free-tier Render services sleep after ~15
   minutes idle and take up to a minute to wake on the next request; a
   connector "not responding" in Claude on the first try is often just this.

### Wiring it into Claude

1. Claude → **Settings → Connectors → Add custom connector**.
2. Name: `AlphaPilot`. URL: the `/mcp` URL from above.
3. Separately add `https://agent.binance.com/mcp/agentic` the same way, and
   complete Binance's own authorization in the browser.
4. In a new chat, ask Claude to call AlphaPilot's `wiring_instructions` tool
   — it self-reports the full dual-MCP checklist.

## Local development

```bash
docker compose up -d postgres
cd backend && pip install -r requirements.txt && alembic upgrade head
uvicorn app.main:app --reload                    # terminal 1: API
python -m app.jobs.scheduler                     # terminal 2: scans + monitor
MCP_SERVER_PORT=9000 python -m app.mcp_server     # terminal 3: MCP server
cd ../frontend && npm install && npm run dev      # terminal 4
```

## First production smoke-test checklist

```text
[ ] GET /api/health returns 200
[ ] Frontend can register/login (no raw 401 JSON on an expired token — should
    redirect to /login?expired=1 instead)
[ ] Market scan runs (Dashboard → Run scan) and produces candidates tagged
    both market_type=spot and market_type=futures
[ ] Opportunities tab shows a reason for watching/rejected candidates, not
    just qualified ones, and nothing older than 6 hours
[ ] "Explain this in plain English" returns a real explanation (or a clear
    templated fallback if OPENROUTER_API_KEY isn't set)
[ ] Copilot: GET /api/agent-chat/status reports ai_configured=true if you
    expect AI narration; a chat message about a bare symbol ("what about
    SOL?") resolves, not just explicit pairs
[ ] AlphaPilot MCP server is reachable at its own URL (separate from the
    backend) and Claude lists its tools after adding it as a connector
[ ] submit_account_context → build_trade_proposal → approve → (execute via
    Binance Agent OS MCP, not AlphaPilot) → record_fill opens a Position
[ ] Position monitor generates an ExitSignal when a stop/target is crossed,
    and confirm-execution closes the loop
```

## Known operational notes

- **JWT expiry**: tokens last `jwt_expire_minutes` (default 24h). An expired
  token now redirects to `/login?expired=1` instead of showing raw JSON —
  if you see this often, check whether `JWT_SECRET` is stable across
  deploys (a `generateValue: true` secret that gets regenerated on a full
  service recreate, rather than an in-place redeploy, invalidates every
  existing session at once).
- Market scans and position monitoring only run while the scheduler service
  is actually up — a paused/crashed scheduler means stale Opportunities and
  unmonitored Positions even if the API is healthy.
