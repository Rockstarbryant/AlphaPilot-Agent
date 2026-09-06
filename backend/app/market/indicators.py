"""
Technical indicators computed from Binance public kline data. Deterministic,
no AI involved — same discipline as app/market/regime.py and
app/risk/engine.py. These feed app/market/coin_analysis.py, which is what
AlphaPilot's advisory tools (REST + MCP) expose to a user or an AI client.

All functions take a list of closing prices ordered oldest -> newest (the
same order Binance's ``/api/v3/klines`` returns) and are defensive about
short/insufficient history rather than raising, since a chat-driven "what do
you think about <symbol>" request should degrade gracefully instead of 500ing.
"""
from __future__ import annotations

from dataclasses import dataclass


def _emas(values: list[float], period: int) -> list[float]:
    """Exponential moving average series, same length as ``values`` once
    it reaches ``period`` samples (shorter runs are seeded with a simple
    average of what's available)."""
    if not values:
        return []
    k = 2 / (period + 1)
    seed_n = min(period, len(values))
    seed = sum(values[:seed_n]) / seed_n
    out = [seed]
    for price in values[seed_n:]:
        out.append(price * k + out[-1] * (1 - k))
    return out


@dataclass
class RSIResult:
    value: float | None  # 0-100, None if not enough data
    period: int
    signal: str  # OVERBOUGHT | OVERSOLD | NEUTRAL | UNKNOWN


def compute_rsi(closes: list[float], period: int = 14) -> RSIResult:
    """Wilder's RSI. Needs at least ``period`` + 1 closes; degrades to
    UNKNOWN rather than raising when history is too short."""
    if len(closes) < period + 1:
        return RSIResult(value=None, period=period, signal="UNKNOWN")

    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(0.0, delta))
        losses.append(max(0.0, -delta))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    if rsi >= 70:
        signal = "OVERBOUGHT"
    elif rsi <= 30:
        signal = "OVERSOLD"
    else:
        signal = "NEUTRAL"
    return RSIResult(value=round(rsi, 2), period=period, signal=signal)


@dataclass
class MACDResult:
    macd: float | None
    signal_line: float | None
    histogram: float | None
    crossover: str  # BULLISH_CROSS | BEARISH_CROSS | BULLISH | BEARISH | UNKNOWN


def compute_macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> MACDResult:
    """Standard 12/26/9 MACD. ``crossover`` reports the most recent histogram
    sign change (a fresh cross) or, absent one, just the current bias."""
    if len(closes) < slow + signal:
        return MACDResult(macd=None, signal_line=None, histogram=None, crossover="UNKNOWN")

    ema_fast = _emas(closes, fast)
    ema_slow = _emas(closes, slow)
    n = min(len(ema_fast), len(ema_slow))
    macd_line = [ema_fast[len(ema_fast) - n + i] - ema_slow[len(ema_slow) - n + i] for i in range(n)]
    signal_series = _emas(macd_line, signal)

    m = min(len(macd_line), len(signal_series))
    hist_series = [macd_line[len(macd_line) - m + i] - signal_series[len(signal_series) - m + i] for i in range(m)]

    if len(hist_series) < 2:
        crossover = "UNKNOWN"
    elif hist_series[-2] <= 0 < hist_series[-1]:
        crossover = "BULLISH_CROSS"
    elif hist_series[-2] >= 0 > hist_series[-1]:
        crossover = "BEARISH_CROSS"
    elif hist_series[-1] > 0:
        crossover = "BULLISH"
    else:
        crossover = "BEARISH"

    return MACDResult(
        macd=round(macd_line[-1], 6),
        signal_line=round(signal_series[-1], 6),
        histogram=round(hist_series[-1], 6),
        crossover=crossover,
    )


@dataclass
class MomentumResult:
    roc_pct: float | None  # rate of change over the lookback window
    direction: str  # UP | DOWN | FLAT | UNKNOWN


def compute_momentum(closes: list[float], lookback: int = 12) -> MomentumResult:
    """Simple rate-of-change momentum over ``lookback`` candles."""
    if len(closes) <= lookback:
        return MomentumResult(roc_pct=None, direction="UNKNOWN")
    start, end = closes[-lookback - 1], closes[-1]
    if start == 0:
        return MomentumResult(roc_pct=None, direction="UNKNOWN")
    roc = (end - start) / start * 100
    direction = "UP" if roc > 0.5 else "DOWN" if roc < -0.5 else "FLAT"
    return MomentumResult(roc_pct=round(roc, 2), direction=direction)
