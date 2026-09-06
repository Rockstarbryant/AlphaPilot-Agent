"""
Ad-hoc coin/token analysis — answers "what do you think about trading
BTC/USDT, should I long or short, or buy spot and hold?"

Deterministic scoring (RSI/MACD/momentum/regime) produces the bias and
confidence; app/agent/ai_provider.py is only used downstream, by callers
that want a plain-language narration of this same structured result — the
same discipline as app/agent/candidate_comparison.py. Nothing here reads an
AI-produced number. This module never touches Binance Agent OS or any
account/auth-scoped endpoint; it is 100% public REST data
(app/binance/market_data.py), so it works even with no MCP connection at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.binance.market_data import BinanceMarketDataClient
from app.market import indicators as ind
from app.market.regime import assess_market_regime

VALID_INTERVALS = {"15m", "1h", "4h", "1d"}


@dataclass
class CoinAnalysis:
    symbol: str
    interval: str
    price: float
    price_change_pct_24h: float
    rsi: dict
    macd: dict
    momentum: dict
    market_regime: str
    regime_notes: str
    bias: str  # LONG | SHORT | HOLD_SPOT | WAIT
    confidence: float  # 0-100
    rationale: list[str]
    spot_guidance: str
    derivatives_guidance: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _score_bias(
    rsi: ind.RSIResult, macd: ind.MACDResult, momentum: ind.MomentumResult, regime: str
) -> tuple[str, float, list[str]]:
    """
    Deterministic point-scoring across three independent signals, then a
    regime gate. Purely additive/subtractive so every number in the output
    is traceable to a specific signal — no hidden weighting.
    """
    long_points = 0
    short_points = 0
    rationale: list[str] = []

    if rsi.signal == "OVERSOLD":
        long_points += 2
        rationale.append(f"RSI({rsi.period}) {rsi.value} is oversold — historically favors mean-reversion up.")
    elif rsi.signal == "OVERBOUGHT":
        short_points += 2
        rationale.append(f"RSI({rsi.period}) {rsi.value} is overbought — historically favors mean-reversion down.")
    elif rsi.signal == "NEUTRAL" and rsi.value is not None:
        rationale.append(f"RSI({rsi.period}) {rsi.value} is neutral — no strong mean-reversion signal.")

    if macd.crossover == "BULLISH_CROSS":
        long_points += 3
        rationale.append("MACD just crossed bullish (histogram flipped positive).")
    elif macd.crossover == "BEARISH_CROSS":
        short_points += 3
        rationale.append("MACD just crossed bearish (histogram flipped negative).")
    elif macd.crossover == "BULLISH":
        long_points += 1
        rationale.append("MACD histogram is positive — trend bias is up.")
    elif macd.crossover == "BEARISH":
        short_points += 1
        rationale.append("MACD histogram is negative — trend bias is down.")

    if momentum.direction == "UP":
        long_points += 2
        rationale.append(f"Momentum is up {momentum.roc_pct}% over the lookback window.")
    elif momentum.direction == "DOWN":
        short_points += 2
        rationale.append(f"Momentum is down {momentum.roc_pct}% over the lookback window.")

    if regime in ("BEARISH", "RISK_OFF"):
        short_points += 1
        long_points = max(0, long_points - 1)
        rationale.append(f"Market regime is {regime} — long setups get a penalty.")
    elif regime == "BULLISH":
        long_points += 1
        rationale.append("Market regime is BULLISH — long setups get a bonus.")
    elif regime in ("HIGH_VOLATILITY", "UNKNOWN"):
        rationale.append(f"Market regime is {regime} — sizing/leverage should be conservative regardless of bias.")

    total = long_points + short_points
    if total == 0:
        return "WAIT", 0.0, rationale + ["Not enough signal agreement to take a directional view right now."]

    if long_points > short_points:
        bias = "LONG"
        confidence = round(long_points / total * 100, 1)
    elif short_points > long_points:
        bias = "SHORT"
        confidence = round(short_points / total * 100, 1)
    else:
        bias = "WAIT"
        confidence = 50.0
        rationale.append("Long and short signals are tied — no clean directional edge.")

    # A directional bias needs conviction, not just a slim majority, before
    # it's worth surfacing as LONG/SHORT rather than WAIT.
    if bias in ("LONG", "SHORT") and confidence < 60:
        rationale.append(f"Confidence {confidence}% is below the 60% bar for a directional call — downgraded to WAIT.")
        bias = "WAIT"

    return bias, confidence, rationale


async def analyze_symbol(symbol: str, interval: str = "1h") -> CoinAnalysis:
    symbol = symbol.upper().replace("/", "")
    if interval not in VALID_INTERVALS:
        interval = "1h"

    client = BinanceMarketDataClient()
    try:
        regime_assessment = await assess_market_regime(client)
        tickers = await client.get_24h_tickers()
        ticker = next((t for t in tickers if t.symbol == symbol), None)
        klines = await client.get_klines(symbol, interval=interval, limit=100)
    finally:
        await client.close()

    closes = [k["close"] for k in klines]
    rsi = ind.compute_rsi(closes)
    macd = ind.compute_macd(closes)
    momentum = ind.compute_momentum(closes)

    bias, confidence, rationale = _score_bias(rsi, macd, momentum, regime_assessment.regime)

    if bias == "LONG":
        spot_guidance = (
            "Deterministic signals lean bullish. A spot buy-and-hold is the lower-risk way to "
            "express this — no liquidation risk, no funding/borrow cost."
        )
        derivatives_guidance = (
            f"If using derivatives: consider a LONG with tight risk sizing. Confidence {confidence}% "
            "is a signal-agreement score, not a win-rate — always pair with a hard stop."
        )
    elif bias == "SHORT":
        spot_guidance = (
            "Deterministic signals lean bearish. Spot can only express this by staying out or "
            "reducing an existing holding — spot has no native short."
        )
        derivatives_guidance = (
            f"If using derivatives: consider a SHORT with tight risk sizing. Confidence {confidence}% "
            "is a signal-agreement score, not a win-rate — always pair with a hard stop."
        )
    else:
        spot_guidance = "No clean directional edge right now — holding cash or an existing position is reasonable."
        derivatives_guidance = "Avoid opening new leveraged positions until signals agree more clearly."

    return CoinAnalysis(
        symbol=symbol,
        interval=interval,
        price=ticker.last_price if ticker else (closes[-1] if closes else 0.0),
        price_change_pct_24h=ticker.price_change_pct_24h if ticker else 0.0,
        rsi={"value": rsi.value, "period": rsi.period, "signal": rsi.signal},
        macd={"macd": macd.macd, "signal_line": macd.signal_line, "histogram": macd.histogram, "crossover": macd.crossover},
        momentum={"roc_pct": momentum.roc_pct, "direction": momentum.direction},
        market_regime=regime_assessment.regime,
        regime_notes=regime_assessment.notes,
        bias=bias,
        confidence=confidence,
        rationale=rationale,
        spot_guidance=spot_guidance,
        derivatives_guidance=derivatives_guidance,
