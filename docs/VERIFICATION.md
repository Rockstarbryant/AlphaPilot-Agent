# AlphaPilot Repository Verification

**Verification pass:** September 4, 2026

This document records what was inspected before the archive was rebuilt. It is intentionally an engineering debugging hand-off document for debugging, not a claim of live Binance certification.

## Repository inventory

- Backend application files: 96
- Backend test files: 20
- Frontend application/component/library source files: 21
- Markdown documentation files: 11

## Backend areas inspected

- `app/main.py` — route registration and CORS
- `app/core/config.py` — Agent OS endpoint and environment configuration
- `app/binance/agent_os_mcp_client.py` — MCP transport, discovery, OAuth/PKCE helpers, tool resolution and order calls
- `app/services/binance_agent_os.py` — direct account, execution and reconciliation orchestration
- `app/api/routes/binance.py` — connection/account/capability endpoints
- `app/api/routes/trade_plans.py` — direct execution and legacy reconciliation
- `app/api/routes/positions.py` — monitoring and direct exit endpoint
- `app/jobs/position_monitor.py` — deterministic exit detection and Agent OS execution routing
- `app/models/models.py` — Binance connection, TradePlan, Position, ExitSignal and account snapshot models
- `app/risk/engine.py` — deterministic risk gate
- `app/strategies/*` — strategy-to-TradePlan pipeline
- `app/mcp_server.py` — AlphaPilot-owned optional MCP server
- Alembic migrations
- backend tests and fixtures

## Frontend areas inspected

- `lib/api.ts` — REST API client and types
- `app/(app)/agent/page.tsx` — Agent OS connection, account state, trading mode and direct execution
- `components/account-state.tsx` — Agentic balances/positions/orders UI
- `app/(app)/dashboard/page.tsx` — compact account-state integration
- `app/(app)/positions/page.tsx` — direct Agent OS exit execution UI
- remaining application pages/components for stale architecture references and API usage
- package/build configuration

## Documentation areas inspected and rewritten

- root `README.md`
- `BINANCE_AGENT_OS_REFACTOR.md`
- `docs/AGENT.md`
- `docs/ARCHITECTURE.md`
- `docs/BINANCE_CAPABILITY_MATRIX.md`
- `docs/MCP_SERVER.md`
- `docs/API.md`
- `docs/SECURITY.md`
- `docs/RISK_ENGINE.md`
- `docs/STRATEGIES.md`
- `docs/DEPLOYMENT.md`
- `docs/HACKATHON_DEMO.md`
- `docs/FINAL_IMPLEMENTATION_REPORT.md`
- `frontend/README.md`

## Static verification

### Python

`python -m compileall -q backend/app backend/tests` passed.

### Repository-wide stale architecture search

A repository-wide search was run to ensure the current documentation and UI describe AlphaPilot as the direct Binance Agent OS MCP client. Any compatibility-only language is explicitly marked as legacy and is not part of the normal execution path.

### Frontend runtime verification

A fresh `npm install` could not complete in the isolated environment because the package installation timed out. Consequently `npm run lint` and `npm run build` were not claimed as successful in this pass.

### Backend runtime verification

A `pytest tests/ -q` collection attempt could not start because the isolated environment lacked runtime dependencies including `asyncpg`, `respx` and `mcp`. Therefore no full test-suite pass is claimed here.

### Binance live verification

No live Binance account was authorized and no real order was submitted. The direct MCP/OAuth implementation therefore remains **protocol-ready but live-unverified** until the user performs the connection test.

## First debugging milestone

Do not begin with a live order. Debug in this exact order:

```text
A. /api/health
B. Binance authorization URL generation
C. OAuth callback
D. /api/binance/connection/{user_id}
E. /api/binance/capabilities/{user_id}
F. /api/binance/account/{user_id}
G. /api/binance/ticker/{user_id}/BTCUSDT
H. inspect the actual tools/list response
I. run a small risk-approved order
J. reconcile order status
K. confirm Position creation
L. trigger/test an exit signal
M. reconcile exit and Position state
```

The live Binance `tools/list` response is the source of truth. If the actual tool names, schemas or authorization flow differ from the generic adapter assumptions, fix the adapter rather than guessing at Binance-specific behavior.

## Known non-Agent-OS security work

Several older generic API routes predate the direct Agent OS refactor and should receive an ownership/authentication audit before public deployment. The new Binance routes already require the current authenticated user to match the requested user ID.
