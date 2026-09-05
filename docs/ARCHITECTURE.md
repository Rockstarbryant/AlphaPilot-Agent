# AlphaPilot Architecture (Option A)

## 1. Purpose

AlphaPilot is a **policy, discovery, and risk workflow** for Binance Agent OS.

- AlphaPilot finds opportunities, scores them, and enforces a deterministic Risk Engine.  
- **Execution** goes through an **allowlisted MCP client** (Claude, Cursor, ChatGPT, …) connected to Binance’s hosted MCP.  
- AlphaPilot records fills and monitors positions.

AlphaPilot is **not** required to be a Binance OAuth client. Binance currently allowlists a small set of AI clients for Agentic Account Access; self-built clients are rejected on the consent screen.

## 2. System flow

```text
 Public Binance REST          Supported MCP client
 (tickers, exchangeInfo)              │
         │                            │ OAuth
         ▼                            ▼
  AlphaPilot scanners          Binance Agent OS MCP
  Strategies + AI reason              │
         │                            │ place order
         ▼                            │
  Deterministic Risk Engine           │
         │                            │
         ▼                            │
     TradePlan (proposed)             │
         │                            │
         ▼                            │
  AlphaPilot MCP / Web UI  ◄──────────┘
  approve / reject                    │
         │                            │
         │    record_fill ◄───────────┘
         ▼
     Position + monitor
```

## 3. Layers

| Layer | Responsibility |
|--------|----------------|
| Presentation | Next.js dashboard |
| API | FastAPI (sessions, plans, risk, auth) |
| Strategies | Gainer / Recovery / Hot market |
| Risk | Hard gate — rejected plans never surface for execution |
| Market data | Public REST only |
| AlphaPilot MCP | Proposals, approve, record_fill for allowlisted clients |
| Binance MCP | Account + orders (via supported client only) |

## 4. Trust boundaries

```text
LLM (Claude / Cursor / …)
    │ may call tools
    ▼
AlphaPilot Risk Engine  ── only risk_check_passed plans listed
    │
    ▼
Human / operator approval (UI or approve_trade_plan)
    │
    ▼
Binance Agent OS  ── user confirmation on writes
    │
    ▼
Agentic sub-account
```

The LLM never receives Binance API keys. AlphaPilot never stores Binance trading OAuth tokens in the Option A path.

## 5. TradePlan lifecycle (Option A)

1. Daily (or manual) market reset → candidates → risk → `TradePlan` `proposed`.  
2. `list_pending_proposals` / UI.  
3. `approve_trade_plan` → `approved`.  
4. Supported client executes via Binance MCP.  
5. `record_fill` → `open` + `Position`.  
6. Position monitor evaluates stops / ladders (market prices via public REST).

## 6. Why not direct AlphaPilot → Binance MCP?

Binance Agent OS OAuth consent rejects unknown agents (`3346001-…`). Until self-built clients are allowlisted, the supported dual-MCP workflow is the production path.
