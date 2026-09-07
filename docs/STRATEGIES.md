# AlphaPilot Strategies

All three scheduled strategies run every `settings.scan_interval_minutes`
(default 60) — **not once a day** — against **both** the spot market and
USDⓈ-M futures perpetuals (`app/binance/market_data.py`'s `market_type`
param), via `app/jobs/daily_market_reset.py:run_market_scan` (the filename
is legacy; the function is what actually runs). Every candidate is tagged
`market_type: "spot" | "futures"` and gets a `reason` string explaining its
outcome — qualified, watching, or rejected — not just the ones that became
a proposal. Candidates older than `candidate_retention_hours` (default 6)
that never became a TradePlan are pruned automatically at the start of each
scan (`app/jobs/market_cleanup.py`), so the Opportunities tab only ever
shows recent, relevant results.

```text
Market scan (spot AND futures, every scan_interval_minutes)
  ↓
Prune candidates older than candidate_retention_hours with no TradePlan
  ↓
Market Regime Engine gate (per strategy)
  ↓
Gainer Hunter / Recovery Hunter / Hot Market Margin (below)
  ↓
Risk validation (app/risk/engine.py) against the latest reported AccountSnapshot
  ↓
TradePlan (risk-validated) or a watching/rejected MarketCandidate with a reason
  ↓
Human approves → allowlisted AI client executes via Binance Agent OS MCP directly
  ↓
record_fill / confirm-execution → AlphaPilot opens a Position and monitors it
```

The same risk-validated-proposal shape also happens **on demand**, outside
this schedule, when a user asks "what do you think about BTC/USDT" through
chat — see `app/services/trade_proposal.py` and `docs/ADVISORY_REFACTOR.md`.

## Gainer Hunter

Top qualifying 24h gainers, scored on momentum / volume / liquidity / spread.
`opportunity_score` below `RiskPolicy.min_opportunity_score` → status
`watching` with a reason citing the actual score and the bar it missed, not
just silence. Default profit ladder: +15%, +30%, +45%, +60%. Default hard
stop: -20%. Configurable via `RiskPolicy`.

## Recovery Hunter

Top qualifying 24h losers, scored on stabilization / volume / liquidity /
spread, then classified. `LOW`/`AVOID` classifications or a score below
`RiskPolicy.min_recovery_score` → status `watching` or `rejected` with a
reason. Default take profit +25%, -20% hard stop, deterministic stagnation
exit logic.

## Hot Market Margin Hunter

Scans for unusually strong momentum + volume, then checks margin
eligibility (liquidity, spread, Market Regime gate, conviction) via
`app/strategies/hot_market.margin_eligibility`. Ineligible candidates are
still recorded — status `rejected` with the specific reasons — for
visibility, not silently dropped. The same eligibility check, on demand for
one symbol, is what backs `get_margin_analysis` / the Margin tab's analyzer
(`app/margin/analysis.py`).

## Coin analysis (on demand, not scheduled)

`app/market/coin_analysis.py` — a multi-factor composite (technical,
structure, volume, order book, derivatives, on-chain, sentiment,
cross-market) → long/short/hold-spot bias with a confidence score and a
transparent coverage report, for any symbol a user asks about. Public data
only. This is what backs `analyze_symbol` (MCP tool), the Market tab's
analyzer, and the Copilot chat. See `docs/ANALYSIS_ENGINE.md` for the full
breakdown.

## Capital Optimizer / Earn scan

`app/earn/scanner.py` reads Binance Simple Earn flexible-product APY,
read-only. AlphaPilot never subscribes or redeems — Earn stays
recommendation-only, same as before.

## Plain-language explanations

Any MarketCandidate can be explained in non-technical language on demand —
`POST /api/candidates/{id}/explain` (`app/services/candidate_explainer.py`),
cached on the row after first generation. Falls back to a deterministic
templated sentence if the AI narration layer is unavailable, so the
Opportunities tab never breaks over it.

## AI role

AI reasoning (OpenRouter, `app/agent/ai_provider.py`) is downstream of
deterministic candidate generation and upstream of nothing — it explains and
narrates, never scores or overrides risk policy. `score_breakdown` and
`opportunity_score` are always plain arithmetic, checkable independent of
any AI model being up.

## Execution role

Every executable strategy ends at a risk-validated TradePlan. AlphaPilot
never executes it — an allowlisted AI client (Claude, ChatGPT, etc.) places
the order through Binance Agent OS MCP directly, then confirms the fill
back via `record_fill` (MCP) or `POST /api/trade-plans/{id}/confirm-execution`
(REST). See `docs/ADVISORY_REFACTOR.md`.
