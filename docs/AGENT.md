> **Current architecture:** AlphaPilot is the analysis/policy/proposal
> workflow. It never places or closes a Binance order. An allowlisted MCP
> client (Claude, ChatGPT, etc.) does that via Binance Agent OS MCP directly,
> then confirms back to AlphaPilot. See `docs/ADVISORY_REFACTOR.md` for the
> full picture — this doc covers the agent loop specifically.

# AlphaPilot Agent Architecture

## Objective

```text
Observe → Reason → Constrain → Propose → (human/client executes externally) → Verify → Monitor
```

The external action boundary is Binance Agent OS MCP, and AlphaPilot is
never on the inside of it — see "Binance authorization boundary" below.

## Observe

- Public Binance market data (spot AND futures) via `app/binance/market_data.py`
- Binance Agent OS account state — only when an AI client reports it via
  `submit_account_context` / `POST /api/binance/account-context/{user_id}`;
  AlphaPilot never reads this itself
- AlphaPilot's own candidates, TradePlans, positions, and risk state

## Reason

`app/agent/ai_provider.py` (OpenRouter) provides advisory narration only —
explaining candidates (`app/services/candidate_explainer.py`), phrasing
Copilot replies, comparing options. It never modifies deterministic risk
policy or scoring; every number it narrates was computed before it was called.

## Constrain

Before a TradePlan is marked `risk_check_passed`, `app/risk/engine.py` checks:

- trade-size limits, allocation/exposure rules (against the latest reported
  AccountSnapshot)
- slippage and liquidity constraints
- strategy-specific restrictions
- idempotency/execution state
- emergency halt / trading mode

The Risk Engine is the sole authority inside AlphaPilot — nothing
downstream of it (AI narration, the frontend, an MCP tool) can override a
`risk_check_passed=False` plan.

## Propose (not Act)

There is no execution entry point in AlphaPilot's own API or MCP server —
by design, not by omission. `POST /api/trade-plans/{plan_id}/confirm-execution`
and the MCP tool `record_fill` are **reconciliation**, not execution: they
run *after* an allowlisted AI client has already placed the order via
Binance Agent OS MCP directly, and they take the resulting order id/fill as
input. AlphaPilot never calls a Binance order tool itself, because it
cannot — see "Binance authorization boundary."

## Verify

AlphaPilot does not equate "the human said it filled" with truth blindly,
but it also has no way to independently check Binance order status (it has
no Binance session). `confirm-execution`/`record_fill` take the order id and
fill price the client reports and open a Position from them; if you want an
independent check, have your AI client query the order status via Binance
Agent OS MCP before confirming.

## Monitor

`app/jobs/position_monitor.py` is deterministic and independent of any LLM.
It detects hard stops, profit targets, and stagnation, and raises
`ExitSignal`s — but never executes them, for the same reason above. A human
or their connected AI client executes the exit via Binance Agent OS MCP and
confirms back via `POST /api/positions/exit-signals/{id}/confirm-execution`.
For a panic question mid-trade ("should I close this?"), see
`app/services/panic_advisor.py` / `explain_panic`.

## Binance authorization boundary

`https://agent.binance.com/mcp/agentic` is Binance's hosted MCP endpoint.
Its Agentic OAuth only accepts a named allowlist of AI clients (Claude
Desktop/Code, ChatGPT, Codex, VS Code, Grok Bot) — a self-built backend is
rejected on the consent screen (error `3346001-…`). This was tried and
abandoned; see `BINANCE_AGENT_OS_REFACTOR.md` for that history. AlphaPilot
now contains **no OAuth client code at all** — it was deleted, not disabled.

## Trading modes

- `read_only`: AlphaPilot's scheduled strategies stop proposing new trades.
- `approval_required`: proposals require explicit human approval before
  `confirm-execution`/`record_fill` will accept a fill for them (default).
- `autonomous`: proposals are created without a separate approve step, but
  execution is still always external and still still requires Binance's own
  user confirmation on write actions.

This setting never lets AlphaPilot place or close an order itself in any
mode — see "Propose (not Act)" above.

## Emergency stop

AlphaPilot's emergency stop (`POST /api/agent/{user_id}/emergency-stop`)
halts new AlphaPilot proposals only. It cannot cancel a Binance order or
disconnect an MCP session — Binance's own account-level Emergency Stop is
the control for that.

## Known limitations

1. `submit_account_context` trusts whatever numbers the calling AI client
   reports — AlphaPilot has no independent way to verify them against
   Binance. Treat this like any other trust boundary in a multi-agent system.
2. Futures market data (`app/binance/market_data.py`, `market_type="futures"`)
   covers ticker/exchangeInfo/depth/klines; funding rate and open-interest
   are not yet pulled in, so futures candidates are scored on the same
   momentum/volume signals as spot, not funding-aware ones.
3. `analyze_symbol`/coin analysis is spot-only today — a futures-specific
   analysis path (e.g. incorporating funding rate) isn't implemented.
