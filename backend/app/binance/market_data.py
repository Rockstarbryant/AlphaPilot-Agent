"""
Binance public Spot market data — no API key, no Agent OS session required.
Endpoints verified against Binance's public REST API (api.binance.com):
  GET /api/v3/ticker/24hr        - 24h stats for all symbols
  GET /api/v3/exchangeInfo       - tradeable symbols, filters
  GET /api/v3/depth              - order book (for spread calc)
  GET /api/v3/klines             - candlesticks

This module is the public REST market-data adapter used by the scheduler.
It never places orders and never needs credentials. Direct Binance Agent OS
account/trading calls live in agent_os_mcp_client.py and binance_agent_os.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings

settings = get_settings()

MAX_DATA_AGE_SECONDS = 30


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
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.binance_public_rest_base
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
        raw = await self._get("/api/v3/ticker/24hr")
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
        """Tradeable symbols against a quote asset, excluding non-SPOT / halted."""
        raw = await self._get("/api/v3/exchangeInfo")
        symbols = set()
        for s in raw.get("symbols", []):
            if (
                s.get("status") == "TRADING"
                and s.get("quoteAsset") == quote_asset
                and s.get("isSpotTradingAllowed", True)
            ):
                symbols.add(s["symbol"])
        return symbols

    async def get_spread_bps(self, symbol: str) -> float | None:
        """Best bid/ask spread in basis points from the order book top level."""
        raw = await self._get("/api/v3/depth", params={"symbol": symbol, "limit": 5})
        bids, asks = raw.get("bids"), raw.get("asks")
        if not bids or not asks:
            return None
        best_bid, best_ask = float(bids[0][0]), float(asks[0][0])
        mid = (best_bid + best_ask) / 2
        if mid <= 0:
            return None
        return ((best_ask - best_bid) / mid) * 10_000

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 24) -> list[dict]:
        raw = await self._get(
            "/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit}
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
