# AlphaPilot Deployment

## Services

The repository supports three backend processes plus the Next.js frontend:

1. FastAPI web service
2. AlphaPilot MCP server (optional)
3. Scheduler worker
4. Next.js frontend

PostgreSQL is the persistent database.

## Environment variables

Backend:

```text
DATABASE_URL
JWT_SECRET
APP_ENV
AI_PROVIDER
OPENROUTER_API_KEY
OPENROUTER_MODEL
BINANCE_PUBLIC_REST_BASE=https://api.binance.com
BINANCE_MCP_ENDPOINT=https://agent.binance.com/mcp/agentic
MCP_CLIENT_NAME=AlphaPilot Agent
MCP_OAUTH_REDIRECT_URI=https://YOUR-BACKEND.onrender.com/api/binance/oauth/callback
MCP_OAUTH_ENCRYPTION_KEY=<Fernet key>
PUBLIC_BASE_URL=https://YOUR-BACKEND.onrender.com
```

Frontend:

```text
NEXT_PUBLIC_API_URL=https://YOUR-BACKEND
```

## Render

`render.yaml` contains the backend, MCP server, scheduler and free PostgreSQL service definitions. Set the `sync: false` variables in the Render dashboard.

The OAuth redirect URI must point to the publicly reachable FastAPI callback endpoint.

Example shape:

`https://alphapilot-backend.example.com/api/binance/oauth/callback`

Do not put the OAuth encryption key in the frontend.

## Local Agent OS debugging

Start the backend and frontend. Then:

1. Register/login.
2. Open **Agent**.
3. Click **Connect Binance Agent OS**.
4. Complete Binance authorization in the browser.
5. Return to AlphaPilot.
6. Check connection status.
7. Call capabilities discovery.
8. Read account state.
9. Run a market scan.
10. Execute only a very small, risk-approved test order after the read-only path is confirmed.

## First production smoke-test checklist

```text
[ ] /api/health works
[ ] OAuth redirect reaches public backend
[ ] Binance authorization succeeds
[ ] connection status = connected
[ ] tools/list succeeds
[ ] account read succeeds
[ ] ticker read succeeds
[ ] TradePlan risk gate succeeds
[ ] Binance order tool is identified from live schema
[ ] Binance-side confirmation/authorization behaves as expected
[ ] order status is reconciled
[ ] Position is created only after FILLED
[ ] exit signal reaches same execution service
```

## Verification caveat

The archive's isolated environment successfully compiled the Python source but did not have all runtime/test dependencies available, and it did not perform a live Binance authorization. The frontend dependency installation/build was likewise not completed in that environment. Treat the first local run as an integration-debugging phase, not as a production certification.
