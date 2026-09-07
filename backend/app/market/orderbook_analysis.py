"""
Order book microstructure — the fastest-moving, shortest-horizon signal in
this whole engine. Unlike klines (which are already-settled history), this
is a live snapshot of resting orders, so it's the closest thing to "what
happens in the next few minutes" this project has. Deliberately kept
separate from the candle-based signals in indicators.py/structure.py/
volume_profile.py — order book imbalance flips far faster than a trend does
and shouldn't be blended into the same score at the same weight.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderBookAnalysis:
    spread_bps: float | None
    bid_depth_usdt: float  # sum of price*qty within the fetched levels, bid side
    ask_depth_usdt: float
    imbalance_ratio: float | None  # bid_depth / (bid_depth + ask_depth); 0.5 = balanced
    imbalance_signal: str  # BID_HEAVY | ASK_HEAVY | BALANCED | UNKNOWN
    large_bid_walls: list[dict]  # [{price, qty, usdt_value}], biggest first
    large_ask_walls: list[dict]
    notes: str


def analyze_order_book(bids: list[list[float]], asks: list[list[float]], *, wall_multiple: float = 5.0) -> OrderBookAnalysis:
    """
    `bids`/`asks` are [[price, qty], ...] with best price first on each
    side (Binance's own ordering). `wall_multiple` controls what counts as
    a "wall": a level with at least `wall_multiple` times the average
    order size on its side of the book — deliberately relative to this
    symbol's own book, not a fixed USDT threshold, so it works for both a
    thin altcoin and BTC without separate tuning.
    """
    if not bids or not asks:
        return OrderBookAnalysis(None, 0.0, 0.0, None, "UNKNOWN", [], [], "Order book unavailable.")

    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2
    spread_bps = ((best_ask - best_bid) / mid) * 10_000 if mid > 0 else None

    bid_depth = sum(p * q for p, q in bids)
    ask_depth = sum(p * q for p, q in asks)
    total_depth = bid_depth + ask_depth
    imbalance_ratio = round(bid_depth / total_depth, 3) if total_depth > 0 else None

    if imbalance_ratio is None:
        imbalance_signal = "UNKNOWN"
    elif imbalance_ratio > 0.60:
        imbalance_signal = "BID_HEAVY"
    elif imbalance_ratio < 0.40:
        imbalance_signal = "ASK_HEAVY"
    else:
        imbalance_signal = "BALANCED"

    def _find_walls(levels: list[list[float]]) -> list[dict]:
        if not levels:
            return []
        avg_qty = sum(q for _, q in levels) / len(levels)
        if avg_qty <= 0:
            return []
        walls = [
            {"price": p, "qty": q, "usdt_value": round(p * q, 2)}
            for p, q in levels
            if q >= avg_qty * wall_multiple
        ]
        walls.sort(key=lambda w: w["usdt_value"], reverse=True)
        return walls[:3]

    bid_walls = _find_walls(bids)
    ask_walls = _find_walls(asks)

    notes_parts = []
    if imbalance_signal == "BID_HEAVY":
        notes_parts.append(f"{imbalance_ratio * 100:.0f}% of visible depth is on the buy side — more resting demand than supply right now.")
    elif imbalance_signal == "ASK_HEAVY":
        notes_parts.append(f"{(1 - (imbalance_ratio or 0)) * 100:.0f}% of visible depth is on the sell side — more resting supply than demand right now.")
    else:
        notes_parts.append("Buy and sell depth are roughly balanced.")
    if bid_walls:
        notes_parts.append(f"A large buy wall sits at {bid_walls[0]['price']} (~${bid_walls[0]['usdt_value']:,.0f}) — may act as short-term support.")
    if ask_walls:
        notes_parts.append(f"A large sell wall sits at {ask_walls[0]['price']} (~${ask_walls[0]['usdt_value']:,.0f}) — may act as short-term resistance.")
    notes_parts.append(
        "Order book depth is a short-horizon read (minutes) — resting orders can be pulled at any time and "
        "shouldn't be weighted like a multi-hour trend signal."
    )

    return OrderBookAnalysis(
        spread_bps=round(spread_bps, 2) if spread_bps is not None else None,
        bid_depth_usdt=round(bid_depth, 2),
        ask_depth_usdt=round(ask_depth, 2),
        imbalance_ratio=imbalance_ratio,
        imbalance_signal=imbalance_signal,
        large_bid_walls=bid_walls,
        large_ask_walls=ask_walls,
        notes=" ".join(notes_parts),
    )
