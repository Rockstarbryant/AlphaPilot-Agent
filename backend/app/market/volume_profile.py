"""
Volume analysis — VWAP and a volume profile (point of control + value
area), computed from the same klines app/market/indicators.py already
fetches. Binance's public kline payload includes per-candle volume, so
none of this needs a separate endpoint.

A volume profile answers a different question than price alone: not "did
price go up" but "did real size trade there". A price level with a lot of
volume behind it (the Point of Control) tends to act as a magnet/support-
resistance in its own right, independent of the swing-pivot levels in
app/market/indicators.py's support/resistance — the two are complementary,
not duplicates.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VWAPResult:
    vwap: float | None
    price_vs_vwap_pct: float | None  # positive = trading above VWAP (bullish for the session)
    signal: str  # ABOVE_VWAP | BELOW_VWAP | AT_VWAP | UNKNOWN


def compute_vwap(klines: list[dict]) -> VWAPResult:
    """Volume-weighted average price over the fetched window (not reset
    daily — this is a rolling VWAP over whatever interval/limit the caller
    requested, which is the right comparison for a swing-trade-horizon
    analysis rather than an intraday-only one)."""
    if not klines:
        return VWAPResult(None, None, "UNKNOWN")

    total_pv = 0.0
    total_v = 0.0
    for k in klines:
        typical_price = (k["high"] + k["low"] + k["close"]) / 3
        total_pv += typical_price * k["volume"]
        total_v += k["volume"]

    if total_v == 0:
        return VWAPResult(None, None, "UNKNOWN")

    vwap = total_pv / total_v
    price = klines[-1]["close"]
    diff_pct = round((price - vwap) / vwap * 100, 2) if vwap else None
    signal = "ABOVE_VWAP" if diff_pct and diff_pct > 0.2 else "BELOW_VWAP" if diff_pct and diff_pct < -0.2 else "AT_VWAP"

    return VWAPResult(vwap=round(vwap, 6), price_vs_vwap_pct=diff_pct, signal=signal)


@dataclass
class VolumeProfileResult:
    point_of_control: float | None  # price level with the most traded volume
    value_area_low: float | None  # bounds of the 70%-of-volume zone around POC
    value_area_high: float | None
    price_vs_poc_pct: float | None
    signal: str  # ABOVE_VALUE_AREA | INSIDE_VALUE_AREA | BELOW_VALUE_AREA | UNKNOWN


def compute_volume_profile(klines: list[dict], *, num_bins: int = 24, value_area_pct: float = 0.70) -> VolumeProfileResult:
    """
    Bins the traded price range into `num_bins` buckets, assigns each
    candle's volume to the bucket its typical price falls in, and finds the
    Point of Control (highest-volume bucket) and Value Area (the smallest
    contiguous band of buckets containing `value_area_pct` of total volume,
    expanded outward from the POC — the standard construction).
    """
    if len(klines) < 10:
        return VolumeProfileResult(None, None, None, None, "UNKNOWN")

    lows = [k["low"] for k in klines]
    highs = [k["high"] for k in klines]
    lo, hi = min(lows), max(highs)
    if hi <= lo:
        return VolumeProfileResult(None, None, None, None, "UNKNOWN")

    bin_width = (hi - lo) / num_bins
    volumes = [0.0] * num_bins

    for k in klines:
        typical_price = (k["high"] + k["low"] + k["close"]) / 3
        idx = min(num_bins - 1, max(0, int((typical_price - lo) / bin_width)))
        volumes[idx] += k["volume"]

    total_volume = sum(volumes)
    if total_volume == 0:
        return VolumeProfileResult(None, None, None, None, "UNKNOWN")

    poc_idx = volumes.index(max(volumes))
    poc_price = lo + (poc_idx + 0.5) * bin_width

    # Expand outward from POC, always taking the larger neighboring bin
    # next, until the accumulated volume crosses the target share.
    low_idx = high_idx = poc_idx
    accumulated = volumes[poc_idx]
    target = total_volume * value_area_pct
    while accumulated < target and (low_idx > 0 or high_idx < num_bins - 1):
        expand_low = volumes[low_idx - 1] if low_idx > 0 else -1
        expand_high = volumes[high_idx + 1] if high_idx < num_bins - 1 else -1
        if expand_high >= expand_low:
            high_idx += 1
            accumulated += volumes[high_idx]
        else:
            low_idx -= 1
            accumulated += volumes[low_idx]

    value_area_low = lo + low_idx * bin_width
    value_area_high = lo + (high_idx + 1) * bin_width
    price = klines[-1]["close"]

    if price > value_area_high:
        signal = "ABOVE_VALUE_AREA"
    elif price < value_area_low:
        signal = "BELOW_VALUE_AREA"
    else:
        signal = "INSIDE_VALUE_AREA"

    return VolumeProfileResult(
        point_of_control=round(poc_price, 6),
        value_area_low=round(value_area_low, 6),
        value_area_high=round(value_area_high, 6),
        price_vs_poc_pct=round((price - poc_price) / poc_price * 100, 2) if poc_price else None,
        signal=signal,
    )
