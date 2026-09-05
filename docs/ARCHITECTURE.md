# AlphaPilot Architecture

## 1. Purpose

AlphaPilot is a market-analysis and execution-orchestration application. Its distinctive boundary is that **AlphaPilot itself is the MCP client of Binance Agent OS**. No separate AI or execution client is required to carry a TradePlan from AlphaPilot into Binance.

## 2. System flow

```text
                        Binance Agent OS
                              MCP
                               ▲
                               │
                    authorization + MCP calls
                               │
                               │
                    ┌──────────┴──────────┐
                    │ BinanceAgentOSClient│
                    └──────────┬──────────┘
                               │
                    BinanceAgentOSService
                               │
          ┌────────────────────┼─────────────────────┐
          │                    │                     │
          ▼                    ▼                     ▼
    account_state()      market_ticker()      execute_trade_plan()
          │                                          │
          │                                          ▼
          │                                    Risk gate
          │                                          │
          │                                      TradePlan
          │                                          │
          │                                          ▼
          │                                   Binance order
          │                                          │
          │                                   order reconcile
          │                                          │
          └──────────────────────────────────────────┘
                               │
                               ▼
                        Position / audit
                               │
                               ▼
                       Position Monitor
```

## 3. Application layers

### Presentation

Next.js provides the dashboard and Agent OS controls. It calls FastAPI using the bearer JWT stored by the existing frontend auth flow.

### API

FastAPI exposes authentication, market sessions, candidates, TradePlans, Binance Agent OS, positions, risk, capital and notifications.

### Agent/orchestration

The AI provider produces analysis/reasoning. It does not own hard financial limits.

### Strategy

Gainer Hunter, Recovery Hunter, Hot Market Margin Hunter and Capital Optimizer implement deterministic business logic.

### Risk

`app/risk/engine.py` is the hard gate. A risk-rejected TradePlan cannot be sent to Binance.

### Binance integration

`app/binance/agent_os_mcp_client.py` implements the direct MCP transport/client abstraction. `app/services/binance_agent_os.py` owns connection state, authorization-token persistence, account reads, order orchestration and reconciliation.

### Persistence

PostgreSQL stores users, configuration, market sessions, candidates, TradePlans, positions, exit signals, audit events, account snapshots and Binance connection metadata.

## 4. Trust boundaries

```text
LLM reasoning
    │
    │ untrusted recommendation
    ▼
Deterministic Risk Engine
    │
    │ approved TradePlan only
    ▼
AlphaPilot execution service
    │
    │ authenticated MCP call
    ▼
Binance Agent OS
    │
    │ Binance-side permissions/confirmation
    ▼
Agentic sub-account
```

The LLM cannot directly write risk policy. Binance credentials/tokens are never supplied to the LLM prompt. Binance-side permissions remain independent of AlphaPilot's own policy.

## 5. Account state

The Agent OS Account scope is the preferred authenticated source for Agentic-account state. The frontend reads the raw structured response through the backend and extracts only fields that are actually present.

`AccountSnapshot` can persist a conservative USDT figure for portfolio-relative risk calculations. This is intentionally not treated as a full mark-to-market portfolio valuation unless Binance explicitly supplies one.

## 6. Direct execution lifecycle

1. A strategy identifies a candidate.
2. AlphaPilot scores it.
3. AI reasoning can explain/compare it.
4. Risk Engine validates hard constraints.
5. A TradePlan is created.
6. `/api/trade-plans/{id}/execute` invokes `BinanceAgentOSService`.
7. The service obtains the user's authorized MCP client.
8. The MCP tool catalog is discovered and the matching execution tool is selected.
9. Binance receives the order request and applies its own authorization/confirmation boundary.
10. AlphaPilot reconciles the order status.
11. Only a confirmed fill creates the Position.
12. Position Monitor independently evaluates exits.
13. Exit signals can be sent through the same Agent OS execution provider.

## 7. What is not the architecture

This is **not** the current intended flow:

```text
