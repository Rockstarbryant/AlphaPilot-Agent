# Binance Agent OS Track A Demo

## Demo objective

Show a judge that AlphaPilot is an agent that can:

1. observe Binance market/account state;
2. reason about an opportunity;
3. enforce deterministic risk controls;
4. call Binance Agent OS MCP itself;
5. obtain the resulting order/fill state;
6. create and monitor the resulting Position.

## The key sentence

> **"AlphaPilot does not generate an order for another AI client to execute. AlphaPilot is the MCP client that calls Binance Agent OS itself."**

## Recommended live flow

### 1. Open Agent

Show:

- Binance Agent OS connection status
- Agentic account state
- USDT available
- assets
- open positions/orders
- trading mode

### 2. Show market opportunity

Run a scan and open a risk-passed candidate.

### 3. Explain the decision

Show AI reasoning alongside the deterministic strategy score. Emphasize that the AI does not control hard limits.

### 4. Show risk gate

Demonstrate:

```text
Candidate
  ↓
AI reasoning
  ↓
Risk Engine ✓
  ↓
TradePlan
```

### 5. Execute directly

Click:

**Execute via Binance Agent OS**

Do not switch to a separate execution client. AlphaPilot is the MCP client and must drive the Binance Agent OS workflow itself.

### 6. Binance boundary

If Binance asks for confirmation under the current Agent OS configuration, complete that Binance-side confirmation. Do not attempt to bypass it.

### 7. Verify

Show:

- Binance order ID
- submitted/filled state
- actual fill price/quantity where returned
- newly created AlphaPilot Position

### 8. Monitor

Show the Position Monitor evaluating the position independently of the LLM.

## What judges should see

```text
              ALPHAPILOT
                   │
          Market observation
                   │
             AI reasoning
                   │
           Risk Engine ✓
                   │
              TradePlan
                   │
          DIRECT MCP CALL
                   │
                   ▼
          BINANCE AGENT OS
                   │
                Binance
                   │
             Order / Fill
                   │
                   ▼
              ALPHAPILOT
                   │
             Position
                   │
             Monitoring
```

## Do not demonstrate

- copying a TradePlan into a separate execution client;
- manually typing a Binance order that AlphaPilot did not request;
- manually entering an order ID back into AlphaPilot as the primary flow;
- claiming a trade is filled when only a request was submitted;
- claiming full portfolio valuation when only raw balances are available.

## Backup demo

If Binance authorization fails during the live demo, demonstrate the complete deterministic pipeline and the Binance connection/capability diagnostics rather than faking execution.
