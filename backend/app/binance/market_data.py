"""
Binance public market data — Spot AND USDⓈ-M Futures, no API key, no Agent
OS session required. Endpoints verified against Binance's public REST APIs:

  Spot (api.binance.com / data-api.binance.vision):
    GET /api/v3/ticker/24hr   GET /api/v3/exchangeInfo
    GET /api/v3/depth         GET /api/v3/klines

  USDⓈ-M Futures (fapi.binance.com):
    GET /fapi/v1/ticker/24hr  GET /fapi/v1/exchangeInfo
    GET /fapi/v1/depth        GET /fapi/v1/klines

Same response shape for the fields this client reads, so one class serves
both — just pass market_type="futures" to point it at the futures host and
use futures' exchangeInfo eligibility fields instead of spot's.

This module is the public REST market-data adapter used by the scheduler,
app/market/coin_analysis.py, app/margin/analysis.py, and the position
monitor. It never places orders and never needs credentials. AlphaPilot
holds no direct Binance Agent OS connection at all — account/trading state
only ever arrives via app/services/account_context.py, reported by an
allowlisted AI client (see BINANCE_AGENT_OS_REFACTOR.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings

settings = get_settings()

MAX_DATA_AGE_SECONDS = 30

MarketType = Literal["spot", "futures"]

_FUTURES_BASE_URL = "https://fapi.binance.com"


@dataclass
class TickerSnapshot:
    symbol: str
    last_price: float
    price_change_pct_24h: float
    quote_volume_24h: float
    fetched_at: datetime

    @property
    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.fetched_at).total_seconds()

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > MAX_DATA_AGE_SECONDS


class StaleMarketDataError(RuntimeError):
    pass


class BinanceMarketDataClient:
    def __init__(self, base_url: str | None = None, market_type: MarketType = "spot"):
        self.market_type = market_type
        if base_url:
            self.base_url = base_url
        elif market_type == "futures":
            self.base_url = _FUTURES_BASE_URL
        else:
            self.base_url = settings.binance_public_rest_base
        self._ticker_path = "/fapi/v1/ticker/24hr" if market_type == "futures" else "/api/v3/ticker/24hr"
        self._exchange_info_path = "/fapi/v1/exchangeInfo" if market_type == "futures" else "/api/v3/exchangeInfo"
        self._depth_path = "/fapi/v1/depth" if market_type == "futures" else "/api/v3/depth"
        self._klines_path = "/fapi/v1/klines" if market_type == "futures" else "/api/v3/klines"
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def close(self):
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=5))
    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        resp = await self._client.get(path, params=params or {})
        if resp.status_code == 429 or resp.status_code == 418:
            # Binance rate-limit / IP-ban signal — let tenacity back off and retry.
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    async def get_24h_tickers(self) -> list[TickerSnapshot]:
        """All symbols' 24h stats in a single call (weight-efficient)."""
        raw = await self._get(self._ticker_path)
        now = datetime.now(timezone.utc)
        out = []
        for row in raw:
            try:
                out.append(
                    TickerSnapshot(
                        symbol=row["symbol"],
                        last_price=float(row["lastPrice"]),
                        price_change_pct_24h=float(row["priceChangePercent"]),
                        quote_volume_24h=float(row["quoteVolume"]),
                        fetched_at=now,
                    )
                )
            except (KeyError, ValueError):
                continue  # skip malformed rows rather than failing the whole scan
        return out

    async def get_exchange_info_symbols(self, quote_asset: str = "USDT") -> set[str]:
        """Tradeable symbols against a quote asset. Spot excludes non-SPOT/
        halted symbols; futures excludes anything that isn't a live
        perpetual contract (delivery/quarterly contracts expire, which
        would silently break a strategy holding one past expiry)."""
        raw = await self._get(self._exchange_info_path)
        symbols = set()
        for s in raw.get("symbols", []):
            if s.get("status") != "TRADING" or s.get("quoteAsset") != quote_asset:
                continue
            if self.market_type == "futures":
                if s.get("contractType") == "PERPETUAL":
                    symbols.add(s["symbol"])
            elif s.get("isSpotTradingAllowed", True):
                symbols.add(s["symbol"])
        return symbols

    async def get_spread_bps(self, symbol: str) -> float | None:
        """Best bid/ask spread in basis points from the order book top level."""
        raw = await self._get(self._depth_path, params={"symbol": symbol, "limit": 5})
        bids, asks = raw.get("bids"), raw.get("asks")
        if not bids or not asks:
            return None
        best_bid, best_ask = float(bids[0][0]), float(asks[0][0])
        mid = (best_bid + best_ask) / 2
        if mid <= 0:
            return None
        return ((best_ask - best_bid) / mid) * 10_000

    async def get_order_book(self, symbol: str, limit: int = 100) -> dict:
        """Full order book snapshot — [price, quantity] pairs, best price
        first on each side. `limit` can be 5/10/20/50/100/500/1000/5000 per
        Binance's accepted depth-limit values; 100 is enough for imbalance/
        wall detection without the heavier weight of the largest snapshots."""
        raw = await self._get(self._depth_path, params={"symbol": symbol, "limit": limit})
        return {
            "bids": [[float(p), float(q)] for p, q in raw.get("bids", [])],
            "asks": [[float(p), float(q)] for p, q in raw.get("asks", [])],
        }

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 24) -> list[dict]:
        raw = await self._get(
            self._klines_path, params={"symbol": symbol, "interval": interval, "limit": limit}
        )
        return [
            {
                "open_time": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in raw
        ]

    # --- Futures-only: derivatives data (app/market/derivatives.py) ---
    # All three are public market-data endpoints (no API key needed) per
    # Binance's futures docs — see docs/BINANCE_CAPABILITY_MATRIX.md.

    async def get_premium_index(self, symbol: str) -> dict:
        """Mark price + current funding rate + next funding time.
        GET /fapi/v1/premiumIndex — futures only."""
        if self.market_type != "futures":
            raise ValueError("get_premium_index is only available for market_type='futures'.")
        raw = await self._get("/fapi/v1/premiumIndex", params={"symbol": symbol})
        return {
            "mark_price": float(raw["markPrice"]),
            "index_price": float(raw["indexPrice"]),
            "last_funding_rate": float(raw["lastFundingRate"]),
            "next_funding_time": int(raw["nextFundingTime"]),
        }

    async def get_funding_rate_history(self, symbol: str, limit: int = 24) -> list[dict]:
        """GET /fapi/v1/fundingRate — futures only. Most recent `limit`
        settlements (funding settles every 8h on Binance, so 24 rows is ~8 days)."""
        if self.market_type != "futures":
            raise ValueError("get_funding_rate_history is only available for market_type='futures'.")
        raw = await self._get("/fapi/v1/fundingRate", params={"symbol": symbol, "limit": limit})
        return [{"funding_time": int(r["fundingTime"]), "funding_rate": float(r["fundingRate"])} for r in raw]

    async def get_open_interest(self, symbol: str) -> float | None:
        """Current open interest in contracts. GET /fapi/v1/openInterest — futures only."""
        if self.market_type != "futures":
            raise ValueError("get_open_interest is only available for market_type='futures'.")
        raw = await self._get("/fapi/v1/openInterest", params={"symbol": symbol})
        try:
            return float(raw["openInterest"])
        except (KeyError, ValueError, TypeError):
            return None
