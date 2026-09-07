# AlphaPilot Security

## Security model

Two independent control layers now, not three — see
`docs/ADVISORY_REFACTOR.md`:

1. **AlphaPilot Risk Engine** — deterministic, application-side gate on
   every proposal (`app/risk/engine.py`). AI narration is downstream of it
   and cannot alter its output.
2. **Binance Agent OS** — account permissions, Agentic sub-account
   boundary, and Binance-side confirmation of write actions, entirely
   outside AlphaPilot, mediated by whichever allowlisted AI client the user
   is running.

There is no "AlphaPilot connects to Binance" layer anymore — it was removed,
not weakened, because it never worked (Binance's allowlist rejects
self-built clients). See `BINANCE_AGENT_OS_REFACTOR.md`.

## Binance credentials

**AlphaPilot stores no Binance credential of any kind** — no API key/secret,
no OAuth token, nothing that could authenticate to Binance. There used to be
Fernet-encrypted OAuth token storage (`MCP_OAUTH_ENCRYPTION_KEY`) for a
direct-client attempt; that code and its DB table (`binance_connections`)
are deleted, not just unused. The `cryptography` package was removed from
`requirements.txt` as a result.

What AlphaPilot does store: whatever balance/exposure numbers an AI client
chooses to report via `submit_account_context` (`app/services/account_context.py`)
— plain numbers, not credentials, timestamped and treated as stale after 10
minutes.

## Binance-side protections (external to AlphaPilot)

Per Binance's own Agent OS documentation
(https://developers.binance.com/en/docs/agent-native/mcp-server/agentic):
Agentic accounts are dedicated sub-accounts, users choose scopes, there is
no withdrawal scope, transfers are restricted to wallets inside the Agentic
sub-account, and Binance confirms write actions before execution. All of
this happens between the user, their AI client, and Binance directly —
AlphaPilot is not in that path and can't weaken or bypass it.

## Application protections

- JWT authentication; a 401 (expired/invalid token) is handled globally by
  the frontend — cleared session + redirect to `/login?expired=1`, never a
  raw JSON error surfaced in a panel.
- Password hashing, parameterized SQLAlchemy queries, CORS configuration.
- Deterministic risk checks; idempotency key on TradePlans; audit events.
- No Binance secrets anywhere in the codebase, by construction (there's
  nothing to leak).
- No secrets in frontend code.

## Order safety

AlphaPilot has no order to lose track of — the account placing the order
(the allowlisted AI client) is responsible for its own retry/reconciliation
logic against Binance. On AlphaPilot's side, a Position is created only
after `confirm-execution` / `record_fill` is explicitly called with a
reported order id and fill — never merely because a proposal existed.

## Emergency stop

AlphaPilot's local emergency stop (`POST /api/agent/{user_id}/emergency-stop`)
prevents new AlphaPilot proposals only. Binance's own Emergency Stop is the
authoritative account-level mechanism for disconnecting agents and
cancelling Agentic-account orders/positions — a different system, external
to AlphaPilot.

## Known gaps to address before public deployment

1. Audit remaining user-scoped routes for ownership checks (most now use
   `get_current_user` + an explicit `current_user.id != user_id` check —
   verify any newly added route follows the same pattern).
2. Replace the development `JWT_SECRET` default before deployment, and keep
   it stable across redeploys — a regenerated secret invalidates every
   existing session at once (see `docs/DEPLOYMENT.md`'s "Known operational
   notes").
3. Configure production CORS (`FRONTEND_PUBLIC_URL`) rather than relying on
   localhost.
4. Add secret scanning to CI — this repo previously had real-looking
   secrets committed in `.env.example`; treat any repo history containing
   that file as compromised and rotate those credentials regardless of code
   changes.
5. Add rate limiting to the account-context relay and Copilot endpoints —
   both call out to external services (implicitly Binance-adjacent trust,
   and OpenRouter respectively) and are unauthenticated-adjacent surface.
6. Add CSRF protection if authentication ever moves from bearer tokens to
   cookies.
7. Add prompt-injection isolation if external text/news/sentiment sources
   are introduced into the AI narration prompts.
