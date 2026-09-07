# AlphaPilot Analysis Engine

`app/market/coin_analysis.py:analyze_symbol()` combines eight categories
into one composite bias/confidence. This doc maps each category to its
module, its data source, and — critically — what happens when that source
is unavailable, because the whole point of this engine is that you always
know exactly how much of it actually ran, not just get a number.

| Category | Module | Data source | Cost |
|---|---|---|---|
| Technical | `app/market/indicators.py` | Binance public klines | Free, no key |
| Market structure | `app/market/structure.py` | Binance public klines | Free, no key |
| Volume & liquidity | `app/market/volume_profile.py` | Binance public klines | Free, no key |
| Order book | `app/market/orderbook_analysis.py` | Binance public depth | Free, no key |
| Derivatives | `app/market/derivatives.py` | Binance public futures REST | Free, no key |
| On-chain | `app/market/onchain.py` | DeFiLlama | Free, no key |
| Sentiment | `app/market/sentiment.py` | alternative.me (Fear & Greed) + CryptoPanic (news, optional) | Fear & Greed free; news needs `CRYPTOPANIC_API_KEY` (free signup) |
| Cross-market | `app/market/cross_market.py` | CoinGecko (dominance) + Binance (ETH/BTC) + Alpha Vantage (macro, optional) | Dominance/ETH-BTC free; macro needs `ALPHA_VANTAGE_API_KEY` (free signup) |

Liquidation data (from the user's requested matrix) has **no free public
API path at all** — Binance doesn't expose historical liquidations through
public REST — so `derivatives.liquidation_data` is always reported as
`"unavailable"` rather than approximated from something else. Whale-wallet
tracking and exchange net-flow are similarly always `"unavailable"` in
`onchain.whale_flow_data` — those need a paid provider (Glassnode/Nansen/
Arkham/Whale Alert) that isn't wired up in this build; the interface is
structured so one could be added later without changing anything else.

## Technical (`indicators.py`)

RSI(14), MACD(12/26/9), rate-of-change momentum, SMA/EMA 20 & 50 (with
golden/death cross detection), Bollinger Bands(20, 2σ) with squeeze/
breakout detection, and fractal/pivot-based support & resistance (a candle
is a swing high/low if it's the extremum within ±3 candles — the same
construction a chartist uses by eye, with no lookahead: only fully-confirmed
pivots are used).

## Market structure (`structure.py`)

Classical Dow Theory: a sequence of Higher-Highs + Higher-Lows (from
confirmed swing points) is an uptrend, Lower-Highs + Lower-Lows is a
downtrend, anything else is ranging. A **Break of Structure** (price taking
out the last swing in the trend's own direction) is a continuation signal; a
**Change of Character** (price breaking the *other* way) is an early
reversal warning — not yet a confirmed new trend.

## Volume & liquidity (`volume_profile.py`)

Rolling VWAP over the fetched window, and a volume profile (price binned
into 24 buckets by traded volume) giving the **Point of Control** (the
single most-traded price) and a **Value Area** (the tightest contiguous
band containing 70% of volume, built by expanding outward from the POC).
Price outside the value area is often a a low-liquidity, faster-moving zone.

## Order book (`orderbook_analysis.py`)

Live snapshot, not historical — the fastest-moving signal in the engine, so
it's weighted lowest in the composite (5%) and never blended at the same
weight as a multi-candle trend signal. Bid/ask depth imbalance, spread, and
"wall" detection (a resting order ≥5x the average size on its own side of
the book — relative to the symbol's own book, not a fixed USDT amount, so it
works the same for a thin altcoin and BTC).

## Derivatives (`derivatives.py`)

Funding rate (current + ~3-day trend), open interest, and basis
(futures mark price vs spot). Funding is scored **contrarian**: a
persistently positive rate beyond ~0.05%/8h means longs are paying a
stretched premium (crowded long, squeeze risk down); persistently negative
means the reverse. A symbol with no USDⓈ-M futures listing reports
`available: false` rather than an error — common for smaller-cap coins.

## On-chain (`onchain.py`)

Chain-level TVL (7-day change) via DeFiLlama, for the handful of base
assets mapped to a native chain in `BASE_TO_CHAIN` (ETH, SOL, BNB, AVAX,
and others). Not every symbol has a meaningful on-chain story — anything
not in that mapping reports `applicable: false` honestly rather than
guessing a chain.

## Sentiment (`sentiment.py`)

Fear & Greed Index, scored **contrarian** (extreme fear → bullish tilt,
extreme greed → bearish tilt) — a market-wide input, not symbol-specific.
News headline sentiment (bullish/bearish vote counts from CryptoPanic) is
symbol-specific but needs `CRYPTOPANIC_API_KEY`; without it, news is
skipped, not estimated.

## Cross-market (`cross_market.py`)

BTC dominance and total market cap (CoinGecko, free, no key — dominance is
returned directly by their `/global` endpoint, not computed manually).
ETH/BTC 24h performance as an alt-season/BTC-season proxy, computed
directly from Binance's own ETHBTC pair. Traditional macro (DXY) needs
`ALPHA_VANTAGE_API_KEY`; without it, macro is skipped, not guessed.

## Composite scoring (`composite_score.py`)

**This is a weighted-vote heuristic, not a trained ML model** — there is no
historical labeled dataset or training pipeline in this project. Each
category reports a score in `[-1, +1]` plus whether it had usable data.
Available categories are combined by their fixed weight (`CATEGORY_WEIGHTS`
— technical 30%, structure 20%, volume 10%, order book 5%, derivatives 10%,
on-chain 5%, sentiment 10%, cross-market 10%), with unavailable categories
excluded and the rest **renormalized** — never silently treated as neutral.
A directional call (LONG/SHORT rather than WAIT) additionally requires at
least 4 of the 8 categories to have data, covering at least 50% of the
total possible weight — same discipline as the technical-only bias fix in
`app/market/coin_analysis.py`'s data-quality gate (see conversation history:
an earlier version let a single market-wide signal masquerade as "100%
confidence" for every symbol; both the technical layer and this composite
layer now refuse to do that).

Every result includes `model_type` (literally states it's a heuristic
composite, not ML), `categories_used`, `categories_missing`, and
`coverage_pct` — always relay these, not just the bias, when explaining an
analysis to a human.

## Performance note

A single `analyze_symbol` call now makes roughly a dozen network requests
(spot ticker/klines/depth, futures premium/funding/OI, DeFiLlama, CoinGecko,
alternative.me, and optionally CryptoPanic/Alpha Vantage), run concurrently
via `asyncio.gather` in two batches (Binance-dependent first, since later
calls need the spot price; fully-independent external providers second).
There is no caching layer yet — repeated calls for the same symbol within a
short window re-fetch everything. Adding a short-TTL cache (a market-wide
input like Fear & Greed or BTC dominance doesn't need to be refetched per
symbol) is reasonable future work, not yet built.
