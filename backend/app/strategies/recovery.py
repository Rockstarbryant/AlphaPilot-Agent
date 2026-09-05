"""
Recovery Hunter — analyzes the day's top losers and scores whether the drop
looks like temporary weakness (recoverable) vs. structural deterioration
(avoid). Same discipline as Gainer Hunter: discovery + scoring only, no
execution here.
"""
from __future__ import annotations

import math

from app.binance.market_data import BinanceMarketDataClient, TickerSnapshot
from app.core.config import get_settings

settings = get_settings()


def _classify(score: float) -> str:
    if score >= 80:
        return "HIGH_RECOVERY_POTENTIAL"
    if score >= 65:
        return "MEDIUM"
    if score >= 40:
        return "LOW"
    return "AVOID"


def _score_recovery(
    ticker: TickerSnapshot,
    spread_bps: float,
    momentum_1h_pct: float,
    volume_ratio: float,
    distance_from_24h_low_pct: float,
) -> tuple[float, dict]:
    """
    Deterministic 0-100 recovery score. Higher = more likely a temporary
    dip with reversal signs, lower = looks like continued distribution.
    """
    breakdown = {}

    # Stabilization: is the very recent move flattening or turning positive
    # relative to the still-negative 24h change? A 1h move that's already
    # positive while 24h is deeply negative suggests selling has paused.
    if ticker.price_change_pct_24h < 0:
        stabilization_ratio = momentum_1h_pct - (ticker.price_change_pct_24h / 24)
    else:
        stabilization_ratio = momentum_1h_pct
    stabilization_score = max(0.0, min(30.0, (stabilization_ratio + 1) * 10))
    breakdown["stabilization"] = round(stabilization_score, 1)

    # Volume behavior: declining volume on the down move (capitulation
    # exhausting) scores better than volume accelerating into new lows.
    if volume_ratio < 1.0:
        volume_score = 20.0 * (1 - volume_ratio)
    else:
        volume_score = max(0.0, 10.0 - (volume_ratio - 1) * 10)
    volume_score = max(0.0, min(20.0, volume_score))
    breakdown["volume_behavior"] = round(volume_score, 1)

    # Liquidity — same treatment as Gainer Hunter, a thin order book makes
    # any "recovery" unreliable to actually trade.
    liq_ratio = ticker.quote_volume_24h / max(settings.min_quote_volume_24h_usdt, 1.0)
    liquidity_score = max(0.0, min(20.0, math.log10(max(liq_ratio, 1.0)) * 10))
    breakdown["liquidity"] = round(liquidity_score, 1)

    # Spread — wide spreads on a beaten-down asset are a liquidity-flight
    # signal, not just a cost.
    spread_score = max(0.0, min(15.0, 15.0 * (1 - (spread_bps / max(settings.max_spread_bps, 1.0)))))
    breakdown["spread_quality"] = round(spread_score, 1)

    # Proximity to the 24h low: too close to the low with no bounce yet is
    # riskier (falling knife); some distance off the low is a mild positive.
    proximity_score = max(0.0, min(15.0, distance_from_24h_low_pct * 3))
    breakdown["off_the_low"] = round(proximity_score, 1)

    # Severity penalty: extremely large single-day drops get a structural-risk
    # penalty by default — the burden of proof for "temporary" rises with
    # the size of the move.
    severity_penalty = 0.0
    if ticker.price_change_pct_24h < -30:
        severity_penalty = 15.0
    elif ticker.price_change_pct_24h < -15:
        severity_penalty = 7.0
    breakdown["severity_penalty"] = -severity_penalty

    total = (
        stabilization_score + volume_score + liquidity_score
        + spread_score + proximity_score - severity_penalty
    )
    total = max(0.0, min(100.0, total))
    return total, breakdown


async def discover_recovery_candidates(client: BinanceMarketDataClient) -> list[dict]:
    tickers = await client.get_24h_tickers()
    tradeable = await client.get_exchange_info_symbols(quote_asset="USDT")

    qualifying = [
        t for t in tickers
        if t.symbol in tradeable
        and t.quote_volume_24h >= settings.min_quote_volume_24h_usdt
        and t.price_change_pct_24h < 0
    ]
    qualifying.sort(key=lambda t: t.price_change_pct_24h)  # most negative first
    top = qualifying[: settings.loser_candidate_count]

    candidates = []
    for ticker in top:
        spread_bps = await client.get_spread_bps(ticker.symbol)
        if spread_bps is None or spread_bps > settings.max_spread_bps:
            continue

        klines = await client.get_klines(ticker.symbol, interval="1h", limit=24)
        if len(klines) < 2:
            continue

        momentum_1h_pct = (
            (klines[-1]["close"] - klines[-2]["close"]) / klines[-2]["close"] * 100
            if klines[-2]["close"] else 0.0
        )
        avg_hourly_volume = sum(k["volume"] for k in klines[:-1]) / max(len(klines) - 1, 1)
        volume_ratio = klines[-1]["volume"] / avg_hourly_volume if avg_hourly_volume else 0.0

        low_24h = min(k["low"] for k in klines)
        distance_from_low_pct = (
            (ticker.last_price - low_24h) / low_24h * 100 if low_24h else 0.0
        )

        score, breakdown = _score_recovery(
            ticker, spread_bps, momentum_1h_pct, volume_ratio, distance_from_low_pct
        )
        classification = _classify(score)

        candidates.append({
            "symbol": ticker.symbol,
            "price": ticker.last_price,
            "daily_change_pct": ticker.price_change_pct_24h,
            "quote_volume_24h": ticker.quote_volume_24h,
            "spread_bps": spread_bps,
            "recovery_score": score,
            "classification": classification,
            "score_breakdown": breakdown,
            "data_source_timestamp": ticker.fetched_at,
            "data_age_seconds": ticker.age_seconds,
        })

    return candidates


def build_trade_plan_dict(candidate: dict, user_id: str, max_trade_usdt: float) -> dict:
    from app.core.config import get_settings as _gs
    s = _gs()
    return {
        "idempotency_key": f"recovery:{candidate['symbol']}:{candidate['data_source_timestamp'].isoformat()}",
        "user_id": user_id,
        "symbol": candidate["symbol"],
        "strategy": "recovery_hunter",
        "side": "BUY",
        "entry_price": candidate["price"],
        "position_size_usdt": min(max_trade_usdt, s.max_spot_trade_usdt),
        "estimated_slippage_bps": candidate["spread_bps"],
        "stop_loss_pct": s.recovery_hard_stop_pct,
        "profit_targets_pct": {str(s.recovery_take_profit_pct): 1.0},  # full exit at target
        "opportunity_score": candidate["recovery_score"],
        "reason": (
            f"{candidate['symbol']} dropped {candidate['daily_change_pct']:.1f}% / 24h but shows "
            f"{candidate['classification']} recovery signals (score "
            f"{candidate['recovery_score']:.1f}/100) — stabilizing momentum, liquidity and spread "
            f"within bounds."
        ),
        "market_conditions": candidate["score_breakdown"],
    }
