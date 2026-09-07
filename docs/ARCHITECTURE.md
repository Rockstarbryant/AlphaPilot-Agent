# AlphaPilot Architecture

## 1. Purpose

AlphaPilot is a **Binance research, policy, and proposal workflow** — see
`docs/ADVISORY_REFACTOR.md` for the authoritative walkthrough. This doc is
the layer/trust-boundary reference.

- AlphaPilot analyzes markets (RSI/MACD/momentum, Earn APY, margin
  eligibility) from public data — no Binance connection needed for this part.
- AlphaPilot finds opportunities (spot AND futures, every
  `scan_interval_minutes`), scores them, and enforces a deterministic Risk
  Engine before anything becomes a sized proposal.
- **Execution** always goes through an **allowlisted MCP client** (Claude,
  ChatGPT, Codex, …) connected to Binance's hosted MCP directly.
- AlphaPilot records fills and monitors positions; it never places or
  closes an order itself, in any workflow, under any trading mode.

AlphaPilot is **not** a Binance OAuth client, and this isn't a temporary
state — Binance's agent allowlist rejects self-built clients on the consent
screen, and AlphaPilot's OAuth client code was deleted (see
`BINANCE_AGENT_OS_REFACTOR.md`).

## 2. System flow

```text
 Public Binance REST              Standalone Copilot          Allowlisted MCP client
 (spot + futures)                 (OpenRouter, no                (Claude, ChatGPT…)
         │                         Binance needed)                       │
         ▼                              │                                │ OAuth
  AlphaPilot analysis/                  │                                ▼
  scanners + Risk Engine ◄──────────────┘                     Binance Agent OS MCP
         │                                                               │
         ▼                                                               │ place order
     TradePlan (proposed)                                                │
         │                                                               │
         ▼                                                               │
  AlphaPilot MCP / Web UI  ◄────────────────────────────────────────────┘
  approve / reject                                                       │
         │                                                                │
         │              record_fill / confirm-execution ◄─────────────────┘
         ▼
     Position + monitor (deterministic; raises ExitSignals, never executes them)
```

## 3. Layers

| Layer | Responsibility |
|--------|----------------|
| Presentation | Next.js — Dashboard, Opportunities, Market, Earn, Margin, Positions, Agent, Copilot |
| API | FastAPI — sessions, candidates, trade plans, market analysis, account-context relay, agent-chat, auth |
| Strategies | Gainer / Recovery / Hot Market — spot AND futures, hourly |
| Analysis (ad hoc) | `app/market/coin_analysis.py`, `app/margin/analysis.py`, `app/earn/scanner.py` — public data, no schedule |
| Risk | Hard gate — a `risk_check_passed=False` plan is never executable, by anyone |
| Market data | Public REST only, spot + futures (`app/binance/market_data.py`) |
| Account context | Relay only — `app/services/account_context.py` stores numbers an AI client reported, never reads Binance itself |
| AlphaPilot MCP | Analysis, Earn/margin scans, proposals, approve, record_fill, explain_panic |
| Binance MCP | Account + orders — via an allowlisted client only, never AlphaPilot |

## 4. Trust boundaries

```text
AI client (Claude / ChatGPT / standalone Copilot)
    │ may call AlphaPilot's tools/endpoints
    ▼
AlphaPilot Risk Engine  ── only risk_check_passed plans are ever confirmable
    │
    ▼
Human approval (UI or approve_trade_plan)
    │
    ▼
Binance Agent OS  ── external to AlphaPilot; user confirmation on writes
    │
    ▼
Agentic sub-account
```

The LLM never receives a Binance credential — there isn't one in this
system for it to receive. AlphaPilot stores no Binance credential of any
kind, ever, not even encrypted.

## 5. TradePlan lifecycle

1. Market scan (hourly, spot + futures — `app/jobs/daily_market_reset.py:run_market_scan`)
   OR a chat-driven request (`app/services/trade_proposal.py:build_trade_proposal`)
   → candidates → risk → `TradePlan` `proposed`.
2. `list_pending_proposals` / Opportunities+Agent UI.
3. `approve_trade_plan` → `approved`.
4. An allowlisted AI client executes via Binance Agent OS MCP directly.
5. `record_fill` / `confirm-execution` → `open` + `Position`.
6. Position monitor evaluates stops/ladders every 60s against public REST
   prices; on a mid-trade panic question, `explain_panic` re-runs the
   original analysis against current price.

## 6. Why not direct AlphaPilot → Binance MCP?

Binance Agent OS OAuth consent rejects unknown agents (`3346001-…`). This
isn't a bug to fix — it's Binance's policy, and the dual-MCP + relay
workflow above is the permanent shape of this integration, not a
placeholder for a future direct connection.
