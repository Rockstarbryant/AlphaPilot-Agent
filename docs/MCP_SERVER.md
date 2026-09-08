# MCP Architecture

AlphaPilot uses **two different MCP roles** in the dual-MCP workflow. They
must not be confused — see `docs/ADVISORY_REFACTOR.md` for the full picture.

## 1. Binance Agent OS MCP — execution rail (allowlisted clients only)

Endpoint: `https://agent.binance.com/mcp/agentic`

Binance: `https://agent.binance.com/mcp/agentic`

AlphaPilot: `https://alphapilot-mcp-server.onrender.com/mcp`

Binance's hosted MCP server. **OAuth is completed inside a supported AI
client**, never inside AlphaPilot:

- Claude Code / Claude Desktop
- Cursor / VS Code
- Codex / ChatGPT
- Grok Bot

A self-built client (including an earlier AlphaPilot attempt — see
`BINANCE_AGENT_OS_REFACTOR.md`) is rejected on the consent screen. AlphaPilot
does not act as a Binance MCP OAuth client, full stop — not as a fallback,
not as an optional mode.

## 2. AlphaPilot MCP — analysis, proposals, and account-context relay

`backend/app/mcp_server.py` (Streamable HTTP) exposes AlphaPilot-owned tools.
It is **not** Binance and never places an exchange order.

### Advisory tools (public data — no Binance connection needed)

| Tool | Purpose |
|------|---------|
| `wiring_instructions` | Full dual-MCP setup checklist |
| `analyze_symbol(symbol, interval="1h")` | RSI/MACD/momentum + regime → long/short/hold bias, confidence, rationale |
| `get_earn_opportunities()` | Simple Earn flexible-product APY scan |
| `get_margin_analysis(symbol, daily_interest_rate_pct=None)` | Margin eligibility, suggested leverage, cost estimate |

### Account-context relay

| Tool | Purpose |
|------|---------|
| `submit_account_context(user_id, portfolio_value_usdt, open_exposure_usdt=0, margin_exposure_usdt=0, realized_daily_loss_pct=0)` | Relay a Binance balance you just read via Binance Agent OS MCP. Required before `build_trade_proposal`; stale after 10 minutes. |

### Proposal / execution workflow

| Tool | Purpose |
|------|---------|
| `build_trade_proposal(user_id, symbol, intent, requested_size_usdt=None, requested_leverage=None)` | Risk-validated size/leverage/stop/targets. `intent` is `long`, `short`, or `spot_hold`. |
| `list_pending_proposals(user_id=None)` | Risk-validated plans (from either the proposal builder or scheduled strategies) |
| `get_trade_plan(plan_id)` | Full structured plan |
| `get_approval_brief(plan_id)` | Human-readable brief |
| `approve_trade_plan(plan_id)` | Mark approved (no order placed) |
| `reject_trade_plan(plan_id, reason=...)` | Cancel plan |
| `execution_checklist(plan_id)` | Steps for placing the order via Binance Agent OS MCP |
| `record_fill(plan_id, order_id, fill_price, quantity)` | After the Binance-side fill → opens a Position |
| `list_open_positions(user_id=None)` | Positions AlphaPilot is monitoring |

### Panic / exit

| Tool | Purpose |
|------|---------|
| `explain_panic(position_id, question="")` | Re-runs analysis against current price; reports whether the original thesis still holds, distance to stop, recommendation |

## Dual-MCP flow

```text
User (any allowlisted AI client)
   │
   ├─► Binance Agent OS MCP ──OAuth──► Agentic sub-account (balances, orders)
   │
   └─► AlphaPilot MCP
             │
     analyze_symbol / get_earn_opportunities / get_margin_analysis
             │  (no Binance connection needed for the above)
     submit_account_context ◄── relayed from what Binance Agent OS returned
             │
     build_trade_proposal → approve_trade_plan
             │
     [order placed via Binance Agent OS MCP directly]
             │
     record_fill → Position opened, monitored by AlphaPilot
             │
     explain_panic ◄── if the human asks "should I close this?"
```

## Running AlphaPilot MCP

```bash
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=9000
DATABASE_URL=...

python -m app.mcp_server
# or the alphapilot-mcp-server Docker service (see render.yaml)
```

Add the Streamable HTTP URL to Claude Code / Cursor / etc. alongside
Binance Agent OS MCP.

## What's intentionally NOT here

- AlphaPilot completing Binance Agentic OAuth as its own client — permanently
  out of scope, not a "todo".
- A `place_order`-style tool on AlphaPilot's MCP server — that tool belongs
  to Binance Agent OS MCP, called by the allowlisted client directly.
