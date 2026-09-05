> **Option A:** AlphaPilot is the policy/proposal workflow. Binance orders are placed by an allowlisted MCP client; AlphaPilot records fills via MCP `record_fill`.

# AlphaPilot Agent Architecture

## Objective

AlphaPilot should behave like an agent rather than a proposal generator:

```text
Observe → Reason → Constrain → Act → Verify → Monitor
```

The external action boundary is Binance Agent OS MCP.

## Observe

AlphaPilot can observe:

- public Binance market data through the existing REST scanner
- Binance Agent OS account state when the Account scope is authorized
- Agent OS capabilities through MCP tool discovery
- AlphaPilot candidates, TradePlans, positions and risk state

## Reason

The OpenRouter provider is used for advisory reasoning/comparison. It can explain opportunities and rank candidates, but it cannot modify deterministic risk policy.

## Constrain

Before execution AlphaPilot checks:

- TradePlan risk status
- configured trade-size limits
- allocation/exposure rules where account state is available
- slippage and liquidity constraints
- strategy-specific restrictions
- idempotency/execution state
- emergency halt/trading mode

The Risk Engine is the authority inside AlphaPilot.

## Act

`POST /api/trade-plans/{plan_id}/execute` is the direct entry point. It calls `BinanceAgentOSService.execute_trade_plan()`, which obtains an authorized `BinanceAgentOSClient` and invokes the discovered Binance order tool.

There is no requirement for a second AI client to copy or paste the TradePlan.

## Verify

AlphaPilot does not equate "tool call returned" with "trade filled".

The service extracts the Binance order ID when available and then queries order status. A Position is created only after a confirmed `FILLED` result.

A timeout or ambiguous response must be reconciled before retrying. Blind order retries are unsafe.

## Monitor

The position monitor remains deterministic and independent of the LLM. It detects:

- hard stops
- profit targets
- stagnation

Exit signals are executed through the same Binance Agent OS service when the user's configuration allows execution.

## Binance authorization boundary

Binance's current MCP documentation describes a hosted endpoint at:

`https://agent.binance.com/mcp/agentic`

It supports market data and, when authorized, Agentic account and trading operations. Binance currently documents user-selected scopes and says write actions are confirmed by the user first. See:

`https://developers.binance.com/en/docs/agent-native/mcp-server/agentic`

The codebase contains a generic OAuth protected-resource discovery + authorization-code/PKCE implementation because the hosted MCP endpoint exposes an OAuth challenge. **The exact self-built-agent authorization path has not been live-tested from this archive**, so the integration must be validated against a real Binance account before being described as production-ready.

## Trading modes

- `read_only`: never submit orders.
- `approval_required`: keep the user/authorization boundary visible; do not attempt to bypass Binance confirmation.
- `autonomous`: allow AlphaPilot to proceed when Binance permissions/policy allow it, while retaining AlphaPilot's own deterministic risk gate.

The setting does not override Binance permissions.

## Emergency stop

AlphaPilot's emergency stop prevents new AlphaPilot proposals. Binance provides its own account-level Emergency Stop for disconnecting agents and cancelling Agentic-account orders/positions. AlphaPilot does not pretend its local emergency-stop endpoint can remotely replace Binance's control.

## Known implementation limitations

1. Live MCP OAuth authorization has not been completed in this development environment.
2. The exact Binance tool names are discovered dynamically, but the adapter's heuristic name matching must be validated against the live tool catalog.
3. The current account snapshot logic conservatively extracts USDT and does not calculate a complete mark-to-market portfolio value.
4. Full test execution requires PostgreSQL and all Python test dependencies.
5. Full frontend verification requires installing Node dependencies and running the Next.js build.
