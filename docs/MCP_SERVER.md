# MCP Architecture (Option A)

AlphaPilot uses **two different MCP roles**. They must not be confused.

## 1. Binance MCP — execution rail (allowlisted clients only)

Endpoint: `https://agent.binance.com/mcp/agentic`

Binance’s hosted MCP server. **OAuth is completed inside a supported AI client**, not inside AlphaPilot:

- Claude Code / Claude Desktop  
- Cursor / VS Code  
- Codex / ChatGPT  
- Grok Bot  

Self-built MCP clients (including AlphaPilot’s own OAuth attempt) currently receive:

> The AI Agent you are using is not currently supported. `(3346001-…)`

So AlphaPilot **does not** act as a Binance MCP OAuth client for trading.

## 2. AlphaPilot MCP — policy & proposal workflow

`backend/app/mcp_server.py` (Streamable HTTP) exposes AlphaPilot-owned data and workflow tools:

| Tool | Purpose |
|------|---------|
| `wiring_instructions` | How to connect dual MCP |
| `list_pending_proposals` | Risk-validated plans |
| `get_trade_plan` | Structured plan |
| `get_approval_brief` | Human-readable brief |
| `approve_trade_plan` | Mark approved (no order) |
| `reject_trade_plan` | Cancel plan |
| `execution_checklist` | Steps for Binance-side order |
| `record_fill` | After Binance fill → open Position |
| `list_open_positions` | Monitored positions |

This server is **not** Binance and never places exchange orders.

## Option A dual-MCP flow

```text
User (desktop)
   │
   ├─► Supported client ──OAuth──► Binance Agent OS MCP ──► Agentic sub-account
   │         │                         (orders, account)
   │         │
   │         └──────────────────► AlphaPilot MCP
   │                                   │
   │                          proposals / approve / record_fill
   │                                   │
   └──────────────────────────► AlphaPilot Web UI / REST
                                      │
                               market scan (public REST)
                               risk engine → TradePlan
```

1. Market scan + strategies + risk run in AlphaPilot (public REST).  
2. Operator reviews plans in UI or via AlphaPilot MCP.  
3. `approve_trade_plan`.  
4. Supported client places order on **Binance** MCP.  
5. `record_fill` so AlphaPilot monitors the position.

## Running AlphaPilot MCP

```bash
# env
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=9000
DATABASE_URL=...

python -m app.mcp_server
# or Docker service alphapilot-mcp-server (see render.yaml)
```

Add the Streamable HTTP URL to Claude Code / Cursor alongside Binance MCP.

## What was removed from the “happy path”

- AlphaPilot completing Binance Agentic OAuth as its own client  
- Market data via Agent OS MCP without allowlisted OAuth  
- Direct `execute_trade_plan` → Binance MCP as the only path  

Legacy `BinanceAgentOSService` code may still exist for experiments; **Option A production path does not depend on it.**
