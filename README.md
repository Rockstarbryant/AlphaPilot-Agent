# AlphaPilot

**Find Opportunities. Control Risk. Optimize Capital.**

AlphaPilot is an AI-assisted market operations agent for the **Binance Agent OS Mini Hackathon — Track A**.

## Architecture: Option A (policy on top of allowed MCP clients)

Binance currently allowlists a small set of MCP clients for Agentic OAuth (Claude Code, Cursor, ChatGPT, Codex, VS Code, Grok Bot). Self-built clients are blocked on the consent screen.

**AlphaPilot therefore:**

1. Scans the market with **public Binance REST** (no Agent OS OAuth).  
2. Runs strategies + deterministic **Risk Engine** → `TradePlan`.  
3. Exposes plans via **Web UI** and **AlphaPilot MCP**.  
4. Lets an **allowlisted client** place orders on **Binance Agent OS MCP**.  
5. Accepts **`record_fill`** so positions are monitored inside AlphaPilot.

```text
Public REST → Strategies → Risk → TradePlan
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
             AlphaPilot MCP / UI              Supported client
             approve / record_fill                 │
                    ▲                               ▼
                    └──────── fill ──────── Binance Agent OS MCP
```

## Dual-MCP wiring (desktop)

1. Add Binance MCP: `https://agent.binance.com/mcp/agentic` → authenticate.  
2. Add AlphaPilot MCP (your Streamable HTTP URL, port `9000` by default).  
3. Call `wiring_instructions` on AlphaPilot MCP for the full checklist.  
4. Typical loop: `list_pending_proposals` → `get_approval_brief` → `approve_trade_plan` → Binance place order → `record_fill`.

## Components

### Backend

- FastAPI + PostgreSQL + Alembic + JWT  
- Deterministic strategies and risk engine  
- Public REST market data  
- Optional AlphaPilot MCP server (workflow tools)  
- Scheduler for daily market reset / position monitor  

### Frontend

Next.js: Dashboard, Agent, Opportunities, Positions, Risk, etc.

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

### AlphaPilot MCP (optional but required for agent execution path)

```bash
cd backend
MCP_SERVER_HOST=0.0.0.0 MCP_SERVER_PORT=9000 python -m app.mcp_server
```

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
BINANCE_PUBLIC_REST_BASE=https://api.binance.com
PUBLIC_BASE_URL=https://your-backend
FRONTEND_PUBLIC_URL=https://your-frontend
# MCP server
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=9000
```

Binance Agent OS **client** OAuth vars are not required for Option A market scans or the dual-MCP execution path.

## Documentation

| Doc | Content |
|-----|---------|
| `docs/ARCHITECTURE.md` | Option A system design |
| `docs/MCP_SERVER.md` | Dual MCP roles and tools |
| `docs/HACKATHON_DEMO.md` | Track A demo script |
| `docs/RISK_ENGINE.md` | Hard risk rules |
| `docs/STRATEGIES.md` | Strategy behavior |
| `docs/API.md` | REST API |
| `docs/DEPLOYMENT.md` | Deploy notes |

## Honest status

- Market discovery and risk-validated proposals: designed for public REST.  
- Live Binance order placement: via allowlisted MCP client + user confirmation.  
- AlphaPilot-as-Binance-OAuth-client: **not** the supported path until Binance allowlists self-built agents.
