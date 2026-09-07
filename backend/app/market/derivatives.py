"""
Derivatives positioning — funding rate, open interest, and basis. All three
answer "how leveraged/one-sided is the bet on this coin right now", which
spot price action alone can't tell you: price can be flat while funding
gets extremely one-sided, and that's usually when a squeeze happens.

Binance's futures REST exposes funding rate and open interest as public,
unauthenticated market data (GET /fapi/v1/premiumIndex, /fundingRate,
/openInterest — see app/binance/market_data.py and
docs/BINANCE_CAPABILITY_MATRIX.md). Binance does NOT expose historical
liquidation data through public REST at all — that's the one cell in the
user's requested matrix with no free-data path; it's surfaced honestly as
unavailable rather than approximated.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.binance.market_data import BinanceMarketDataClient

# Binance settles funding every 8h; a rate persistently beyond this band is
# considered "stretched" — longs (positive) or shorts (negative) are paying
# a meaningfully above-normal premium to hold their position.
STRETCHED_FUNDING_RATE_PCT = 0.05  # 0.05% per 8h ≈ ~55% annualized


@dataclass
class DerivativesAnalysis:
    available: bool
    funding_rate_pct: float | None  # current, per 8h settlement, as a percentage
    funding_rate_annualized_pct: float | None
    funding_trend: str  # RISING | FALLING | STABLE | UNKNOWN
    open_interest: float | None  # in contracts
    open_interest_trend_pct: float | None  # change over the funding-history lookback window
    basis_pct: float | None  # (futures mark price - spot price) / spot price
    positioning_signal: str  # OVERHEATED_LONG | OVERHEATED_SHORT | NEUTRAL | UNKNOWN
    liquidation_data: str  # always "unavailable" — see module docstring
    notes: str


async def analyze_derivatives(symbol: str, spot_price: float | None = None) -> DerivativesAnalysis:
    """
    `spot_price` — if the caller already fetched a spot ticker for this
    symbol (as app/market/coin_analysis.py does), pass it in to get a real
    basis calculation; without it, basis is reported as unavailable rather
    than guessed.
    """
    client = BinanceMarketDataClient(market_type="futures")
    try:
        try:
            premium = await client.get_premium_index(symbol)
        except Exception:
            # Most likely this symbol simply has no futures listing —
            # common for smaller-cap spot-only coins. Not an error to alarm on.
            return DerivativesAnalysis(
                available=False, funding_rate_pct=None, funding_rate_annualized_pct=None,
                funding_trend="UNKNOWN", open_interest=None, open_interest_trend_pct=None,
                basis_pct=None, positioning_signal="UNKNOWN", liquidation_data="unavailable",
                notes=f"No USDⓈ-M futures market found for {symbol} — derivatives positioning isn't applicable.",
            )

        funding_history = await client.get_funding_rate_history(symbol, limit=9)  # ~3 days at 8h settlements
        open_interest = await client.get_open_interest(symbol)
    finally:
        await client.close()

    current_funding_pct = premium["last_funding_rate"] * 100
    annualized = round(current_funding_pct * 3 * 365, 2)  # 3 settlements/day

    funding_trend = "UNKNOWN"
    if len(funding_history) >= 3:
        recent = [f["funding_rate"] for f in funding_history[-3:]]
        if recent[-1] > recent[0] * 1.2 and recent[-1] > 0:
            funding_trend = "RISING"
        elif recent[-1] < recent[0] * 1.2 and recent[-1] < 0:
            funding_trend = "FALLING"
        else:
            funding_trend = "STABLE"

    basis_pct = None
    if spot_price and spot_price > 0:
        basis_pct = round((premium["mark_price"] - spot_price) / spot_price * 100, 3)

    if current_funding_pct > STRETCHED_FUNDING_RATE_PCT:
        positioning_signal = "OVERHEATED_LONG"
    elif current_funding_pct < -STRETCHED_FUNDING_RATE_PCT:
        positioning_signal = "OVERHEATED_SHORT"
    else:
        positioning_signal = "NEUTRAL"

    notes_parts = [
        f"Funding rate is {current_funding_pct:+.4f}% per 8h (~{annualized:+.1f}%/yr annualized) — "
        + (
            "longs are paying shorts a stretched premium, a classic 'too many people long' warning sign."
            if positioning_signal == "OVERHEATED_LONG"
            else "shorts are paying longs a stretched premium, a classic 'too many people short' warning sign."
            if positioning_signal == "OVERHEATED_SHORT"
            else "within a normal range — no one-sided crowding."
        )
    ]
    if basis_pct is not None:
        notes_parts.append(f"Futures trade at a {basis_pct:+.3f}% basis to spot.")
    notes_parts.append(
        "Liquidation data isn't available from Binance's public API — this reads positioning risk from "
        "funding/open-interest only, not actual forced-close volume."
    )

    return DerivativesAnalysis(
        available=True,
        funding_rate_pct=round(current_funding_pct, 4),
        funding_rate_annualized_pct=annualized,
        funding_trend=funding_trend,
        open_interest=open_interest,
        open_interest_trend_pct=None,  # would need a stored prior snapshot to diff against; not computed here
        basis_pct=basis_pct,
        positioning_signal=positioning_signal,
        liquidation_data="unavailable",
        notes=" ".join(notes_parts),
    )
