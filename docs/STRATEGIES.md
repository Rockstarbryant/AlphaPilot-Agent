# AlphaPilot Strategies

## Gainer Hunter

```text
Market scan
  ↓
Top qualifying gainers
  ↓
Momentum / volume / liquidity / spread scoring
  ↓
Risk validation
  ↓
TradePlan
  ↓
Direct Binance Agent OS execution
```

Default profit ladder: +15%, +30%, +45%, +60%. Default hard stop: -20%. Values are configurable.

## Recovery Hunter

```text
Market scan
  ↓
Top qualifying losers
  ↓
Stabilization / volume / liquidity / spread scoring
  ↓
Recovery classification
  ↓
Risk validation
  ↓
TradePlan
```

Default take profit is +25%, with a -20% hard stop and deterministic stagnation logic.

## Hot Market Margin Hunter

The strategy scans the qualifying universe for unusually strong momentum and volume. Margin execution remains deliberately limited until isolated-margin execution details are verified against the live Binance Agent OS capability surface.

## Capital Optimizer

The optimizer recommends how idle capital could be allocated. Binance Simple Earn subscribe/redeem is not treated as a direct Agent OS execution capability in this project, so Earn remains recommendation-only.

## AI role

AI reasoning is downstream of deterministic candidate generation and upstream of the final risk gate. It can explain and compare; it cannot override risk policy.

## Execution role

Every executable strategy ends at a TradePlan. A risk-passed TradePlan can be sent directly by AlphaPilot to Binance Agent OS through the execution service. The normal workflow executes through AlphaPilot's Binance Agent OS MCP client; no external execution client is required.
