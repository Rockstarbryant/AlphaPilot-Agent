# AlphaPilot

**A Binance research & trading advisory.**

AlphaPilot analyzes Binance markets (RSI, MACD, momentum, regime) and gives
a plain-language long/short/hold view for any symbol, scans Simple Earn for
APY and margin trades for eligibility, and — when you want to size a real
trade — builds a risk-validated proposal (margin, leverage, stop, take-profit
ladder). It never places an order itself.

> New to this repo? Read [`docs/ADVISORY_REFACTOR.md`](docs/ADVISORY_REFACTOR.md)
> first — it's the authoritative architecture doc. `BINANCE_AGENT_OS_REFACTOR.md`
> at the root is kept only as a history of how this integration got here.

## Why AlphaPilot doesn't execute trades itself

Binance's Agent OS allowlists only a handful of named AI clients for
Agentic OAuth — Claude Desktop/Code, ChatGPT, Codex, VS Code, Grok Bot. A
self-built backend like AlphaPilot's is rejected on Binance's consent
screen. So AlphaPilot **never holds a Binance credential of any kind**.
Instead:

1. AlphaPilot answers "what do you think about this coin" from public data alone.
2. When you want a sized trade, an allowlisted AI client (e.g. Claude) reads
   your real Binance balance and relays it to AlphaPilot.
3. AlphaPilot returns a risk-validated proposal (size, leverage, stop, targets).
4. You approve; the AI client places the order through Binance Agent OS MCP
   directly and confirms the fill back to AlphaPilot, which then monitors it.

```text
                    ┌─────────────────────────────┐
 "what about BTC?"  │      AlphaPilot MCP /        │   analyze_symbol
 ─────────────────► │      REST / Copilot chat     │ ─ (public data,
                    │  (this repo, no Binance      │    no auth needed)
                    │   credential, ever)           │
                    └───────────────┬──────────────┘
                                    │ submit_account_context
                                    │ build_trade_proposal
                                    ▼
                    ┌─────────────────────────────┐
  approve → order   │   Allowlisted AI client      │
 ◄───────────────── │   (Claude, ChatGPT, ...)      │
                    └───────────────┬──────────────┘
                                    │ places order directly
                                    ▼
                         Binance Agent OS MCP
                                    │
                                    │ record_fill / confirm-execution
                                    ▼
                    AlphaPilot Position + monitor
```

## What AlphaPilot can do

- **Coin analysis** — RSI/MACD/momentum + market regime → long/short/
  hold-spot bias with a confidence score and rationale, for any symbol.
  Public data only, no account needed. (`app/market/coin_analysis.py`)
- **Simple Earn scan** — current flexible-product APY. Read-only; AlphaPilot
  never subscribes/redeems. (`app/earn/scanner.py`)
- **Margin analysis** — per-symbol eligibility (liquidity, spread, regime,
  conviction), suggested leverage, and an interest-cost estimate.
  (`app/margin/analysis.py`)
- **Trade proposals** — margin/leverage/stop/take-profit-ladder, risk-gated
  against your relayed Binance balance. (`app/services/trade_proposal.py`)
- **Panic explainer** — "it's going against me, should I close it?" re-runs
  the analysis against current price and tells you if the original thesis
  still holds. (`app/services/panic_advisor.py`)
- **Scheduled strategies** — Gainer Hunter, Recovery Hunter, Hot Market
  Margin run every hour (not daily) across **both** spot and futures
  markets, and produce the same kind of risk-validated proposals as the
  chat-driven path. Every candidate — qualified, watching, or rejected —
  gets a reason, and is pruned after 6 hours if it never became a proposal.
  (`app/strategies/`, `app/jobs/daily_market_reset.py`, `app/jobs/market_cleanup.py`)
- **Plain-language explanations** — any scanned coin can be explained in
  non-technical language on demand. (`app/services/candidate_explainer.py`)
- **Standalone Copilot chat** — a free-OpenRouter-model chat page that needs
  no MCP client at all, with persistent history and an honest status
  indicator for whether AI narration is actually configured (falls back to
  deterministic templated answers otherwise — never silently fakes it).
  (`app/api/routes/agent_chat.py`, `frontend/app/(app)/copilot/page.tsx`)

## Components

### Backend

- FastAPI + PostgreSQL + Alembic + JWT
- Deterministic strategies + Risk Engine (`app/risk/engine.py`) — the sole
  authority on whether a proposal is safe to execute
- Public Binance REST market data — no API key needed for any of this
- AlphaPilot's own MCP server (`app/mcp_server.py`) for the dual-MCP workflow
- Scheduler for market reset / position monitoring

### Frontend

Next.js: Dashboard, Market (coin analysis), Earn, Margin, Positions
(with panic explainer), Agent (account-context relay + execution
confirmation), Copilot (standalone chat), Risk, Settings.

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

### AlphaPilot MCP (for the dual-MCP workflow)

```bash
cd backend
MCP_SERVER_HOST=0.0.0.0 MCP_SERVER_PORT=9000 python -m app.mcp_server
```

Add this alongside `https://agent.binance.com/mcp/agentic` in Claude
Desktop/Code (or another allowlisted client). Call `wiring_instructions`
first for the full checklist.

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

## Env (backend)

```text
DATABASE_URL=...
JWT_SECRET=...
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=...          # a real ":free"-suffixed OpenRouter model id
BINANCE_PUBLIC_REST_BASE=https://api.binance.com
BINANCE_MCP_ENDPOINT=https://agent.binance.com/mcp/agentic   # documentation only — AlphaPilot never connects to this itself
BINANCE_EARN_API_KEY=          # optional, read-only, for the Earn APY scan
PUBLIC_BASE_URL=https://your-backend
FRONTEND_PUBLIC_URL=https://your-frontend
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=9000
```

No Binance API key or OAuth material is ever required or stored — see
`docs/ADVISORY_REFACTOR.md`.

## Documentation

| Doc | Content |
|-----|---------|
| `docs/ADVISORY_REFACTOR.md` | **Start here** — current architecture |
| `docs/ANALYSIS_ENGINE.md` | The multi-factor analysis engine — every category, data source, and what degrades when a key isn't set |
| `docs/ARCHITECTURE.md` | System layers and trust boundaries |
| `docs/MCP_SERVER.md` | AlphaPilot MCP tool reference + wiring |
| `docs/API.md` | REST API |
| `docs/RISK_ENGINE.md` | Deterministic risk rules |
| `docs/STRATEGIES.md` | Strategy behavior |
| `docs/BINANCE_CAPABILITY_MATRIX.md` | What's live-verified vs. not |
| `docs/SECURITY.md` | Security model |
| `docs/DEPLOYMENT.md` | Deploy notes |
| `BINANCE_AGENT_OS_REFACTOR.md` | History only — why direct-client access was abandoned |

## Honest status

- Market discovery, coin/margin analysis, and Earn scanning: public REST,
  no auth, working as designed.
- Risk-validated proposals (scheduled or chat-driven): deterministic, don't
  depend on any AI model being available.
- Live Binance order placement: always via an allowlisted AI client
  connected to Binance Agent OS MCP directly, confirmed back to AlphaPilot.
- AlphaPilot-as-Binance-OAuth-client: **not** a supported path, and not
  planned unless Binance changes its allowlist policy.
