"""
Ad-hoc coin/token analysis — answers "what do you think about trading
BTC/USDT, should I long or short, or buy spot and hold?"

This is a multi-factor composite across every category in
docs/ADVISORY_REFACTOR.md's analysis matrix: technical (RSI/MACD/EMA-SMA/
Bollinger/support-resistance), market structure (HH-HL sequence, breaks of
structure), volume (VWAP, volume profile), order book (bid/ask imbalance,
walls), derivatives (funding rate, open interest, basis), on-chain (chain
TVL trend where applicable), sentiment (Fear & Greed + optional news), and
cross-market (BTC dominance, ETH/BTC, optional macro). See
app/market/composite_score.py for how these combine and
app/market/{structure,volume_profile,orderbook_analysis,derivatives,
onchain,sentiment,cross_market}.py for each category's own module.

Every category reports whether it actually had data — `coverage` in the
result tells you exactly how much of the matrix a given analysis drew on,
so "this bias is confident" always comes with "based on N/8 categories",
never a silent shortcut. app/agent/ai_provider.py is only used downstream,
by callers that want a plain-language narration of this same structured
result — nothing here reads an AI-produced number. This module never
touches Binance Agent OS or any account/auth-scoped endpoint; every piece
is public data, so it works even with no MCP connection or Binance account
at all (some categories degrade to "unavailable" without an optional free
API key — see each module's own docstring).
"""
from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.binance.market_data import BinanceMarketDataClient
from app.market import indicators as ind
from app.market import structure as struct_mod
from app.market import volume_profile as vol_mod
from app.market.composite_score import CategoryScore, build_composite
from app.market.cross_market import analyze_cross_market
from app.market.derivatives import analyze_derivatives
from app.market.onchain import analyze_onchain
from app.market.orderbook_analysis import analyze_order_book
from app.market.regime import assess_market_regime
from app.market.sentiment import get_fear_greed_index, get_news_sentiment

VALID_INTERVALS = {"15m", "1h", "4h", "1d"}
_KNOWN_QUOTES = ("USDT", "USDC", "BUSD", "BTC", "ETH", "BNB", "FDUSD")


def _extract_base(symbol: str) -> str:
    for quote in sorted(_KNOWN_QUOTES, key=len, reverse=True):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)]
    return symbol


@dataclass
class CoinAnalysis:
    symbol: str
    interval: str
    price: float
    price_change_pct_24h: float

    # --- Technical (RSI/MACD/momentum/moving averages/Bollinger/support-resistance) ---
    rsi: dict
    macd: dict
    momentum: dict
    moving_averages: dict
    bollinger: dict
    support_resistance: dict

    # --- Market structure ---
    structure: dict

    # --- Volume & liquidity ---
    vwap: dict
    volume_profile: dict

    # --- Order book (spot) ---
    order_book: dict

    # --- Derivatives (futures — funding/OI/basis) ---
    derivatives: dict

    # --- On-chain ---
    onchain: dict

    # --- Sentiment ---
    fear_greed: dict
    news_sentiment: dict

    # --- Cross-market / macro ---
    cross_market: dict

    # --- Regime (market-wide gate, same as before) ---
    market_regime: str
    regime_notes: str

    # --- Composite result (the headline bias/confidence, now multi-factor) ---
    bias: str  # LONG | SHORT | WAIT
    confidence: float  # 0-100
    composite_score: float  # -1..1 raw weighted vote
    categories_used: list[str]
    categories_missing: list[str]
    coverage_pct: float  # % of the full 8-category weighted matrix actually used
    model_type: str
    rationale: list[str]

    spot_guidance: str
    derivatives_guidance: str
    data_quality: str  # full | partial | insufficient — technical-signal quality specifically (legacy field, kept for callers that check it)
    klines_fetched: int
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """Use this instead of __dict__/vars() — several fields are nested
        dataclasses (via the category modules) before this call, and
        dataclasses.asdict recursively converts all of them to plain
        JSON-safe dicts/lists in one pass."""
        return dataclasses.asdict(self)


def _technical_score(
    rsi: ind.RSIResult, macd: ind.MACDResult, momentum: ind.MomentumResult,
    ma: ind.MAResult, bb: ind.BollingerResult,
) -> tuple[float, int, list[str]]:
    """Combines RSI/MACD/momentum/MA/Bollinger into one [-1,1] technical
    score plus how many of the 5 sub-signals actually resolved (used for
    both the legacy data_quality field and this category's own coverage)."""
    points = 0.0
    resolved = 0
    notes = []

    if rsi.signal == "OVERSOLD":
        points += 0.6; resolved += 1
        notes.append(f"RSI({rsi.period}) {rsi.value} is oversold.")
    elif rsi.signal == "OVERBOUGHT":
        points -= 0.6; resolved += 1
        notes.append(f"RSI({rsi.period}) {rsi.value} is overbought.")
    elif rsi.signal == "NEUTRAL" and rsi.value is not None:
        resolved += 1
        notes.append(f"RSI({rsi.period}) {rsi.value} is neutral.")

    if macd.crossover == "BULLISH_CROSS":
        points += 1.0; resolved += 1
        notes.append("MACD just crossed bullish.")
    elif macd.crossover == "BEARISH_CROSS":
        points -= 1.0; resolved += 1
        notes.append("MACD just crossed bearish.")
    elif macd.crossover == "BULLISH":
        points += 0.4; resolved += 1
        notes.append("MACD histogram positive.")
    elif macd.crossover == "BEARISH":
        points -= 0.4; resolved += 1
        notes.append("MACD histogram negative.")

    if momentum.direction == "UP":
        points += 0.5; resolved += 1
        notes.append(f"Momentum up {momentum.roc_pct}%.")
    elif momentum.direction == "DOWN":
        points -= 0.5; resolved += 1
        notes.append(f"Momentum down {momentum.roc_pct}%.")
    elif momentum.direction == "FLAT":
        resolved += 1

    if ma.trend == "UPTREND":
        points += 0.5; resolved += 1
        notes.append("Price above rising 20/50 moving averages.")
    elif ma.trend == "DOWNTREND":
        points -= 0.5; resolved += 1
        notes.append("Price below falling 20/50 moving averages.")
    elif ma.trend == "SIDEWAYS":
        resolved += 1
    if ma.golden_cross:
        points += 0.5
        notes.append("A golden cross (20MA above 50MA) just formed.")
    if ma.death_cross:
        points -= 0.5
        notes.append("A death cross (20MA below 50MA) just formed.")

    if bb.signal == "UPPER_BREAKOUT":
        points += 0.3
        notes.append("Price broke above its Bollinger Band — strong move, watch for mean-reversion.")
    elif bb.signal == "LOWER_BREAKOUT":
        points -= 0.3
        notes.append("Price broke below its Bollinger Band — strong move, watch for mean-reversion.")
    elif bb.signal == "SQUEEZE":
        notes.append("Bollinger Bands are squeezed tight — a big move often follows, direction unclear yet.")

    score = max(-1.0, min(1.0, points / 3.0))
    return score, resolved, notes


async def analyze_symbol(symbol: str, interval: str = "1h") -> CoinAnalysis:
    symbol = symbol.upper().replace("/", "")
    if interval not in VALID_INTERVALS:
        interval = "1h"
    base = _extract_base(symbol)

    spot_client = BinanceMarketDataClient(market_type="spot")
    try:
        regime_assessment, tickers, klines, order_book = await asyncio.gather(
            assess_market_regime(spot_client),
            spot_client.get_24h_tickers(),
            spot_client.get_klines(symbol, interval=interval, limit=150),
            spot_client.get_order_book(symbol, limit=100),
        )
    finally:
        await spot_client.close()

    ticker = next((t for t in tickers if t.symbol == symbol), None)
    price = ticker.last_price if ticker else (klines[-1]["close"] if klines else 0.0)

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]

    rsi = ind.compute_rsi(closes)
    macd = ind.compute_macd(closes)
    momentum = ind.compute_momentum(closes)
    ma = ind.compute_moving_averages(closes)
    bb = ind.compute_bollinger_bands(closes)
    sr = ind.compute_support_resistance(highs, lows, closes)
    market_structure = struct_mod.analyze_market_structure(highs, lows, closes)
    vwap = vol_mod.compute_vwap(klines)
    vol_profile = vol_mod.compute_volume_profile(klines)
    ob_analysis = analyze_order_book(order_book["bids"], order_book["asks"])

    # Independent external calls — run concurrently, each with its own
    # internal error handling (they return an "unavailable" result rather
    # than raising), so one slow/down provider never blocks the others.
    derivatives, onchain, fear_greed, news, cross_market = await asyncio.gather(
        analyze_derivatives(symbol, spot_price=price),
        analyze_onchain(base),
        get_fear_greed_index(),
        get_news_sentiment(base),
        analyze_cross_market(),
    )

    tech_score, tech_resolved, tech_notes = _technical_score(rsi, macd, momentum, ma, bb)
    data_quality = "full" if tech_resolved >= 4 else "partial" if tech_resolved > 0 else "insufficient"

    structure_score = 0.0
    if market_structure.sequence == "UPTREND":
        structure_score = 0.6
    elif market_structure.sequence == "DOWNTREND":
        structure_score = -0.6
    if market_structure.break_of_structure == "BULLISH_BOS":
        structure_score = min(1.0, structure_score + 0.4)
    elif market_structure.break_of_structure == "BEARISH_BOS":
        structure_score = max(-1.0, structure_score - 0.4)
    elif market_structure.change_of_character == "BULLISH_CHOCH":
        structure_score = 0.3
    elif market_structure.change_of_character == "BEARISH_CHOCH":
        structure_score = -0.3

    volume_score = 0.0
    if vwap.signal == "ABOVE_VWAP":
        volume_score += 0.4
    elif vwap.signal == "BELOW_VWAP":
        volume_score -= 0.4
    if vol_profile.signal == "ABOVE_VALUE_AREA":
        volume_score += 0.3
    elif vol_profile.signal == "BELOW_VALUE_AREA":
        volume_score -= 0.3
    volume_score = max(-1.0, min(1.0, volume_score))

    orderbook_score = 0.0
    if ob_analysis.imbalance_signal == "BID_HEAVY":
        orderbook_score = (ob_analysis.imbalance_ratio - 0.5) * 2
    elif ob_analysis.imbalance_signal == "ASK_HEAVY":
        orderbook_score = (ob_analysis.imbalance_ratio - 0.5) * 2

    # Funding is a CONTRARIAN signal — overheated long positioning tilts
    # bearish (crowded trade, squeeze risk), overheated short tilts bullish.
    derivatives_score = 0.0
    if derivatives.positioning_signal == "OVERHEATED_LONG":
        derivatives_score = -0.5
    elif derivatives.positioning_signal == "OVERHEATED_SHORT":
        derivatives_score = 0.5

    onchain_score = 0.0
    if onchain.signal == "RISING_TVL":
        onchain_score = 0.5
    elif onchain.signal == "FALLING_TVL":
        onchain_score = -0.5

    # Fear & Greed is also CONTRARIAN — extreme fear tilts bullish (capitulation),
    # extreme greed tilts bearish (euphoria/top risk).
    sentiment_score = 0.0
    if fear_greed.signal == "CONTRARIAN_BUY":
        sentiment_score += 0.5
    elif fear_greed.signal == "CONTRARIAN_CAUTION":
        sentiment_score -= 0.5
    if news.available and news.headline_count > 0:
        news_net = (news.bullish_count - news.bearish_count) / news.headline_count
        sentiment_score = max(-1.0, min(1.0, sentiment_score + news_net * 0.5))

    cross_market_score = 0.0
    if base != "BTC":  # BTC dominance/ETH-BTC are altcoin-relevant, not self-referential for BTC
        if cross_market.eth_btc_signal == "ALTS_LEADING":
            cross_market_score += 0.4
        elif cross_market.eth_btc_signal == "BTC_LEADING":
            cross_market_score -= 0.4

    categories = [
        CategoryScore("technical", tech_resolved > 0, tech_score, "; ".join(tech_notes) or "No technical signals resolved."),
        CategoryScore("structure", market_structure.sequence != "UNKNOWN", structure_score, market_structure.notes),
        CategoryScore("volume", vwap.signal != "UNKNOWN" or vol_profile.signal != "UNKNOWN", volume_score,
                      f"VWAP: {vwap.signal}; Volume profile: {vol_profile.signal}."),
        CategoryScore("orderbook", ob_analysis.imbalance_signal != "UNKNOWN", orderbook_score, ob_analysis.notes),
        CategoryScore("derivatives", derivatives.available, derivatives_score, derivatives.notes),
        CategoryScore("onchain", onchain.applicable and onchain.signal not in ("UNAVAILABLE",), onchain_score, onchain.notes),
        CategoryScore("sentiment", fear_greed.value is not None, sentiment_score,
                      f"Fear & Greed: {fear_greed.value} ({fear_greed.classification})." if fear_greed.value is not None else "Fear & Greed unavailable."),
        CategoryScore("cross_market", cross_market.btc_dominance_pct is not None, cross_market_score, cross_market.notes),
    ]
    composite = build_composite(categories)

    bias, confidence = composite.bias, composite.confidence
    rationale = list(composite.rationale)

    if bias == "LONG":
        spot_guidance = (
            "The multi-factor composite leans bullish. A spot buy-and-hold is the lower-risk way to "
            "express this — no liquidation risk, no funding/borrow cost."
        )
        derivatives_guidance = (
            f"If using derivatives: consider a LONG with tight risk sizing. {confidence}% confidence "
            f"is a weighted-signal-agreement score across {len(composite.categories_used)} categories, "
            "not a win-rate — always pair with a hard stop."
        )
    elif bias == "SHORT":
        spot_guidance = (
            "The multi-factor composite leans bearish. Spot can only express this by staying out or "
            "reducing an existing holding — spot has no native short."
        )
        derivatives_guidance = (
            f"If using derivatives: consider a SHORT with tight risk sizing. {confidence}% confidence "
            f"is a weighted-signal-agreement score across {len(composite.categories_used)} categories, "
            "not a win-rate — always pair with a hard stop."
        )
    else:
        if data_quality == "insufficient":
            spot_guidance = "AlphaPilot couldn't get enough recent price history for this symbol to form a technical view — try again shortly."
        else:
            spot_guidance = "No clean directional edge right now across enough categories — holding cash or an existing position is reasonable."
        derivatives_guidance = "Avoid opening new leveraged positions until more categories agree."

    return CoinAnalysis(
        symbol=symbol, interval=interval, price=price, price_change_pct_24h=ticker.price_change_pct_24h if ticker else 0.0,
        rsi={"value": rsi.value, "period": rsi.period, "signal": rsi.signal},
        macd={"macd": macd.macd, "signal_line": macd.signal_line, "histogram": macd.histogram, "crossover": macd.crossover},
        momentum={"roc_pct": momentum.roc_pct, "direction": momentum.direction},
        moving_averages=dataclasses.asdict(ma),
        bollinger=dataclasses.asdict(bb),
        support_resistance=dataclasses.asdict(sr),
        structure=dataclasses.asdict(market_structure),
        vwap=dataclasses.asdict(vwap),
        volume_profile=dataclasses.asdict(vol_profile),
        order_book=dataclasses.asdict(ob_analysis),
        derivatives=dataclasses.asdict(derivatives),
        onchain=dataclasses.asdict(onchain),
        fear_greed=dataclasses.asdict(fear_greed),
        news_sentiment=dataclasses.asdict(news),
        cross_market=dataclasses.asdict(cross_market),
        market_regime=regime_assessment.regime,
        regime_notes=regime_assessment.notes,
        bias=bias, confidence=confidence, composite_score=composite.composite_score,
        categories_used=composite.categories_used, categories_missing=composite.categories_missing,
        coverage_pct=composite.coverage_weight_pct, model_type=composite.model_type,
        rationale=rationale,
        spot_guidance=spot_guidance, derivatives_guidance=derivatives_guidance,
        data_quality=data_quality, klines_fetched=len(closes),
    )
