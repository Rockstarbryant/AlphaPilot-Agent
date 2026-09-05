# AlphaPilot Binance Agent OS Refactor

This archive changes AlphaPilot from a proposal/hand-off architecture into a **direct Binance Agent OS MCP client architecture**.

## What changed

### Backend

- Replaced the old Binance MCP placeholder with a Streamable HTTP MCP client.
- Added protected-resource OAuth discovery and authorization-code + PKCE helpers.
- Added encrypted OAuth token persistence through the `BinanceConnection` model.
- Added Binance Agent OS connection, capability, ticker and account endpoints.
- Added direct `POST /api/trade-plans/{plan_id}/execute` execution.
- Added order-ID extraction and post-submission order reconciliation.
- Create AlphaPilot `Position` records only after a confirmed fill.
- Added direct exit-signal execution through the same Binance Agent OS service.
- Added Agentic account-state synchronization and frontend account-state support.
- Retained AlphaPilot's own MCP server as an optional application-data interface; it is not the Binance MCP server.

### Frontend

- Added Binance Agent OS connection UI.
- Added Agentic account-state panel.
- Added balance, USDT availability, portfolio-value-when-provided, open-position and open-order indicators.
- Added direct TradePlan execution button.
- Added Binance Agent OS status and trading-mode presentation.
- Added compact account-state view to the dashboard.

## Current direct architecture

```text
AlphaPilot market/strategy pipeline
          ↓
      AI reasoning
          ↓
  Deterministic Risk Engine
          ↓
       TradePlan
          ↓
BinanceAgentOSService
          ↓
 BinanceAgentOSClient
          ↓
 Binance Agent OS MCP
          ↓
  Agentic sub-account
          ↓
    order / fill
          ↓
 AlphaPilot Position
```

No second AI client is required to copy a proposal from AlphaPilot into Binance.

## Binance facts used by this refactor

Binance's current developer documentation lists the hosted MCP endpoint as:

`https://agent.binance.com/mcp/agentic`

It documents market data, Agentic account reads and trading scopes, plus an Agentic sub-account boundary and no withdrawal scope. Binance currently documents a confirmation boundary for non-read actions.

Official reference:

`https://developers.binance.com/en/docs/agent-native/mcp-server/agentic`

## What is NOT claimed

The code was statically compiled, but this archive was **not** able to complete a live Binance authorization, inspect the real authorized Binance tool catalog, or place a real order. The frontend dependencies could not be installed to completion in the isolated verification environment either.

Therefore:

- the integration is implementation-ready, not live-certified;
- generic tool-name/schema matching must be checked against the real `tools/list` response;
- the first real test should be read-only;
- do not use real funds until authorization, account read, tool discovery and order reconciliation have all been verified.

## Required environment variables

```text
BINANCE_MCP_ENDPOINT=https://agent.binance.com/mcp/agentic
MCP_CLIENT_NAME=AlphaPilot Agent
MCP_OAUTH_REDIRECT_URI=https://YOUR-BACKEND/api/binance/oauth/callback
MCP_OAUTH_ENCRYPTION_KEY=<Fernet key>
PUBLIC_BASE_URL=https://YOUR-BACKEND
```

Generate the encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## First debugging sequence

1. Start PostgreSQL and the backend.
2. Start the Next.js frontend.
3. Log in to AlphaPilot.
4. Open **Agent**.
5. Start Binance authorization.
6. Return to AlphaPilot after authorization.
7. Verify `/api/binance/connection/{user_id}` reports connected.
8. Verify `/api/binance/capabilities/{user_id}` returns a real tool catalog.
9. Verify `/api/binance/account/{user_id}` returns account state.
10. Verify a ticker read.
11. Only then test a very small risk-approved order.
12. Verify the returned order state and Position creation.

## Verification performed in this archive

- Python application and test source passed `python -m compileall`.
- Repository-wide source inspection was performed for backend/frontend Agent OS integration and stale architecture descriptions.
- Full `pytest` could not be collected in the isolated environment because runtime dependencies including `asyncpg`, `respx` and `mcp` were unavailable.
- Frontend `npm install` timed out in the isolated environment, so a fresh Next.js build was not claimed.
- No live Binance authorization or trade was performed.
