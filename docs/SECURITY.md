# AlphaPilot Security

## Security model

The system has three independent control layers:

1. **LLM reasoning** — can propose/explain; cannot define hard risk policy.
2. **AlphaPilot Risk Engine** — deterministic application-side gate.
3. **Binance Agent OS** — account permissions, Agentic sub-account boundary and Binance-side authorization/confirmation.

A trade is allowed only when all three boundaries permit it.

## Binance credentials

AlphaPilot does not use Binance API-key/secret HMAC signing for the Agent OS path.

The direct client is designed around the hosted Binance MCP authorization flow. OAuth access/refresh material, when obtained, is encrypted with a Fernet key before database persistence.

Environment variable:

`MCP_OAUTH_ENCRYPTION_KEY`

Generate it with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never commit the key.

## Important verification limitation

The repository's OAuth implementation is standards-oriented, but a real Binance authorization has not been completed in this isolated environment. Therefore the security posture of the **implemented code** and the security guarantees of the **live Binance connection** must be distinguished until the first live smoke test succeeds.

## Binance-side protections

Binance's current Agent OS documentation states:

- Agentic accounts are dedicated sub-accounts.
- Users choose scopes.
- Account scope can expose Agentic balances/positions.
- Trade scope covers supported exchange products.
- There is no withdrawal scope.
- Transfers are restricted to wallets inside the Agentic sub-account.
- Binance currently confirms write actions before execution.

Reference: https://developers.binance.com/en/docs/agent-native/mcp-server/agentic

## Application protections

- JWT authentication.
- Password hashing.
- Parameterized SQLAlchemy queries.
- CORS configuration.
- Deterministic risk checks.
- Idempotency key on TradePlans.
- Order-status reconciliation.
- Audit events.
- Encrypted OAuth token persistence.
- No secrets in frontend code.

## Order safety

A network timeout is not treated as proof that an order failed. The execution service should reconcile order status before any retry.

A Position is not created merely because an order request was issued. It requires a confirmed fill.

## Emergency stop

AlphaPilot's local emergency stop prevents new AlphaPilot proposals. Binance's own Emergency Stop is the authoritative account-level mechanism for disconnecting agents and cancelling Agentic-account orders/positions.

## Known security gaps to address before public deployment

1. Audit all legacy user-scoped routes for ownership checks.
2. Replace the development JWT default before deployment.
3. Configure production CORS rather than relying on localhost.
4. Add secret scanning to CI.
5. Add rate limiting to sensitive Agent OS endpoints.
6. Add CSRF protection if authentication ever moves from bearer tokens to cookies.
7. Add prompt-injection isolation if external text/news/sentiment sources are introduced.
8. Perform a live MCP OAuth and least-privilege scope test.
