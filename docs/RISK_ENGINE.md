# AlphaPilot Risk Engine

## Principle

The LLM is not the final risk authority.

```text
AI reasoning
    ↓
TradePlan candidate
    ↓
Deterministic Risk Engine
    ↓
PASS ─────────────→ Binance Agent OS execution
FAIL ─────────────→ no Binance order call
```

## Main controls

The current policy supports:

- maximum Spot trade notional
- maximum Spot allocation percentage
- maximum Margin trade notional
- maximum Margin allocation percentage
- maximum leverage
- maximum daily loss percentage
- maximum slippage
- minimum opportunity score
- minimum recovery score
- hot-market threshold
- strategy-specific hard stops
- trading reserve

Values are configured in `app/core/config.py` and can be represented per user by `RiskPolicy`.

## Account-relative risk

The Agent OS account endpoint can now provide authenticated account state. `sync_account_snapshot()` stores a conservative USDT snapshot with `source="agent_os_mcp"`.

The implementation intentionally does **not** pretend that a USDT balance alone equals the full USD value of BTC, ETH or other assets. Full portfolio valuation requires explicit valuation data or additional market-price joins.

## Execution gate

`BinanceAgentOSService.execute_trade_plan()` refuses a plan when:

- `risk_check_passed` is false;
- the plan is not in an executable state;
- Binance Agent OS is not connected;
- the required Binance MCP capability cannot be discovered.

The order call occurs only after those checks.

## Position exits

The Position Monitor is deterministic and does not ask the LLM whether a hard stop should trigger. It can generate:

- hard-stop signals
- profit-target signals
- stagnation signals

The execution phase then routes the signal through the Binance Agent OS service when execution is permitted.

## AI failure behavior

If OpenRouter is unavailable, deterministic scanning/risk logic should not invent an AI answer. New AI-dependent comparisons can degrade explicitly while deterministic monitoring remains available.
