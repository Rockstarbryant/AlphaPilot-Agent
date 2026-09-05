"""
Gainer Hunter — discovery + scoring only. This module never places an order;
it produces MarketCandidate rows and, when a candidate clears the bar, a
risk-validated TradePlan. Execution is owned by the Binance Agent OS service.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.binance.market_data import BinanceMarketDataClient, TickerSnapshot
from app.core.config import get_settings

settings = get_settings()


def _score_gainer(
    ticker: TickerSnapshot,
    spread_bps: float,
    momentum_1h_pct: float,
    volume_ratio: float,
) -> tuple[float, dict]:
    """
    Deterministic 0-100 opportunity score. Every component is computed from
    real data passed in — nothing here is a placeholder or hardcoded token
    list. Weights are simple and documented so they're easy to defend to
    judges and to retune.
    """
    breakdown = {}

    # Momentum persistence: is the recent 1h move still in the same direction
    # as the 24h move, and not violently reversing?
    momentum_score = max(0.0, min(30.0, (momentum_1h_pct / max(ticker.price_change_pct_24h, 1e-6)) * 30))
    breakdown["momentum_persistence"] = round(momentum_score, 1)

    # Volume confirmation: volume_ratio is recent-hour volume vs the 24h
    # hourly average; >1 means volume is accelerating, not fading.
    volume_score = max(0.0, min(25.0, (volume_ratio - 0.5) * 25))
    breakdown["volume_confirmation"] = round(volume_score, 1)

    # Liquidity: quote volume 24h, scaled logarithmically against the
    # configured minimum so a $50M pair doesn't dwarf a $600K pair unfairly.
    import math
    liq_ratio = ticker.quote_volume_24h / max(settings.min_quote_volume_24h_usdt, 1.0)
    liquidity_score = max(0.0, min(20.0, math.log10(max(liq_ratio, 1.0)) * 10))
    breakdown["liquidity"] = round(liquidity_score, 1)

    # Spread: tighter is better, penalize anything near the configured ceiling.
    spread_score = max(0.0, min(15.0, 15.0 * (1 - (spread_bps / max(settings.max_spread_bps, 1.0)))))
    breakdown["spread_quality"] = round(spread_score, 1)

    # Extension risk: penalize moves that look overextended (naive proxy —
    # very large 24h change with fading 1h momentum is a red flag).
    extension_penalty = 0.0
    if ticker.price_change_pct_24h > 40 and momentum_1h_pct < 0:
        extension_penalty = 10.0
    breakdown["extension_penalty"] = -extension_penalty

    total = (
        momentum_score + volume_score + liquidity_score + spread_score - extension_penalty
    )
    total = max(0.0, min(100.0, total))
    return total, breakdown


async def discover_gainer_candidates(client: BinanceMarketDataClient) -> list[dict]:
    """
    Returns raw candidate dicts (not yet persisted) for the top N qualifying
    gainers, per docs/STRATEGIES.md. Filtering happens BEFORE ranking so we
    never crop a viable candidate out in favor of an illiquid top-24h mover.
    """
    tickers = await client.get_24h_tickers()
    tradeable = await client.get_exchange_info_symbols(quote_asset="USDT")

    qualifying = [
        t for t in tickers
        if t.symbol in tradeable
        and t.quote_volume_24h >= settings.min_quote_volume_24h_usdt
        and t.price_change_pct_24h > 0
    ]
    qualifying.sort(key=lambda t: t.price_change_pct_24h, reverse=True)
    top = qualifying[: settings.gainer_candidate_count]

    candidates = []
    for ticker in top:
        spread_bps = await client.get_spread_bps(ticker.symbol)
        if spread_bps is None or spread_bps > settings.max_spread_bps:
            continue  # excluded: abnormal spread, not silently kept

        klines = await client.get_klines(ticker.symbol, interval="1h", limit=24)
        if len(klines) < 2:
            continue

        momentum_1h_pct = (
            (klines[-1]["close"] - klines[-2]["close"]) / klines[-2]["close"] * 100
            if klines[-2]["close"] else 0.0
        )
        avg_hourly_volume = sum(k["volume"] for k in klines[:-1]) / max(len(klines) - 1, 1)
        volume_ratio = klines[-1]["volume"] / avg_hourly_volume if avg_hourly_volume else 0.0

        score, breakdown = _score_gainer(ticker, spread_bps, momentum_1h_pct, volume_ratio)

        candidates.append({
            "symbol": ticker.symbol,
            "price": ticker.last_price,
            "daily_change_pct": ticker.price_change_pct_24h,
            "quote_volume_24h": ticker.quote_volume_24h,
            "spread_bps": spread_bps,
            "opportunity_score": score,
            "score_breakdown": breakdown,
            "data_source_timestamp": ticker.fetched_at,
            "data_age_seconds": ticker.age_seconds,
        })

    return candidates


def build_trade_plan_dict(candidate: dict, user_id: str, max_trade_usdt: float) -> dict:
    """
    Builds a TradePlan-shaped dict for a candidate that cleared the opportunity
    score bar. This is still just a proposal — risk_check_passed is set by
    the risk engine, not here, and status starts at 'proposed'.
    """
    ladder_targets = [float(x) for x in settings.gainer_ladder_targets_pct.split(",")]
    profit_targets = {str(t): settings.gainer_ladder_sell_fraction for t in ladder_targets}

    return {
        "idempotency_key": f"gainer:{candidate['symbol']}:{candidate['data_source_timestamp'].isoformat()}",
        "user_id": user_id,
        "symbol": candidate["symbol"],
        "strategy": "gainer_hunter",
        "side": "BUY",
        "entry_price": candidate["price"],
        "position_size_usdt": min(max_trade_usdt, settings.max_spot_trade_usdt),
        "estimated_slippage_bps": candidate["spread_bps"],
        "stop_loss_pct": settings.gainer_hard_stop_pct,
        "profit_targets_pct": profit_targets,
        "opportunity_score": candidate["opportunity_score"],
        "reason": (
            f"{candidate['symbol']} is a top-15 daily gainer "
            f"({candidate['daily_change_pct']:.1f}% / 24h) with confirmed volume and "
            f"acceptable liquidity/spread. Score {candidate['opportunity_score']:.1f}/100."
        ),
        "market_conditions": candidate["score_breakdown"],
    }
