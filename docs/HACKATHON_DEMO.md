# Demo script

**Narrative:** AlphaPilot is a Binance research advisory and risk/proposal
layer; Binance Agent OS is the execution rail; Claude/ChatGPT is the
authorized operator that bridges them.

## Prep (desktop)

1. Claude Code or Claude Desktop installed.
2. Binance MCP added and authenticated (`https://agent.binance.com/mcp/agentic`).
3. AlphaPilot backend + MCP server running; AlphaPilot MCP URL (a *separate*
   deployed service — see `docs/DEPLOYMENT.md`) added to the same client.
4. Agentic sub-account funded with a small USDT amount you can afford to test.
5. AlphaPilot user logged in.

## Demo arc (8–10 minutes)

### 1. Problem (30s)

"Binance only allowlists certain MCP clients for Agentic OAuth. AlphaPilot
doesn't fight that — it becomes the research and workflow layer on top,
and it never needs a Binance credential at all."

### 2. Pure advisory, zero Binance connection (1–2 min)

In the Copilot tab (no MCP client needed): ask "what do you think about
BTC/USDT — long, short, or buy and hold?" Show the RSI/MACD/momentum
breakdown and the plain-language bias. Ask about Binance Earn APY. This
all works with nothing connected to Binance at all.

### 3. Scheduled discovery (1–2 min)

- Show the Opportunities tab: spot AND futures candidates, hourly-refreshed,
  each with a "scanned Xm ago" and a plain-language reason — including the
  ones AlphaPilot decided *not* to trade, not just the winners.
- Click "Explain this in plain English" on one.

### 4. Dual MCP (1 min)

In Claude:

```text
Use wiring_instructions from AlphaPilot MCP.
```

Then:

```text
analyze_symbol BTCUSDT
list_pending_proposals
get_approval_brief <plan_id>
```

### 5. Sized proposal against a real balance (2–3 min)

```text
[Claude reads your Binance balance via Binance Agent OS MCP]
submit_account_context <user_id> <portfolio_value_usdt> ...
build_trade_proposal <user_id> BTCUSDT long
approve_trade_plan <plan_id>
```

Place a **small** market order via Binance MCP tools directly (Binance
confirms on its own side if prompted) — AlphaPilot never places it.

```text
record_fill <plan_id> <order_id> <fill_price> <quantity>
```

### 6. Panic button (1 min)

On the Positions tab, click "Ask AlphaPilot" on the open position and ask
"this is going against me, should I close it?" — show it re-running the
same analysis against current price rather than guessing.

### 7. Close

"Analysis and risk stay deterministic in AlphaPilot, work without any
Binance connection at all, and refresh hourly across both spot and futures.
Execution stays entirely inside Binance's allowlisted Agent OS path — that
boundary is permanent, not a limitation to demo around."

## Submission tips

- GitHub: highlight `docs/ADVISORY_REFACTOR.md`, `docs/MCP_SERVER.md`,
  `backend/app/mcp_server.py`, `backend/app/market/coin_analysis.py`,
  `backend/app/binance/market_data.py`.
- Video: show the Copilot answering without any Binance connection, then
  the dual-MCP flow, then one tiny live fill.
- Do **not** claim AlphaPilot completes Binance Agentic OAuth as its own
  client — it doesn't, and the code that once tried to has been deleted.
