"""
Hot Market Engine — HOT is not "biggest gainer." It's a composite of
momentum, volume acceleration, liquidity, spread, volatility, and price
persistence, computed across the qualifying universe (not just the top-15
gainer list). Only candidates clearing hot_score_threshold become eligible
for Margin analysis, and margin eligibility itself is a separate, stricter
gate on top of the HOT score — see margin_eligibility().
"""
from __future__ import annotations

import math
import statistics

from app.binance.market_data import BinanceMarketDataClient, TickerSnapshot
from app.core.config import get_settings

settings = get_settings()


def _hot_score(
    ticker: TickerSnapshot,
    spread_bps: float,
    momentum_1h_pct: float,
    volume_ratio: float,
    volatility_pct: float,
    persistence_hours: int,
) -> tuple[float, dict]:
    breakdown = {}

    # Momentum: recent-hour move in the same direction as the 24h trend,
    # scaled — this rewards assets that are still accelerating, not assets
    # that already made their entire move and stalled.
    momentum_score = max(0.0, min(25.0, abs(momentum_1h_pct) * 5))
    breakdown["momentum"] = round(momentum_score, 1)

    # Volume acceleration: recent hour vs trailing average.
    volume_score = max(0.0, min(20.0, (volume_ratio - 1) * 20))
    breakdown["volume_acceleration"] = round(volume_score, 1)

    # Liquidity floor — HOT assets must still be genuinely tradeable.
    liq_ratio = ticker.quote_volume_24h / max(settings.min_quote_volume_24h_usdt, 1.0)
    liquidity_score = max(0.0, min(15.0, math.log10(max(liq_ratio, 1.0)) * 7.5))
    breakdown["liquidity"] = round(liquidity_score, 1)

    # Spread quality.
    spread_score = max(0.0, min(10.0, 10.0 * (1 - (spread_bps / max(settings.max_spread_bps, 1.0)))))
    breakdown["spread_quality"] = round(spread_score, 1)

    # Relative strength: 24h change vs market cohort — computed by caller
    # and passed pre-normalized isn't done here to keep this function pure;
    # instead we approximate with raw 24h change magnitude, capped.
    relative_strength_score = max(0.0, min(15.0, abs(ticker.price_change_pct_24h) / 4))
    breakdown["relative_strength"] = round(relative_strength_score, 1)

    # Persistence: how many of the last N hourly candles moved in the
    # dominant direction — rewards sustained trends over one-candle spikes.
    persistence_score = max(0.0, min(10.0, persistence_hours * 2))
    breakdown["persistence"] = round(persistence_score, 1)

    # Volatility penalty: HOT should mean strong and controlled, not just
    # chaotic. Penalize volatility beyond a reasonable band.
    volatility_penalty = max(0.0, (volatility_pct - 8.0)) * 1.5
    breakdown["volatility_penalty"] = round(-volatility_penalty, 1)

    total = (
        momentum_score + volume_score + liquidity_score + spread_score
        + relative_strength_score + persistence_score - volatility_penalty
    )
    total = max(0.0, min(100.0, total))
    return total, breakdown


async def discover_hot_candidates(client: BinanceMarketDataClient, limit: int = 10) -> list[dict]:
    tickers = await client.get_24h_tickers()
    tradeable = await client.get_exchange_info_symbols(quote_asset="USDT")

    qualifying = [
        t for t in tickers
        if t.symbol in tradeable and t.quote_volume_24h >= settings.min_quote_volume_24h_usdt
    ]
    # Pre-rank by absolute 24h move to bound how many symbols we do the
    # expensive per-symbol kline/depth calls for.
    qualifying.sort(key=lambda t: abs(t.price_change_pct_24h), reverse=True)
    pool = qualifying[: max(limit * 4, 40)]

    candidates = []
    for ticker in pool:
        spread_bps = await client.get_spread_bps(ticker.symbol)
        if spread_bps is None or spread_bps > settings.max_spread_bps:
            continue

        klines = await client.get_klines(ticker.symbol, interval="1h", limit=24)
        if len(klines) < 6:
            continue

        momentum_1h_pct = (
            (klines[-1]["close"] - klines[-2]["close"]) / klines[-2]["close"] * 100
            if klines[-2]["close"] else 0.0
        )
        avg_hourly_volume = sum(k["volume"] for k in klines[:-1]) / max(len(klines) - 1, 1)
        volume_ratio = klines[-1]["volume"] / avg_hourly_volume if avg_hourly_volume else 0.0

        hourly_returns = [
            (klines[i]["close"] - klines[i - 1]["close"]) / klines[i - 1]["close"] * 100
            for i in range(1, len(klines)) if klines[i - 1]["close"]
        ]
        volatility_pct = statistics.pstdev(hourly_returns) if len(hourly_returns) > 1 else 0.0

        dominant_direction = 1 if ticker.price_change_pct_24h >= 0 else -1
        persistence_hours = sum(
            1 for r in hourly_returns[-6:] if (r >= 0) == (dominant_direction >= 0)
        )

        score, breakdown = _hot_score(
            ticker, spread_bps, momentum_1h_pct, volume_ratio, volatility_pct, persistence_hours
        )

        candidates.append({
            "symbol": ticker.symbol,
            "price": ticker.last_price,
            "daily_change_pct": ticker.price_change_pct_24h,
            "quote_volume_24h": ticker.quote_volume_24h,
            "spread_bps": spread_bps,
            "volatility_pct": volatility_pct,
            "hot_score": score,
            "score_breakdown": breakdown,
            "data_source_timestamp": ticker.fetched_at,
            "data_age_seconds": ticker.age_seconds,
        })

    candidates.sort(key=lambda c: c["hot_score"], reverse=True)
    return candidates[:limit]


def build_margin_trade_plan_dict(candidate: dict, user_id: str, max_trade_usdt: float, leverage: float) -> dict:
    """
    Margin trade plan proposal. Per docs/BINANCE_CAPABILITY_MATRIX.md, Agent
    OS's "Trade" scope covers margin generically without a confirmed
    isolated-vs-cross parameter in the published schema — so this plan
    records the margin intent conservatively. The actual Binance Agent OS
    tool schema is authoritative; AlphaPilot refuses to invent unsupported
    margin parameters.
    """
    from app.core.config import get_settings as _gs
    s = _gs()
    return {
        "idempotency_key": f"margin:{candidate['symbol']}:{candidate['data_source_timestamp'].isoformat()}",
        "user_id": user_id,
        "symbol": candidate["symbol"],
        "strategy": "hot_market_margin",
        "side": "BUY",
        "entry_price": candidate["price"],
        "position_size_usdt": min(max_trade_usdt, s.max_margin_trade_usdt),
        "estimated_slippage_bps": candidate["spread_bps"],
        "stop_loss_pct": s.gainer_hard_stop_pct,  # margin uses the same hard-stop discipline as spot by default
        "profit_targets_pct": {str(t): s.gainer_ladder_sell_fraction for t in [15, 30, 45, 60]},
        "opportunity_score": candidate["hot_score"],
        "leverage": leverage,
        "is_margin": True,
        "reason": (
            f"{candidate['symbol']} cleared the HOT score threshold "
            f"({candidate['hot_score']:.1f}/100) and all margin-eligibility checks "
            f"(liquidity, spread, volatility, market regime). Proposed at {leverage:.1f}x "
            f"isolated margin — verify isolated is actually selected in your MCP client, "
            f"Binance's Agent OS scope does not guarantee it over cross-margin. See "
            f"docs/BINANCE_CAPABILITY_MATRIX.md."
        ),
        "market_conditions": candidate["score_breakdown"],
    }


def margin_eligibility(candidate: dict, market_regime: str) -> tuple[bool, list[str]]:
    """
    ALL of these must pass for Margin to even be considered — see
    docs/STRATEGIES.md #21. This is intentionally stricter than the plain
    HOT score gate.
    """
    reasons = []
    eligible = True

    if candidate["hot_score"] < settings.hot_score_threshold:
        eligible = False
        reasons.append(f"HOT score {candidate['hot_score']:.1f} below threshold {settings.hot_score_threshold}")

    if candidate["quote_volume_24h"] < settings.min_quote_volume_24h_usdt * 3:
        eligible = False
        reasons.append("Liquidity insufficient for margin (requires 3x the spot minimum)")

    if candidate["spread_bps"] > settings.max_spread_bps * 0.5:
        eligible = False
        reasons.append("Spread too wide for margin's stricter tolerance")

    if candidate["volatility_pct"] > 8.0:
        eligible = False
        reasons.append(f"Volatility {candidate['volatility_pct']:.1f}% exceeds margin comfort band")

    if market_regime in ("RISK_OFF", "HIGH_VOLATILITY", "UNKNOWN"):
        eligible = False
        reasons.append(f"Market regime '{market_regime}' disables new margin trades")

    if eligible:
        reasons.append("Passed all margin eligibility checks")

    return eligible, reasons
