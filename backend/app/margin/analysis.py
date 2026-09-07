"""
Spot margin trading analysis for a specific symbol — complements
app/strategies/hot_market.py's scan-the-whole-market margin_eligibility()
with an on-demand, single-symbol version for chat-driven questions like
"should I margin trade SOL/USDT?".

Binance's live cross/isolated margin interest rate is an authenticated,
account-scoped read (rate tiers can differ per VIP level and per isolated
pair), so — like app/services/account_context.py — AlphaPilot does not try
to fetch it directly. Callers running through an AI client that already has
Binance Agent OS connected can pass a `daily_interest_rate_pct` supplied by
that client; without one, this module falls back to a clearly-labeled
conservative estimate and says so, rather than presenting a guess as fact.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.binance.market_data import BinanceMarketDataClient
from app.core.config import get_settings
from app.market.coin_analysis import analyze_symbol
from app.market.regime import REGIME_HIGH_VOLATILITY, REGIME_RISK_OFF, REGIME_UNKNOWN

settings = get_settings()

# Binance's general unsecured margin daily interest rate has hovered in this
# band for major pairs historically. This is a fallback estimate ONLY, used
# purely for a rough cost illustration — never treated as a live rate.
FALLBACK_DAILY_INTEREST_RATE_PCT = 0.02


@dataclass
class MarginAnalysis:
    symbol: str
    eligible: bool
    reasons: list[str]
    bias: str
    confidence: float
    suggested_leverage: float
    max_leverage_allowed: float
    daily_interest_rate_pct: float
    interest_rate_is_estimate: bool
    est_daily_cost_pct_of_position: float
    notes: str
    data_quality: str


async def analyze_margin_symbol(
    symbol: str, *, daily_interest_rate_pct: float | None = None
) -> MarginAnalysis:
    symbol = symbol.upper().replace("/", "")
    analysis = await analyze_symbol(symbol)

    client = BinanceMarketDataClient()
    try:
        spread_bps = await client.get_spread_bps(symbol)
        tickers = await client.get_24h_tickers()
    finally:
        await client.close()

    ticker = next((t for t in tickers if t.symbol == symbol), None)
    quote_volume = ticker.quote_volume_24h if ticker else 0.0

    reasons: list[str] = []
    eligible = True

    if analysis.data_quality == "insufficient":
        eligible = False
        reasons.append(
            f"AlphaPilot couldn't get enough live price history for {symbol} to analyze it right now "
            "(a market-data gap, not a real signal) — try again shortly rather than trusting this result."
        )
    if quote_volume < settings.min_quote_volume_24h_usdt * 3:
        eligible = False
        reasons.append("24h volume is below the 3x-of-spot-minimum liquidity floor margin requires.")
    if spread_bps is not None and spread_bps > settings.max_spread_bps * 0.5:
        eligible = False
        reasons.append(f"Spread {spread_bps:.1f}bps exceeds margin's stricter tolerance.")
    if analysis.market_regime in (REGIME_RISK_OFF, REGIME_HIGH_VOLATILITY, REGIME_UNKNOWN):
        eligible = False
        reasons.append(f"Market regime '{analysis.market_regime}' disables new margin trades.")
    if analysis.bias == "WAIT" and analysis.data_quality != "insufficient":
        eligible = False
        reasons.append("No directional conviction from technical analysis — not worth paying borrow interest for.")

    if eligible:
        reasons.append("Passed liquidity, spread, regime, and directional-conviction checks for margin.")

    # Confidence scales leverage within the account's configured ceiling —
    # never above it, and halved as a conservative default even at max
    # confidence, since leverage should be earned by track record, not
    # granted by a single analysis call.
    suggested_leverage = 1.0
    if eligible:
        suggested_leverage = round(
            min(settings.max_leverage, 1 + (settings.max_leverage - 1) * (analysis.confidence / 100) * 0.5), 2
        )

    rate_is_estimate = daily_interest_rate_pct is None
    rate = daily_interest_rate_pct if daily_interest_rate_pct is not None else FALLBACK_DAILY_INTEREST_RATE_PCT
    est_daily_cost = round(rate * suggested_leverage, 4)

    notes = (
        f"{'Estimated' if rate_is_estimate else 'Reported'} daily interest {rate:.4f}%/day on the borrowed "
        f"portion — at {suggested_leverage}x that's roughly {est_daily_cost:.4f}% of position value per day "
        "in carry cost, before any trading P&L. "
    )
    if rate_is_estimate:
        notes += (
            "This is a rough estimate, not Binance's live rate. Ask the connected AI client to read the "
            "real cross/isolated margin rate from Binance Agent OS before sizing a real trade."
        )

    return MarginAnalysis(
        symbol=symbol,
        eligible=eligible,
        reasons=reasons,
        bias=analysis.bias,
        confidence=analysis.confidence,
        suggested_leverage=suggested_leverage,
        max_leverage_allowed=settings.max_leverage,
        daily_interest_rate_pct=rate,
        interest_rate_is_estimate=rate_is_estimate,
        est_daily_cost_pct_of_position=est_daily_cost,
        notes=notes,
        data_quality=analysis.data_quality,
    )
