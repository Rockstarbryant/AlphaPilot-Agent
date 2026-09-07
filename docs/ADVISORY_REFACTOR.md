# AlphaPilot Advisory Refactor

This is the current, authoritative description of AlphaPilot's architecture.
If another doc in this repo disagrees with this one, this one is right —
flag the other doc for an update.

## What AlphaPilot is

AlphaPilot is a **Binance research and trading advisory**. Given a symbol,
it fetches public market data, computes RSI/MACD/momentum, and gives a
long/short/hold-spot view with a confidence score and plain-language
rationale. It also scans Binance Simple Earn for APY and evaluates
margin-trade eligibility. None of this requires a Binance account.

When a user wants to size an actual trade, AlphaPilot builds a
risk-validated proposal (margin, leverage, hard stop, take-profit ladder) —
but it never places the order itself.

## Why AlphaPilot never touches Binance Agent OS directly

Binance's agent allowlist for Agentic OAuth only covers a named set of AI
clients: Claude Desktop, Claude Code, ChatGPT, Codex, VS Code, and Grok Bot.
AlphaPilot's own backend is not on that list and never will be without
Binance adding it — see `BINANCE_AGENT_OS_REFACTOR.md` for the history of
why an earlier direct-client attempt was abandoned. This isn't a workaround;
it's the permanent shape of the integration: **AlphaPilot holds no Binance
credential of any kind**, ever.

## The dual-MCP workflow

The user runs one of the allowlisted AI clients (this doc assumes Claude, but
any allowlisted client works the same way) and connects it to **two** MCP
servers at once:

1. **Binance Agent OS MCP** (`https://agent.binance.com/mcp/agentic`) — the
   client authenticates directly with Binance and gets account/trading tools.
2. **AlphaPilot MCP** (`backend/app/mcp_server.py`, this repo) — analysis,
   Earn/margin scans, proposal building, and fill recording.

```text
User: "What do you think about BTC/USDT — long, short, or just buy and hold?"
   │
   ▼
Claude calls AlphaPilot MCP: analyze_symbol("BTCUSDT")
   │  (RSI/MACD/momentum + regime → bias + confidence; public data only)
   ▼
Claude answers the user directly — no Binance connection needed yet

User: "OK, size me a long with my real balance."
   │
   ▼
Claude calls Binance Agent OS MCP: read account balance/positions
   │
   ▼
Claude calls AlphaPilot MCP: submit_account_context(user_id, portfolio_value_usdt, ...)
   │  (relays what it just read — AlphaPilot stores it with a timestamp)
   ▼
Claude calls AlphaPilot MCP: build_trade_proposal(user_id, "BTCUSDT", "long")
   │  (risk engine validates against RiskPolicy + the relayed balance;
   │   returns suggested margin, leverage, hard stop, take-profit ladder)
   ▼
Claude presents the proposal; human approves
   │
   ▼
Claude places the order via Binance Agent OS MCP directly (AlphaPilot never does this)
   │
   ▼
Claude calls AlphaPilot MCP: record_fill(plan_id, order_id, fill_price, quantity)
   │  (AlphaPilot opens a Position and starts monitoring stops/targets)
   ▼
... later, price moves against the position ...

User: "This is going against me, should I close it?"
   │
   ▼
Claude calls AlphaPilot MCP: explain_panic(position_id, question)
   │  (re-runs analyze_symbol against current price; reports whether the
   │   original thesis still holds, distance to stop, a recommendation)
   ▼
Claude answers the user. If they close it, execution again goes through
Binance Agent OS MCP directly, confirmed back via record_fill / confirm-execution.
```

The scheduled strategies (Gainer Hunter, Recovery Hunter, Hot Market Margin)
follow the same shape minus the chat trigger: they run on a timer, produce
risk-validated `TradePlan`s, and wait for the same approve → execute →
confirm loop.

## The account-context relay

Because AlphaPilot can't read Binance itself, `app/services/account_context.py`
is the seam: whichever AI client the user is chatting with reports balance
and exposure numbers here (via the MCP tool `submit_account_context` or
`POST /api/binance/account-context/{user_id}`), and AlphaPilot stores them
with a timestamp. `build_trade_proposal` refuses to size a trade against a
snapshot older than 10 minutes (`MAX_CONTEXT_AGE`) — it asks for a re-read
rather than sizing off stale numbers. AlphaPilot never stores anything that
could authenticate to Binance, only the numbers it was told.

## The standalone Copilot (no MCP client required)

Not everyone wants to run Claude Desktop with two MCP servers wired up. The
frontend's **Copilot** page (`frontend/app/(app)/copilot/page.tsx`) talks
directly to `POST /api/agent-chat/{user_id}/message`
(`app/api/routes/agent_chat.py`), which is backed by a free OpenRouter model
(`OPENROUTER_MODEL` in `.env.example`). It can do everything that needs only
public data — symbol analysis, Earn scan, margin analysis — and explain an
existing position's panic question. It **cannot** read live Binance balances
or place trades, because it has no Agent OS connection; for that, use the
Agent page's dual-MCP setup. The routing inside `agent_chat.py` is
deterministic (keyword + symbol extraction gathers real numbers first); the
AI model only phrases the final answer around those numbers and never
invents one.

## What never changed

- The deterministic Risk Engine (`app/risk/engine.py`) is still the sole
  authority on whether a proposal passes — nothing here bypasses it.
- The Position Monitor (`app/jobs/position_monitor.py`) still runs on a
  timer and is independent of any AI client — it now only *detects* exit
  conditions (hard stop / profit target / stagnation) and raises
  `ExitSignal`s; it never executes them, for the same allowlist reason
  above. A human or their connected client executes through Binance Agent
  OS MCP and confirms back via `POST /api/positions/exit-signals/{id}/confirm-execution`.
- Public Binance REST (`app/binance/market_data.py`) is unauthenticated and
  unaffected by any of this — it's what powers analysis, regime detection,
  and the scheduled strategies' market scans.

## Scanning cadence and breadth

Scheduled strategies (Gainer/Recovery/Hot Market Margin) run every
`settings.scan_interval_minutes` (default 60), not once a day, and scan
**both** spot and USDⓈ-M futures perpetuals — every `MarketCandidate` is
tagged `market_type`. A candidate that never became a `TradePlan` is pruned
after `candidate_retention_hours` (default 6) so the Opportunities tab never
shows a stale scan. Every candidate — qualified, watching, or rejected — now
gets a plain `reason` string, and can be expanded into a fuller
non-technical explanation on demand via `POST /api/candidates/{id}/explain`
(`app/services/candidate_explainer.py`, OpenRouter-backed with a
deterministic fallback). See `docs/STRATEGIES.md`.

## Copilot persistence and honesty about AI availability

The standalone Copilot page persists every turn to a `ChatMessage` table
(`GET/POST /api/agent-chat/{user_id}/...`), so conversation history survives
a reload. Each reply also reports `ai_narration_used: bool` — when
`OPENROUTER_API_KEY`/`OPENROUTER_MODEL` aren't configured (or the call
fails), the user sees a visible "templated reply" flag instead of silently
getting a generic-sounding answer indistinguishable from a working one.
`GET /api/agent-chat/status` exposes this for a page-level status indicator.

## Where to look next

- `docs/MCP_SERVER.md` — full tool list and wiring steps
- `docs/API.md` — REST surface
- `docs/RISK_ENGINE.md` — the risk gate
- `docs/BINANCE_CAPABILITY_MATRIX.md` — what's read-only vs. what still needs
  a live Binance smoke test
