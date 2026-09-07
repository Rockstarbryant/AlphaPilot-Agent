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


def _sma(values: list[float], period: int) -> list[float]:
    """Simple moving average series — shorter than ``values`` by ``period - 1``."""
    if len(values) < period:
        return []
    return [sum(values[i - period + 1 : i + 1]) / period for i in range(period - 1, len(values))]


@dataclass
class MAResult:
    sma_20: float | None
    sma_50: float | None
    ema_20: float | None
    ema_50: float | None
    price_vs_sma20_pct: float | None  # positive = price above the average
    golden_cross: bool  # sma20 crossed above sma50 in the last few candles
    death_cross: bool
    trend: str  # UPTREND | DOWNTREND | SIDEWAYS | UNKNOWN


def compute_moving_averages(closes: list[float]) -> MAResult:
    """SMA/EMA 20 & 50, plus whether a golden/death cross just happened —
    the classic 'is this a real trend or just noise' check."""
    if len(closes) < 51:
        return MAResult(None, None, None, None, None, False, False, "UNKNOWN")

    sma20_series = _sma(closes, 20)
    sma50_series = _sma(closes, 50)
    ema20_series = _emas(closes, 20)
    ema50_series = _emas(closes, 50)

    sma20, sma50 = sma20_series[-1], sma50_series[-1]
    ema20, ema50 = ema20_series[-1], ema50_series[-1]

    # Look back a few candles on the SMA series (aligned to the shorter
    # series' length) to catch a cross that happened recently, not just
    # the instantaneous relationship.
    n = min(len(sma20_series), len(sma50_series))
    recent20 = sma20_series[-n:]
    recent50 = sma50_series[-n:]
    lookback = min(5, n - 1)
    golden_cross = lookback > 0 and recent20[-1 - lookback] <= recent50[-1 - lookback] and recent20[-1] > recent50[-1]
    death_cross = lookback > 0 and recent20[-1 - lookback] >= recent50[-1 - lookback] and recent20[-1] < recent50[-1]

    price = closes[-1]
    price_vs_sma20 = round((price - sma20) / sma20 * 100, 2) if sma20 else None

    if sma20 > sma50 and price > sma20:
        trend = "UPTREND"
    elif sma20 < sma50 and price < sma20:
        trend = "DOWNTREND"
    else:
        trend = "SIDEWAYS"

    return MAResult(
        sma_20=round(sma20, 6), sma_50=round(sma50, 6), ema_20=round(ema20, 6), ema_50=round(ema50, 6),
        price_vs_sma20_pct=price_vs_sma20, golden_cross=golden_cross, death_cross=death_cross, trend=trend,
    )


@dataclass
class BollingerResult:
    upper: float | None
    middle: float | None
    lower: float | None
    bandwidth_pct: float | None  # (upper-lower)/middle — squeeze detector
    percent_b: float | None  # 0 = at lower band, 1 = at upper band, can exceed [0,1]
    signal: str  # SQUEEZE | UPPER_BREAKOUT | LOWER_BREAKOUT | INSIDE | UNKNOWN


def compute_bollinger_bands(closes: list[float], period: int = 20, num_std: float = 2.0) -> BollingerResult:
    """Bollinger Bands — volatility envelope around a moving average.
    A tight bandwidth ('squeeze') often precedes a big move; a close
    outside the bands is a volatility breakout, not automatically a
    reversal signal, so it's reported descriptively, not scored as
    directional on its own."""
    if len(closes) < period:
        return BollingerResult(None, None, None, None, None, "UNKNOWN")

    window = closes[-period:]
    middle = sum(window) / period
    variance = sum((c - middle) ** 2 for c in window) / period
    std = variance ** 0.5
    upper = middle + num_std * std
    lower = middle - num_std * std
    price = closes[-1]

    bandwidth_pct = round((upper - lower) / middle * 100, 2) if middle else None
    percent_b = round((price - lower) / (upper - lower), 3) if upper != lower else None

    if bandwidth_pct is not None and bandwidth_pct < 4:
        signal = "SQUEEZE"
    elif price > upper:
        signal = "UPPER_BREAKOUT"
    elif price < lower:
        signal = "LOWER_BREAKOUT"
    else:
        signal = "INSIDE"

    return BollingerResult(
        upper=round(upper, 6), middle=round(middle, 6), lower=round(lower, 6),
        bandwidth_pct=bandwidth_pct, percent_b=percent_b, signal=signal,
    )


@dataclass
class SupportResistanceResult:
    support_levels: list[float]  # nearest first, below current price
    resistance_levels: list[float]  # nearest first, above current price
    nearest_support: float | None
    nearest_resistance: float | None
    distance_to_support_pct: float | None
    distance_to_resistance_pct: float | None


def compute_support_resistance(
    highs: list[float], lows: list[float], closes: list[float], *, pivot_window: int = 3, max_levels: int = 3
) -> SupportResistanceResult:
    """
    Fractal/pivot-based support & resistance: a candle is a swing high if
    its high is the max within +/- pivot_window candles (swing low,
    symmetric). This is the same logic a human chartist applies by eye —
    deterministic, no lookahead (only pivots that are already fully formed,
    i.e. not within pivot_window of the most recent candle, are used).
    """
    n = len(closes)
    if n < pivot_window * 2 + 5:
        return SupportResistanceResult([], [], None, None, None, None)

    swing_highs, swing_lows = [], []
    # Exclude the last `pivot_window` candles — a pivot there isn't
    # confirmed yet (we can't see candles after it).
    for i in range(pivot_window, n - pivot_window):
        window_highs = highs[i - pivot_window : i + pivot_window + 1]
        window_lows = lows[i - pivot_window : i + pivot_window + 1]
        if highs[i] == max(window_highs):
            swing_highs.append(highs[i])
        if lows[i] == min(window_lows):
            swing_lows.append(lows[i])

    price = closes[-1]
    resistance_levels = sorted({round(h, 6) for h in swing_highs if h > price})[:max_levels]
    support_levels = sorted({round(l, 6) for l in swing_lows if l < price}, reverse=True)[:max_levels]

    nearest_resistance = resistance_levels[0] if resistance_levels else None
    nearest_support = support_levels[0] if support_levels else None

    return SupportResistanceResult(
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        distance_to_support_pct=round((price - nearest_support) / price * 100, 2) if nearest_support else None,
        distance_to_resistance_pct=round((nearest_resistance - price) / price * 100, 2) if nearest_resistance else None,
    )
