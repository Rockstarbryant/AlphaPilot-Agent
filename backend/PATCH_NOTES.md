# AlphaPilot patch: Binance Agent OS CIMD + market-data auth

## Problems fixed

1. **Connect button 502**  
   `MCP authorization server did not advertise dynamic client registration.`  
   Binance Agent OS does **not** support Dynamic Client Registration. It advertises  
   `client_id_metadata_document_supported: true` (Client ID Metadata Document / CIMD).

2. **Market scan / account 500–502**  
   `Binance Agent OS authorization is missing or expired.`  
   The MCP endpoint requires a Bearer token even for market-data tools.  
   `BinanceMarketDataClient` was constructed without a connection.

## Files changed

| File | Change |
|------|--------|
| `backend/app/binance/agent_os_mcp_client.py` | CIMD-first OAuth `begin()`; discovery flag; comments |
| `backend/app/core/config.py` | `mcp_client_metadata_url` setting |
| `backend/app/main.py` | Public `/.well-known/oauth-client-metadata.json` (+ alias) |
| `backend/app/binance/market_data.py` | Accepts `BinanceConnectionData` |
| `backend/app/services/binance_agent_os.py` | `connection_data(user_id)` helper |
| `backend/app/jobs/daily_market_reset.py` | Loads user connection before market scan |
| `render.yaml` | Documents `MCP_CLIENT_METADATA_URL` |

## Required env vars (Render / backend)

```text
BINANCE_MCP_ENDPOINT=https://agent.binance.com/mcp/agentic
MCP_CLIENT_NAME=AlphaPilot Agent
PUBLIC_BASE_URL=https://alphapilot-agent.onrender.com
MCP_OAUTH_REDIRECT_URI=https://alphapilot-agent.onrender.com/api/binance/oauth/callback
MCP_OAUTH_ENCRYPTION_KEY=<Fernet key>
FRONTEND_PUBLIC_URL=https://t-agent.vercel.app
```

Optional (defaults to `{PUBLIC_BASE_URL}/.well-known/oauth-client-metadata.json`):

```text
MCP_CLIENT_METADATA_URL=https://alphapilot-agent.onrender.com/.well-known/oauth-client-metadata.json
```

Generate encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## After deploy

1. Confirm metadata is public:
   ```bash
   curl -s https://YOUR-BACKEND/.well-known/oauth-client-metadata.json
   ```
   You should see JSON with `client_id` equal to that same URL and your redirect URI.

2. In the UI: Agent → **Connect Binance Agent OS** → complete Binance consent.

3. `GET /api/binance/connection/{user_id}` → `status: connected`.

4. Retry market scan / account read.

## How CIMD works (short)

- `client_id` in the authorize URL is an **HTTPS URL**.
- That URL returns a JSON document describing AlphaPilot (`client_name`, `redirect_uris`, etc.).
- Binance fetches it; no `/register` call is made.
- Token exchange still uses PKCE (`code_verifier`) and `token_endpoint_auth_method: none`.
