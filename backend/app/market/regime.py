"""
Market Regime Engine. Deterministic, not AI-driven — the regime gates which
strategies are allowed to run (see docs/STRATEGIES.md #32), so it needs to be
as auditable as the risk engine itself.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from app.binance.market_data import BinanceMarketDataClient, TickerSnapshot

REGIME_BULLISH = "BULLISH"
REGIME_NEUTRAL = "NEUTRAL"
REGIME_BEARISH = "BEARISH"
REGIME_HIGH_VOLATILITY = "HIGH_VOLATILITY"
REGIME_RISK_OFF = "RISK_OFF"
REGIME_UNKNOWN = "UNKNOWN"


@dataclass
class RegimeAssessment:
    regime: str
    btc_change_24h_pct: float
    market_breadth_pct: float  # % of USDT pairs that are up on the day
    btc_volatility_pct: float
    notes: str


async def assess_market_regime(client: BinanceMarketDataClient) -> RegimeAssessment:
    tickers = await client.get_24h_tickers()
    tradeable = await client.get_exchange_info_symbols(quote_asset="USDT")
    usdt_tickers = [t for t in tickers if t.symbol in tradeable]

    btc = next((t for t in usdt_tickers if t.symbol == "BTCUSDT"), None)
    if btc is None or not usdt_tickers:
        return RegimeAssessment(
            regime=REGIME_UNKNOWN,
            btc_change_24h_pct=0.0,
            market_breadth_pct=0.0,
            btc_volatility_pct=0.0,
            notes="Could not retrieve BTCUSDT or market universe data.",
        )

    up_count = sum(1 for t in usdt_tickers if t.price_change_pct_24h > 0)
    breadth_pct = (up_count / len(usdt_tickers)) * 100

    klines = await client.get_klines("BTCUSDT", interval="1h", limit=24)
    hourly_returns = [
        (klines[i]["close"] - klines[i - 1]["close"]) / klines[i - 1]["close"] * 100
        for i in range(1, len(klines)) if klines[i - 1]["close"]
    ]
    btc_volatility = statistics.pstdev(hourly_returns) if len(hourly_returns) > 1 else 0.0

    if btc_volatility > 6.0:
        regime = REGIME_HIGH_VOLATILITY
        notes = f"BTC hourly volatility {btc_volatility:.1f}% exceeds high-volatility threshold."
    elif btc.price_change_pct_24h < -8.0 and breadth_pct < 25:
        regime = REGIME_RISK_OFF
        notes = f"BTC down {btc.price_change_pct_24h:.1f}% with only {breadth_pct:.0f}% of pairs green."
    elif btc.price_change_pct_24h > 2.0 and breadth_pct > 60:
        regime = REGIME_BULLISH
        notes = f"BTC up {btc.price_change_pct_24h:.1f}% with {breadth_pct:.0f}% market breadth."
    elif btc.price_change_pct_24h < -2.0 and breadth_pct < 40:
        regime = REGIME_BEARISH
        notes = f"BTC down {btc.price_change_pct_24h:.1f}% with weak {breadth_pct:.0f}% breadth."
    else:
        regime = REGIME_NEUTRAL
        notes = f"BTC {btc.price_change_pct_24h:+.1f}%, breadth {breadth_pct:.0f}% — no strong signal either way."

    return RegimeAssessment(
        regime=regime,
        btc_change_24h_pct=btc.price_change_pct_24h,
        market_breadth_pct=breadth_pct,
        btc_volatility_pct=btc_volatility,
        notes=notes,
    )


# Which strategies are allowed to produce new proposals under each regime.
# Referenced by jobs, not enforced silently inside strategies, so the
# decision is visible in the audit trail.
REGIME_STRATEGY_GATES = {
    REGIME_BULLISH: {"gainer_hunter": True, "recovery_hunter": True, "hot_market_margin": True},
    REGIME_NEUTRAL: {"gainer_hunter": True, "recovery_hunter": True, "hot_market_margin": True},
    REGIME_BEARISH: {"gainer_hunter": True, "recovery_hunter": False, "hot_market_margin": False},
    REGIME_HIGH_VOLATILITY: {"gainer_hunter": False, "recovery_hunter": False, "hot_market_margin": False},
    REGIME_RISK_OFF: {"gainer_hunter": False, "recovery_hunter": False, "hot_market_margin": False},
    REGIME_UNKNOWN: {"gainer_hunter": False, "recovery_hunter": False, "hot_market_margin": False},
}
