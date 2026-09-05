# AlphaPilot

**Find Opportunities. Control Risk. Optimize Capital.**

AlphaPilot is an AI-assisted market operations agent designed for the **Binance Agent OS Mini Hackathon — Track A**. It combines deterministic market strategies and risk controls with an AI reasoning layer, then uses a direct MCP client to reach Binance Agent OS for account reads and trade execution.

> **Current status:** the direct Agent OS integration is implemented in the codebase, but a real Binance authorization + live-order smoke test has **not** been completed in this development environment. Do not treat the integration as production-verified until that test succeeds in the user's Binance Agent OS account.

## Current architecture

```text
                    ┌─────────────────────────┐
                    │   Binance Agent OS MCP   │
                    │ agent.binance.com/mcp/...│
                    └────────────┬────────────┘
                                 │ MCP / OAuth
                                 ▼
                    ┌─────────────────────────┐
                    │ AlphaPilot Binance MCP   │
                    │ client + Agent OS svc   │
                    └────────────┬────────────┘
                                 │
       ┌─────────────────────────┼────────────────────────┐
       │                         │                        │
       ▼                         ▼                        ▼
 Market scanners            Account state            Execution
       │                         │                        │
       ▼                         ▼                        ▼
 Strategies ─────────────► AI reasoning ────────► Risk Engine
                                                       │
                                                       ▼
                                                   TradePlan
                                                       │
                                                       ▼
                                             Binance Agent OS MCP
                                                       │
                                                       ▼
                                                   Order/fill
                                                       │
                                                       ▼
                                                    Position
                                                       │
                                                       ▼
                                               Position Monitor
```

### The important architectural change

The old implementation stopped at a proposal and required a separate AI client to execute it. That is no longer the intended execution path.

**Current path:**

```text
Market data
   ↓
Strategy
   ↓
AI reasoning
   ↓
Deterministic Risk Engine
   ↓
TradePlan
   ↓
AlphaPilot Binance Agent OS client
   ↓
Binance MCP
   ↓
Binance Agentic account
   ↓
Order verification
   ↓
AlphaPilot Position
```

AlphaPilot's own MCP server is a separate, optional interface into AlphaPilot. It is **not** the Binance MCP server and it is not required for AlphaPilot's direct Binance execution path.

## Binance Agent OS boundary

Binance's current developer documentation says its hosted MCP server can provide market data, Agentic-account balances/positions, and trading capabilities including Spot, Margin, Convert, USDⓈ-M Futures and COIN-M Futures, subject to the scopes and account permissions granted by the user. There is no withdrawal scope; transfers are limited to wallets inside the Agentic sub-account. Binance's current documentation also states that write actions are confirmed by the user first. See:

- https://developers.binance.com/en/docs/agent-native/mcp-server/agentic
- https://academy.binance.com/en/articles/how-binance-agent-os-is-changing-crypto-trading

The repository therefore treats Binance Agent OS as the **external execution authority** while AlphaPilot keeps its own deterministic risk layer in front of every order request.

## Components

### Backend

- FastAPI REST API
- SQLAlchemy + PostgreSQL
- Alembic migrations
- JWT authentication
- Deterministic strategy and risk engines
- OpenRouter AI reasoning provider
- Binance Agent OS MCP client
- OAuth/PKCE credential persistence abstraction
- Direct TradePlan execution and order reconciliation
- Account-state synchronization
- Position monitoring and exit execution
- Optional AlphaPilot MCP server
- Background scheduler

### Frontend

Next.js dashboard with pages for:

- Dashboard
- Agent
- Market
- Opportunities
- Positions
- Risk
- Margin
- Earn
- Activity
- Settings

The Agent and Dashboard views include Binance Agentic account state, connection status, trading mode, risk status and direct execution controls.

## Account state

After authorization, AlphaPilot can request account state through `/api/binance/account/{user_id}`. The frontend presents returned balances, USDT availability, portfolio value when explicitly returned by Binance, open positions and open orders.

The frontend deliberately does **not** invent portfolio valuation for non-USDT assets. If Binance does not return a portfolio value, the UI shows `—` rather than pretending that the sum of raw token quantities is a USD value.

## Trading modes

AlphaPilot supports:

- `read_only` — no new execution.
- `approval_required` — AlphaPilot may prepare/submit the action through Agent OS, but Binance's own authorization/confirmation policy remains authoritative.
- `autonomous` — intended for an Agent OS connection configured to allow autonomous execution within its granted permissions. AlphaPilot still enforces its deterministic risk checks.

AlphaPilot never attempts to bypass Binance's authorization or confirmation controls.

## Quick start

### Backend

```bash
cp .env.example .env
docker compose up -d postgres
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Open `http://localhost:3000`, register, then open **Agent**.

### Tests

```bash
cd backend
pytest tests/ -v
```

The repository was statically compiled successfully during this refactor. Full tests and the Next.js build require the project dependencies and PostgreSQL environment; those were not available in the isolated verification environment used for this archive.

## Documentation map

- `docs/ARCHITECTURE.md` — current system architecture and trust boundaries
- `docs/AGENT.md` — agent lifecycle and direct Agent OS execution
- `docs/BINANCE_CAPABILITY_MATRIX.md` — Binance capabilities, implementation status and verification state
- `docs/MCP_SERVER.md` — AlphaPilot's optional MCP server vs Binance's MCP server
- `docs/API.md` — REST API, including Agent OS endpoints
- `docs/SECURITY.md` — authentication, OAuth-token handling, authorization boundaries and known gaps
- `docs/RISK_ENGINE.md` — deterministic risk rules and execution gate
- `docs/STRATEGIES.md` — strategy behavior
- `docs/DEPLOYMENT.md` — local/Render/Vercel deployment and Agent OS callback configuration
- `docs/HACKATHON_DEMO.md` — recommended Track A demonstration
- `docs/FINAL_IMPLEMENTATION_REPORT.md` — honest implementation and verification status
- `docs/VERIFICATION.md` — file-by-file verification scope, test limitations and debugging order
- `BINANCE_AGENT_OS_REFACTOR.md` — change log for this refactor
