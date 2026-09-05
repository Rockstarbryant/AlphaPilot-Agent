# MCP Architecture

AlphaPilot contains **two different MCP roles**. Keeping them separate is essential.

## 1. Binance MCP — external execution service

Endpoint:

`https://agent.binance.com/mcp/agentic`

This is Binance's hosted MCP server. AlphaPilot acts as a client to it through:

`backend/app/binance/agent_os_mcp_client.py`

and:

`backend/app/services/binance_agent_os.py`

It is used for:

- account state
- market data where needed
- order placement
- order status
- cancellation where supported

## 2. AlphaPilot MCP — optional application interface

`backend/app/mcp_server.py` exposes AlphaPilot-owned data such as:

- pending risk-validated proposals
- approval briefs
- Binance connection state
- AlphaPilot positions

This server is **not** Binance's execution server.

An external MCP client may connect to AlphaPilot's application-data MCP server if desired. This is optional and is separate from AlphaPilot's direct Binance execution path.

## Direct execution path

```text
AlphaPilot API/UI
      ↓
BinanceAgentOSService
      ↓
BinanceAgentOSClient
      ↓
MCP tools/call
      ↓
Binance Agent OS
      ↓
Agentic account
```

## Tool discovery

AlphaPilot calls `tools/list` and stores the returned catalog in the client instance. Execution methods resolve a compatible tool from the discovered catalog and build arguments from its declared JSON schema.

This is deliberately safer than assuming a particular third-party tool name or request shape.

## Important limitation

The code is designed around the hosted Binance MCP protocol, but the live Binance-specific tool catalog and authorization behavior have not been executed from this development environment. The first debugging milestone is therefore a real connection followed by `tools/list` and one read-only account/market call.

## Recommended debugging sequence

1. Connect Agent OS.
2. Call `/api/binance/connection/{user_id}`.
3. Call `/api/binance/capabilities/{user_id}`.
4. Confirm the returned tool names/schemas.
5. Call `/api/binance/account/{user_id}`.
6. Only after the above works, test a small risk-approved order.
