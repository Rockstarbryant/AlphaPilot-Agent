# Binance Agent OS Capability Matrix

Official reference: https://developers.binance.com/en/docs/agent-native/mcp-server/agentic

AlphaPilot's relationship to each Binance capability now falls into exactly
one of three buckets — see `docs/ADVISORY_REFACTOR.md`:

- **AlphaPilot implements this directly**, using Binance's *public,
  unauthenticated* REST API — no Agent OS connection needed at all.
- **AlphaPilot never implements this** — it's authenticated/write territory
  that only exists on the far side of Binance Agent OS MCP, reachable only
  by an allowlisted AI client, never by AlphaPilot's backend. This is a
  permanent boundary, not a gap to close.
- **Relayed** — AlphaPilot doesn't call Binance for it, but can *use* a
  value an AI client reports after reading it from Binance Agent OS.

| Capability | Bucket | AlphaPilot code | Notes |
|---|---|---|---|
| Spot public market data (ticker/exchangeInfo/depth/klines) | Implements directly | `app/binance/market_data.py` (`market_type="spot"`) | Powers scanning, `analyze_symbol`, regime detection |
| USDⓈ-M Futures public market data | Implements directly | `app/binance/market_data.py` (`market_type="futures"`) | Same client, `fapi.binance.com` host; scheduled strategies now scan both |
| Simple Earn flexible-product APY | Implements directly (read-only) | `app/earn/scanner.py` | Never subscribes/redeems — recommendation only |
| Margin eligibility / leverage / cost estimate | Implements directly (analysis, not execution) | `app/margin/analysis.py` | Uses public data + `RiskPolicy` limits; doesn't place a margin trade |
| Agentic account balance/positions | Relayed | `app/services/account_context.py` | Only via `submit_account_context`, reported by an AI client that read it from Binance Agent OS |
| Spot trading (order placement) | Never implemented in AlphaPilot | — | Allowlisted AI client → Binance Agent OS MCP directly; AlphaPilot only receives the resulting fill via `record_fill`/`confirm-execution` |
| Margin trading (order placement) | Never implemented in AlphaPilot | — | Same as above |
| USDⓈ-M / COIN-M Futures trading (order placement) | Never implemented in AlphaPilot | — | Same as above |
| Convert | Never implemented in AlphaPilot | — | No AlphaPilot workflow at all |
| Internal Agentic wallet transfers | Never implemented in AlphaPilot | — | No AlphaPilot workflow |
| External withdrawals | Not possible via Agent OS at all | — | Binance documents no withdrawal scope, full stop |
| User confirmation on writes | External, Binance-side | — | AlphaPilot has no write path to bypass this on |
| MCP authorization / OAuth | AlphaPilot has none | — | Deleted, not disabled — Binance's allowlist rejects self-built clients; see `BINANCE_AGENT_OS_REFACTOR.md` |
| Order reconciliation | Relayed | `confirm-execution` / `record_fill` | Takes the order id/fill an AI client reports; AlphaPilot doesn't independently query Binance order status |

## Funding rate / open interest (futures)

Not yet pulled into `app/binance/market_data.py` — futures candidates are
currently scored on the same momentum/volume signals as spot, not a
funding-aware model. Flagged in `docs/AGENT.md`'s known limitations.

## Security boundary

Binance documents an isolated Agentic sub-account, user-selected scopes,
and no withdrawal scope. Funding the Agentic sub-account is a manual
Binance-side action, entirely outside AlphaPilot. AlphaPilot's backend
cannot move funds — it has no code path that could, by design.

## Verification labels

- **Implemented and verified:** code exists, imports/compiles, and its
  logic is exercised by this repo's own tests or has been manually run
  against live public Binance endpoints during development.
- **Relayed:** correct by construction (it's just storing a number), but
  its *accuracy* depends entirely on what the reporting AI client actually
  read from Binance — not independently verifiable by AlphaPilot.
- **Never implemented:** not a roadmap item: AlphaPilot deliberately has no
  code path here, and none should be added without revisiting the
  architecture decision in `docs/ADVISORY_REFACTOR.md`.
