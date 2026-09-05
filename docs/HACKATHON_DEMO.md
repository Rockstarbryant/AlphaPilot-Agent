# Hackathon demo script — Track A (Option A)

**Narrative:** AlphaPilot is the risk and proposal layer; Binance Agent OS is the execution rail; Claude/Cursor is the authorized operator.

## Prep (desktop)

1. Claude Code or Cursor installed.
2. Binance MCP added and authenticated (`https://agent.binance.com/mcp/agentic`).
3. AlphaPilot backend + MCP server running; AlphaPilot MCP URL added to the same client.
4. Agentic sub-account funded with a small USDT amount you can afford to test.
5. AlphaPilot user logged in; at least one market scan completed (`POST /api/sessions/run`).

## Demo arc (5–8 minutes)

### 1. Problem (30s)

"Binance only allowlists certain MCP clients for Agentic OAuth. AlphaPilot doesn't fight that — it becomes the workflow on top."

### 2. Discovery (1–2 min)

- Show AlphaPilot Opportunities / session after a scan.
- Point out regime + scores + **risk_check_passed**.
- Rejected ideas never appear on the execution list.

### 3. Dual MCP (1 min)

In the client:

```text
Use wiring_instructions from AlphaPilot MCP.
```

Then:

```text
list_pending_proposals
get_approval_brief <plan_id>
```

### 4. Approve + execute (2–3 min)

```text
approve_trade_plan <plan_id>
execution_checklist <plan_id>
```

Place a **small** market order via Binance MCP tools (user confirms on Binance if prompted).

```text
record_fill <plan_id> <order_id> <fill_price> <quantity>
```

### 5. Monitor (1 min)

- AlphaPilot Positions page shows the open position.
- Explain stops / profit ladder still enforced by AlphaPilot's monitor using public prices.

### 6. Close

"Strategy and risk stay deterministic in AlphaPilot. Execution stays inside Binance's allowlisted Agent OS path. That's Option A."

## Submission tips

- GitHub: highlight `docs/ARCHITECTURE.md`, `docs/MCP_SERVER.md`, `backend/app/mcp_server.py`, `backend/app/binance/market_data.py`.
- Video: show dual MCP tool list + one paper or tiny live fill.
- Do **not** claim AlphaPilot completes Binance Agentic OAuth as its own client.
