# AlphaPilot Risk Engine

## Principle

The LLM is not the final risk authority.

```text
AI reasoning
    ↓
TradePlan candidate (scheduled scan OR chat-driven build_trade_proposal)
    ↓
Deterministic Risk Engine
    ↓
PASS ─────────────→ risk_check_passed=True → human approves → an allowlisted
                     AI client executes via Binance Agent OS MCP directly
FAIL ─────────────→ risk_check_passed=False → no proposal is ever executable,
                     by anyone, through any path
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

AlphaPilot cannot read Binance account state itself (see
`docs/ADVISORY_REFACTOR.md`) — `app/services/account_context.py` stores
whatever an AI client reports after reading Binance Agent OS, with
`source="mcp_client_reported"`, timestamped. `build_trade_proposal` and the
scheduled scan both refuse to size a trade against a snapshot older than 10
minutes (`MAX_CONTEXT_AGE`) rather than using stale numbers. This is
intentionally conservative: no reported snapshot means allocation-%
checks fail closed (block the trade), never pass on an assumed balance.

## Execution gate

There is no execution call inside AlphaPilot to gate — that's the point.
`risk_check_passed` on a `TradePlan` is the only thing that determines
whether `POST /api/trade-plans/{id}/confirm-execution` / the MCP tool
`record_fill` will accept a reported fill for it; a risk-rejected plan
can't be confirmed into a Position regardless of what actually happened on
Binance's side.

## Position exits

The Position Monitor (`app/jobs/position_monitor.py`) is deterministic and
does not ask the LLM whether a hard stop should trigger. It generates
hard-stop, profit-target, and stagnation signals — and stops there. A human
or their connected AI client executes the exit via Binance Agent OS MCP
directly and confirms back via
`POST /api/positions/exit-signals/{id}/confirm-execution`. For a mid-trade
panic question, `app/services/panic_advisor.py` re-runs the same
deterministic analysis against current price — it advises, never acts.

## AI failure behavior

If OpenRouter is unavailable, deterministic scanning/risk logic should not invent an AI answer. New AI-dependent comparisons can degrade explicitly while deterministic monitoring remains available.
