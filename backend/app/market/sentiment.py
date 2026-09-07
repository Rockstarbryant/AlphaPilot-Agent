"""
Sentiment — market-wide Fear & Greed, plus an optional news headline feed.

The Fear & Greed Index (alternative.me) is free, public, and needs no API
key — it's a genuine, real-time, market-wide contrarian-sentiment gauge and
is implemented in full. News/social sentiment (headlines, X, Reddit) has no
equivalent free, keyless, reliable source — implemented as a pluggable
provider (CRYPTOPANIC_API_KEY) that degrades honestly to "not configured"
rather than a fake/empty result, same pattern as app/earn/scanner.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings

settings = get_settings()

FNG_URL = "https://api.alternative.me/fng/"
CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"


@dataclass
class FearGreedResult:
    value: int | None  # 0-100
    classification: str  # e.g. "Extreme Fear", "Neutral", "Extreme Greed"
    signal: str  # CONTRARIAN_BUY | CONTRARIAN_CAUTION | NEUTRAL | UNKNOWN
    unavailable_reason: str | None


async def get_fear_greed_index() -> FearGreedResult:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(FNG_URL, params={"limit": 1})
        resp.raise_for_status()
        raw = resp.json()
        entry = raw["data"][0]
        value = int(entry["value"])
        classification = entry["value_classification"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        return FearGreedResult(None, "UNKNOWN", "UNKNOWN", f"Fear & Greed index request failed: {exc}")

    # Classic contrarian read: extreme fear often marks capitulation (a
    # tactical buy zone), extreme greed often marks euphoria (a caution
    # zone) — this is a market-wide input, not symbol-specific, so it's one
    # of several inputs to the composite score, never the whole story.
    if value <= 25:
        signal = "CONTRARIAN_BUY"
    elif value >= 75:
        signal = "CONTRARIAN_CAUTION"
    else:
        signal = "NEUTRAL"

    return FearGreedResult(value=value, classification=classification, signal=signal, unavailable_reason=None)


@dataclass
class NewsSentimentResult:
    available: bool
    headline_count: int
    bullish_count: int
    bearish_count: int
    top_headlines: list[str]
    unavailable_reason: str | None


async def get_news_sentiment(symbol_base: str) -> NewsSentimentResult:
    """`symbol_base` is the coin part only (e.g. "BTC" from "BTCUSDT")."""
    api_key = getattr(settings, "cryptopanic_api_key", "") or ""
    if not api_key:
        return NewsSentimentResult(
            False, 0, 0, 0, [],
            "CRYPTOPANIC_API_KEY is not set. Get a free key at cryptopanic.com/developers/api/ to enable "
            "headline sentiment — without it, news/social is skipped rather than faked.",
        )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                CRYPTOPANIC_URL,
                params={"auth_token": api_key, "currencies": symbol_base, "public": "true"},
            )
        resp.raise_for_status()
        raw = resp.json()
    except httpx.HTTPError as exc:
        return NewsSentimentResult(False, 0, 0, 0, [], f"News request failed: {exc}")

    results = raw.get("results", [])
    bullish = sum(1 for r in results if (r.get("votes") or {}).get("positive", 0) > (r.get("votes") or {}).get("negative", 0))
    bearish = sum(1 for r in results if (r.get("votes") or {}).get("negative", 0) > (r.get("votes") or {}).get("positive", 0))
    headlines = [r.get("title", "") for r in results[:5] if r.get("title")]

    return NewsSentimentResult(
        available=True, headline_count=len(results), bullish_count=bullish, bearish_count=bearish,
        top_headlines=headlines, unavailable_reason=None,
    )
