# AlphaPilot Frontend

Next.js frontend for AlphaPilot's market-analysis and Binance Agent OS workflow.

## Development

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

Configure the backend URL in `.env.local`:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Important pages

- `/dashboard` — market session summary and compact Binance Agentic account state
- `/agent` — Binance Agent OS connection, account state, trading mode and direct TradePlan execution
- `/market` — scanned market candidates
- `/opportunities` — qualified opportunities
- `/positions` — open positions, exit signals and direct Agent OS exit execution
- `/risk` — risk-rejected plans and risk context
- `/margin` — margin eligibility information
- `/earn` — capital optimizer recommendations
- `/activity` — TradePlan/activity history
- `/settings` — capital/risk-related controls

## Binance Agent OS UI

The Agent page is designed around the direct AlphaPilot execution path:

```text
Connect Binance Agent OS
        ↓
Read Agentic account state
        ↓
Review TradePlan
        ↓
Risk passed
        ↓
Execute via Binance Agent OS
        ↓
Show Binance result/order state
```

The account-state component reads raw account data returned by the backend and displays only values it can identify. It does not fabricate a USD portfolio valuation from unrelated token quantities.

## Build

```bash
npm run lint
npm run build
```

A clean build requires installing the dependencies first. The refactor verification environment did not complete `npm install`, so this archive does not claim a fresh production build result.
