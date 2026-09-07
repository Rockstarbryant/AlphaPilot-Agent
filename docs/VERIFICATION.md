# Verification Status

This reflects what was actually checked during the advisory refactor (see
`docs/ADVISORY_REFACTOR.md`), not aspirational coverage.

## What was verified

- **Backend imports cleanly with real dependencies installed** — not just
  `py_compile` (syntax only): `pip install -r requirements.txt` into a venv,
  then `import app.main`, `import app.mcp_server`, and every new/changed
  module (`app.services.trade_proposal`, `app.services.panic_advisor`,
  `app.services.account_context`, `app.market.coin_analysis`,
  `app.margin.analysis`, `app.earn.scanner`, `app.api.routes.market`,
  `app.api.routes.agent_chat`, `app.jobs.daily_market_reset`,
  `app.jobs.market_cleanup`, `app.jobs.scheduler`) all succeeded.
- **Both Alembic migrations parse and import** (`9f3a7c2e1b44_advisory_refactor.py`,
  `1c8e4f2a9d67_candidate_labels_and_chat_history.py`) — not applied against
  a live database in this environment; run `alembic upgrade head` against
  your actual Postgres before deploying.
- **Frontend typechecks clean**: `npx tsc --noEmit` — zero errors, including
  after the Copilot/Opportunities/Agent page rewrites.
- **Frontend builds clean**: `npx next build` — compiles, generates all 14
  routes as static content, zero errors or warnings.
- **`BinanceMarketDataClient(market_type="futures")`** constructs with the
  correct `fapi.binance.com` base URL and futures-specific paths — verified
  by direct instantiation, not a live network call from this environment.

## What was NOT verified (needs a real deploy/account to check)

- A live Binance Agent OS OAuth flow from Claude/ChatGPT — this environment
  has no way to complete Binance's browser-based consent screen.
- A live `submit_account_context` → `build_trade_proposal` →
  Binance-side order placement → `record_fill` round trip against a real
  Agentic sub-account.
- Live Simple Earn / futures ticker responses against Binance's actual API
  (the endpoint paths and field names are implemented per Binance's public
  documentation, but not exercised against a live response in this
  environment — see `app/earn/scanner.py`'s docstring for the specific
  fallback behavior if the assumed response shape is wrong).
- The AlphaPilot MCP server actually being reachable from Claude as a
  connector — depends on your deployment (see `docs/DEPLOYMENT.md`,
  "Finding your AlphaPilot MCP URL").
- The JWT-expiry → `/login?expired=1` redirect, in a real browser session
  (verified by code review of `lib/api.ts`'s `request()`, not by clicking
  through an actual expired session in this environment).

## How to close these gaps

Run the smoke-test checklist in `docs/DEPLOYMENT.md` against your actual
deployment. Nothing in this repo should be described as "live verified"
until that checklist has actually been run once, end to end, against a real
Binance Agentic sub-account.
