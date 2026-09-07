# Implementation Report

This repo has gone through two major pivots, both driven by the same fact:
**Binance's Agent OS allowlist rejects self-built AI clients.**

1. Original attempt: AlphaPilot as a direct Binance Agent OS OAuth client.
   Abandoned — rejected on Binance's consent screen. See
   `BINANCE_AGENT_OS_REFACTOR.md`.
2. "Option A": AlphaPilot as a proposal-only workflow, execution via an
   allowlisted AI client. Correct shape, but originally missing real
   technical analysis, Earn/margin scanning, an account-context relay, and
   a panic-question path.
3. **Current state — the advisory refactor** (`docs/ADVISORY_REFACTOR.md`):
   AlphaPilot is a Binance research and trading advisory. It analyzes
   markets (RSI/MACD/momentum, both spot and futures, hourly), scans Earn
   and margin opportunities, builds risk-validated proposals against a
   relayed account balance, explains panic questions about open positions,
   and offers a standalone OpenRouter-backed chat (Copilot) for users
   without an MCP client set up. It still never executes anything itself.

## What's implemented and checked

See `docs/VERIFICATION.md` for the specific, current list of what was
actually verified (import checks, typecheck, build) versus what still needs
a live deploy/Binance account to confirm.

## What's explicitly out of scope, permanently

- AlphaPilot completing Binance Agentic OAuth as its own client.
- AlphaPilot placing or canceling a Binance order of any kind.
- AlphaPilot storing a Binance API key, secret, or OAuth token.

These aren't gaps on a roadmap — see `docs/ADVISORY_REFACTOR.md` for why
they're the permanent shape of this integration.

## Honest known gaps

- Futures analysis doesn't yet incorporate funding rate or open interest —
  futures candidates are scored on the same signals as spot.
- `analyze_symbol` (ad-hoc coin analysis) is spot-only; there's no
  futures-specific analysis endpoint yet, only futures *scanning* for the
  scheduled strategies.
- The Simple Earn scanner's exact response-parsing was written against
  Binance's documented shape, not a live response — see
  `app/earn/scanner.py`'s docstring for its fallback behavior if that
  assumption is wrong.
