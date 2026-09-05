# AlphaPilot API

All URLs below are relative to the FastAPI backend.

## Authentication

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Register |
| POST | `/api/auth/login` | Login and receive JWT |

Protected endpoints use `Authorization: Bearer <JWT>`.

## Binance Agent OS

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/binance/connection/{user_id}` | Current AlphaPilot↔Binance connection state |
| POST | `/api/binance/connect/{user_id}` | Start Binance authorization and return authorization URL |
| GET | `/api/binance/oauth/callback` | OAuth callback |
| GET | `/api/binance/capabilities/{user_id}` | Discover Binance MCP tools |
| GET | `/api/binance/ticker/{user_id}/{symbol}` | Read ticker through Agent OS adapter |
| GET | `/api/binance/account/{user_id}` | Read Agentic account state |
| POST | `/api/binance/account/{user_id}/sync` | Persist a conservative account snapshot |

## Trade plans

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/trade-plans/` | List TradePlans |
| GET | `/api/trade-plans/{id}/approval-brief` | Get human-readable plan summary |
| POST | `/api/trade-plans/{id}/execute` | **Direct AlphaPilot → Binance Agent OS execution** |
| POST | `/api/trade-plans/{id}/confirm-execution` | Legacy reconciliation endpoint; not the normal direct path |

The direct `/execute` endpoint performs the AlphaPilot risk gate, calls the Binance Agent OS service, reconciles the order and creates a Position only after a confirmed fill.

## Positions

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/positions/` | List positions |
| POST | `/api/positions/monitor/run` | Run deterministic monitoring pass |
| GET | `/api/positions/exit-signals` | List exit signals |
| POST | `/api/positions/exit-signals/{id}/execute` | Direct exit through Agent OS |
| POST | `/api/positions/exit-signals/{id}/acknowledge` | Mark signal acknowledged |

## Agent controls

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/agent/{user_id}` | Read AgentConfig |
| POST | `/api/agent/{user_id}/trading-mode` | Change trading mode |
| POST | `/api/agent/{user_id}/emergency-stop` | Halt new AlphaPilot proposals |
| POST | `/api/agent/{user_id}/resume` | Resume proposals |

## Account snapshots

The legacy `/api/account/snapshot` route exists for account data supplied by another source. The preferred Track A path is the authenticated Binance Agent OS account endpoint above. Before using the legacy route in production, authorization and ownership checks should be tightened to match the protected Binance routes.

## Health

`GET /api/health` returns the application health state.

## Authentication/ownership note

The codebase contains several legacy routes created before the Agent OS refactor. During debugging, verify that every user-scoped route checks the authenticated user before exposing or mutating data. The Binance routes already perform this check; older generic routes should be audited before public deployment.
