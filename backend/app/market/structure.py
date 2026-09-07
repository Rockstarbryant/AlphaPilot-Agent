"""
Market structure — the "is this actually trending or just noisy" read that
technical indicators alone can't give you. Built on the same swing-pivot
detection app/market/indicators.py uses for support/resistance, so a swing
high/low here is defined identically to a resistance/support level there.

Classical Dow Theory structure: a sequence of Higher Highs + Higher Lows is
an uptrend; Lower Highs + Lower Lows is a downtrend; anything else is
range-bound. A "break of structure" (BOS) — price taking out the most
recent swing high in an uptrend, or swing low in a downtrend — is the
textbook continuation signal; the opposite (failing to make a new high/low
and breaking the other way) is a "change of character" (CHoCH), the
textbook early-reversal signal.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: str  # HIGH | LOW


@dataclass
class MarketStructureResult:
    sequence: str  # UPTREND | DOWNTREND | RANGING | UNKNOWN
    last_swing_high: float | None
    last_swing_low: float | None
    break_of_structure: str | None  # "BULLISH_BOS" | "BEARISH_BOS" | None
    change_of_character: str | None  # "BULLISH_CHOCH" | "BEARISH_CHOCH" | None
    notes: str


def _find_swings(highs: list[float], lows: list[float], pivot_window: int) -> list[SwingPoint]:
    n = len(highs)
    swings: list[SwingPoint] = []
    for i in range(pivot_window, n - pivot_window):
        wh = highs[i - pivot_window : i + pivot_window + 1]
        wl = lows[i - pivot_window : i + pivot_window + 1]
        if highs[i] == max(wh):
            swings.append(SwingPoint(index=i, price=highs[i], kind="HIGH"))
        if lows[i] == min(wl):
            swings.append(SwingPoint(index=i, price=lows[i], kind="LOW"))
    swings.sort(key=lambda s: s.index)
    return swings


def analyze_market_structure(
    highs: list[float], lows: list[float], closes: list[float], *, pivot_window: int = 3
) -> MarketStructureResult:
    n = len(closes)
    if n < pivot_window * 2 + 10:
        return MarketStructureResult("UNKNOWN", None, None, None, None, "Not enough candle history for structure analysis.")

    swings = _find_swings(highs, lows, pivot_window)
    swing_highs = [s for s in swings if s.kind == "HIGH"]
    swing_lows = [s for s in swings if s.kind == "LOW"]

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return MarketStructureResult("UNKNOWN", None, None, None, None, "Not enough confirmed swing points yet.")

    last_high, prev_high = swing_highs[-1], swing_highs[-2]
    last_low, prev_low = swing_lows[-1], swing_lows[-2]

    higher_high = last_high.price > prev_high.price
    higher_low = last_low.price > prev_low.price
    lower_high = last_high.price < prev_high.price
    lower_low = last_low.price < prev_low.price

    if higher_high and higher_low:
        sequence = "UPTREND"
    elif lower_high and lower_low:
        sequence = "DOWNTREND"
    else:
        sequence = "RANGING"

    price = closes[-1]
    break_of_structure = None
    change_of_character = None

    if sequence == "UPTREND":
        if price > last_high.price:
            break_of_structure = "BULLISH_BOS"
        elif price < last_low.price:
            change_of_character = "BEARISH_CHOCH"
    elif sequence == "DOWNTREND":
        if price < last_low.price:
            break_of_structure = "BEARISH_BOS"
        elif price > last_high.price:
            change_of_character = "BULLISH_CHOCH"

    notes_parts = [f"Structure reads {sequence.lower()} from the last two confirmed swing highs/lows."]
    if break_of_structure:
        notes_parts.append(f"Price just broke the prior swing in the trend's own direction ({break_of_structure}) — a continuation signal.")
    if change_of_character:
        notes_parts.append(f"Price broke against the prevailing trend ({change_of_character}) — an early reversal warning, not yet a confirmed new trend.")

    return MarketStructureResult(
        sequence=sequence,
        last_swing_high=round(last_high.price, 6),
        last_swing_low=round(last_low.price, 6),
        break_of_structure=break_of_structure,
        change_of_character=change_of_character,
        notes=" ".join(notes_parts),
    )
