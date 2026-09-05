# Binance Agent OS Capability Matrix

**Reference checked:** Binance Developer Docs, Binance MCP Server, last modified September 3, 2026.

Official reference: https://developers.binance.com/en/docs/agent-native/mcp-server/agentic

| Capability | Binance documentation | AlphaPilot implementation | Verification state |
|---|---|---|---|
| Hosted MCP endpoint | `https://agent.binance.com/mcp/agentic` | Configurable default in `Settings` | Endpoint documented; live AlphaPilot session not tested here |
| Public market data | Tickers, order books, candles, funding | Existing REST scanner + Agent OS ticker adapter | Code path present; live Agent OS call not tested here |
| Agentic account balance | Account scope | `/api/binance/account/{user_id}` + frontend account-state component | Code path present; live response not tested here |
| Agentic positions | Account scope | Account-state parser + service | Code path present; live response shape must be validated |
| Spot trading | Trade scope | Generic discovered-tool order execution | Code path present; live order not tested |
| Margin trading | Trade scope | Capability available at Binance boundary; AlphaPilot margin execution remains incomplete | Not fully implemented |
| Convert | Trade scope | Binance boundary supports it; AlphaPilot has no dedicated Convert workflow | Not implemented |
| USDⓈ-M Futures | Trade scope | Binance boundary supports it; AlphaPilot's core execution is currently spot-shaped | Not implemented |
| COIN-M Futures | Trade scope | Binance boundary supports it; AlphaPilot has no dedicated workflow | Not implemented |
| Internal Agentic wallet transfers | Transfer scope | No AlphaPilot transfer workflow | Not implemented |
| External withdrawals | No withdrawal scope | No withdrawal code | Binance says unavailable |
| User confirmation | Binance says write actions are confirmed first | AlphaPilot does not bypass this | Binance-side boundary |
| Autonomous mode | Binance documentation says users can configure more autonomous trading; exact account/client behavior depends on connection policy | `TradingMode.autonomous` exists | Must be tested with real Agent OS permissions |
| MCP authorization | Binance Agent OS authenticates during first MCP connection | AlphaPilot implements protected-MCP discovery/PKCE and encrypted token persistence | Must be live-tested against the deployed Agent OS connection |
| Dynamic client registration | Only used if protected-MCP metadata advertises it | Implemented as standard MCP authorization behavior | Must be verified against live metadata; AlphaPilot must not assume Binance-specific registration |
| Order reconciliation | Binance order status tool expected | Implemented via discovered-tool adapter | Live tool name/response must be verified |

## Important interpretation

"Agent OS" is broader than one protocol. Binance's hosted MCP server currently exposes trading and market-data capabilities; other Agent OS capabilities can use other Binance surfaces. AlphaPilot's Track A scope should focus on the MCP-based market/account/execution workflow actually demonstrated.

## Security boundary

Binance documents an isolated Agentic sub-account, user-selected scopes and no withdrawal scope. Funding the Agentic sub-account is a manual Binance-side action. AlphaPilot should never imply that its backend can pull funds from the user's main account.

## Verification labels

- **Implemented:** code exists and has been statically checked.
- **Protocol-ready:** code follows the intended MCP/OAuth shape but has not completed a live Binance smoke test.
- **Live verified:** only use this label after an actual authorized Binance call has succeeded.
- **Not implemented:** do not expose as a working AlphaPilot feature.
