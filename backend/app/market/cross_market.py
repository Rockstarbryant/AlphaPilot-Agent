"""
Cross-market / macro regime — the "what's the tide doing" read. An
individual coin's technicals matter less when BTC dominance is spiking
(risk-off within crypto, capital rotating out of alts) or when broad
macro (DXY/rates) is fighting every risk asset at once.

BTC dominance + total market cap: free via CoinGecko's keyless /global
endpoint (returns dominance directly, no manual computation needed).
ETH/BTC ratio: computed directly from Binance's own ETHBTC pair — no
external dependency at all for this one.
Traditional macro (DXY, Nasdaq, Gold): genuinely has no free/keyless
reliable source for a backend service — implemented as a pluggable
provider (ALPHA_VANTAGE_API_KEY, a real free-tier key from
alphavantage.co) that degrades honestly when not configured.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.binance.market_data import BinanceMarketDataClient
from app.core.config import get_settings

settings = get_settings()

COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"


@dataclass
class CrossMarketResult:
    btc_dominance_pct: float | None
    total_market_cap_usd: float | None
    eth_btc_ratio: float | None
    eth_btc_signal: str  # ALTS_LEADING | BTC_LEADING | NEUTRAL | UNKNOWN
    macro_available: bool
    dxy_note: str | None  # only populated if ALPHA_VANTAGE_API_KEY is set
    notes: str


async def analyze_cross_market() -> CrossMarketResult:
    btc_dominance = None
    total_mcap = None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(COINGECKO_GLOBAL_URL)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        btc_dominance = data.get("market_cap_percentage", {}).get("btc")
        total_mcap = data.get("total_market_cap", {}).get("usd")
    except httpx.HTTPError:
        pass  # degrade silently on this one piece; still return what else we have

    eth_btc_ratio = None
    eth_btc_signal = "UNKNOWN"
    spot_client = BinanceMarketDataClient(market_type="spot")
    try:
        tickers = await spot_client.get_24h_tickers()
        eth_btc = next((t for t in tickers if t.symbol == "ETHBTC"), None)
        if eth_btc:
            eth_btc_ratio = eth_btc.last_price
            # Rising ETH/BTC historically coincides with broader alt-season
            # risk appetite; falling means capital consolidating into BTC.
            if eth_btc.price_change_pct_24h > 1.0:
                eth_btc_signal = "ALTS_LEADING"
            elif eth_btc.price_change_pct_24h < -1.0:
                eth_btc_signal = "BTC_LEADING"
            else:
                eth_btc_signal = "NEUTRAL"
    finally:
        await spot_client.close()

    dxy_note = None
    macro_available = False
    av_key = getattr(settings, "alpha_vantage_api_key", "") or ""
    if av_key:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    ALPHA_VANTAGE_URL,
                    params={"function": "GLOBAL_QUOTE", "symbol": "DX-Y.NYB", "apikey": av_key},
                )
            resp.raise_for_status()
            quote = resp.json().get("Global Quote", {})
            change_pct = quote.get("10. change percent")
            if change_pct:
                macro_available = True
                dxy_note = f"DXY (US Dollar Index) {change_pct} today — a rising dollar is historically a headwind for crypto/risk assets."
        except httpx.HTTPError:
            pass

    notes_parts = []
    if btc_dominance is not None:
        notes_parts.append(f"BTC dominance is {btc_dominance:.1f}% of total crypto market cap.")
    if eth_btc_signal == "ALTS_LEADING":
        notes_parts.append("ETH is outperforming BTC over the last 24h — a mild alt-season signal.")
    elif eth_btc_signal == "BTC_LEADING":
        notes_parts.append("BTC is outperforming ETH over the last 24h — capital consolidating into BTC.")
    if dxy_note:
        notes_parts.append(dxy_note)
    elif not av_key:
        notes_parts.append(
            "Traditional macro (DXY/Nasdaq/Gold) needs ALPHA_VANTAGE_API_KEY (a free key from "
            "alphavantage.co) — not configured, so macro cross-checks are skipped rather than guessed."
        )

    return CrossMarketResult(
        btc_dominance_pct=round(btc_dominance, 2) if btc_dominance is not None else None,
        total_market_cap_usd=round(total_mcap, 0) if total_mcap is not None else None,
        eth_btc_ratio=eth_btc_ratio,
        eth_btc_signal=eth_btc_signal,
        macro_available=macro_available,
        dxy_note=dxy_note,
        notes=" ".join(notes_parts) if notes_parts else "Cross-market data unavailable right now.",
    )
