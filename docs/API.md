# AlphaPilot API

All URLs below are relative to the FastAPI backend (`NEXT_PUBLIC_API_URL`).
This is the REST surface for the frontend; the MCP tool surface for AI
clients is documented separately in `docs/MCP_SERVER.md` — they cover
mostly the same operations, just two different transports for two
different callers. See `docs/ADVISORY_REFACTOR.md` for the architecture.

## Authentication

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Register, receive JWT |
| POST | `/api/auth/login` | Log in, receive JWT |
| GET | `/api/auth/me` | Current user |

Protected endpoints use `Authorization: Bearer <JWT>`. An expired/invalid
token gets a `401`; the frontend's `request()` helper (`lib/api.ts`) catches
this globally, clears the stored session, and redirects to
`/login?expired=1` — no route needs to handle this itself.

## Market analysis, Earn, margin (public data — no Binance connection needed)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/market/analyze/{symbol}?interval=1h` | RSI/MACD/momentum + regime → bias/confidence |
| GET | `/api/market/earn` | Simple Earn flexible-product APY scan |
| GET | `/api/market/margin/{symbol}` | Margin eligibility + suggested leverage/cost |
| GET | `/api/market/panic/{position_id}?question=...` | "Should I close this?" explainer |
| POST | `/api/market/proposal/{user_id}` | Build a risk-validated trade proposal (needs a fresh account-context report) |

## Account-context relay (replaces the old Binance OAuth connect flow)

AlphaPilot never authenticates to Binance itself — see
`docs/ADVISORY_REFACTOR.md`. These store whatever numbers an AI client
already read from Binance Agent OS.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/binance/account-context/{user_id}` | Report a balance/exposure snapshot |
| GET | `/api/binance/account-context/{user_id}` | Read back the most recently reported snapshot |

## Trade plans

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/trade-plans/` | List TradePlans (`?status=`) |
| GET | `/api/trade-plans/{id}/approval-brief` | Human-readable plan summary |
| POST | `/api/trade-plans/{id}/confirm-execution` | **The only execution-side endpoint.** Call after the order was placed via Binance Agent OS MCP directly, with the resulting order id/fill — opens a Position and starts monitoring it. |

There is no `/execute` endpoint — AlphaPilot's backend never places a
Binance order.

## Positions

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/positions/` | List positions |
| POST | `/api/positions/monitor/run` | Manually trigger a monitoring pass (also runs automatically every 60s via the scheduler) |
| GET | `/api/positions/exit-signals?acknowledged=` | List detected exit signals |
| POST | `/api/positions/exit-signals/{id}/acknowledge` | Mark a signal acknowledged (not the same as executed) |
| POST | `/api/positions/exit-signals/{id}/confirm-execution` | After the exit was placed via Binance Agent OS MCP directly — updates the Position |

## Market candidates ("Opportunities")

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/candidates/?market_type=&status=&strategy=&session_id=` | List candidates from the last `candidate_retention_hours` (default 6) |
| POST | `/api/candidates/{id}/explain` | Plain-language explanation for non-technical users (cached after first call) |

## Market sessions / scans

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions/run?user_id=` | Manually trigger a market scan (spot + futures, all strategies) — also runs automatically every `scan_interval_minutes` |
| GET | `/api/sessions/` | List scan sessions |

## Standalone Copilot chat

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/agent-chat/status` | Whether AI narration (OpenRouter) is actually configured |
| GET | `/api/agent-chat/{user_id}/history` | Persisted chat history |
| POST | `/api/agent-chat/{user_id}/message` | Send a message; response includes `ai_narration_used` so the UI can be honest about whether it's a real AI-phrased answer or a deterministic fallback |

## Agent controls

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/agent/{user_id}` | Read AgentConfig |
| POST | `/api/agent/{user_id}/trading-mode` | `read_only` \| `approval_required` \| `autonomous` — governs whether scheduled strategies keep proposing; never affects execution, which is always external |
| POST | `/api/agent/{user_id}/emergency-stop` | Halt new proposals |
| POST | `/api/agent/{user_id}/resume` | Resume proposals |

## Account snapshots (risk-engine input, distinct from the Binance relay above)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/account/snapshot` | Record a portfolio snapshot for risk checks |
| GET | `/api/account/snapshot/{user_id}/latest` | Latest snapshot |

## Capital optimizer

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/capital/evaluate` | Idle-capital allocation recommendation |

## Notifications

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/notifications/{user_id}?unread_only=` | List notifications |
| POST | `/api/notifications/{id}/read` | Mark one read |
| POST | `/api/notifications/{user_id}/read-all` | Mark all read |

## Health

`GET /api/health` — always unauthenticated, used by the frontend's Agent
page for a live backend-reachability indicator.
