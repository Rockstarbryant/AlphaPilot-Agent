"""
Public Binance REST market-data adapter (Option A).

AlphaPilot no longer depends on Binance Agent OS MCP OAuth for market scans.
The hosted MCP endpoint is allowlisted to a few first-party clients; public
REST (`api.binance.com` / data endpoints) is the reliable path for regime
assessment and strategy discovery.

Return shapes match the previous MCP-backed client so strategies, regime
engine, and daily_market_reset keep working unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings

MAX_DATA_AGE_SECONDS = 30
settings = get_settings()


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
    """Public REST market data — no Agent OS OAuth required."""

    def __init__(self, connection: Any = None):
        # ``connection`` accepted for backward compatibility with call sites
        # that still pass BinanceConnectionData; it is ignored.
        self._base = (settings.binance_public_rest_base or "https://api.binance.com").rstrip("/")
        self._timeout = httpx.Timeout(20.0, connect=10.0)

    async def close(self):
        pass

    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, params=params or {})
            response.raise_for_status()
            return response.json()

    async def get_24h_tickers(self) -> list[TickerSnapshot]:
        raw = await self._get("/api/v3/ticker/24hr")
        now = datetime.now(timezone.utc)
        out: list[TickerSnapshot] = []
        if not isinstance(raw, list):
            return out
        for row in raw:
            try:
                out.append(
                    TickerSnapshot(
                        symbol=row["symbol"],
                        last_price=float(row["lastPrice"]),
                        price_change_pct_24h=float(row["priceChangePercent"]),
                        quote_volume_24h=float(row.get("quoteVolume") or 0),
                        fetched_at=now,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out

    async def get_exchange_info_symbols(self, quote_asset: str = "USDT") -> set[str]:
        raw = await self._get("/api/v3/exchangeInfo")
        symbols: set[str] = set()
        for s in raw.get("symbols") or []:
            if s.get("status") != "TRADING":
                continue
            if s.get("quoteAsset") != quote_asset:
                continue
            perms = s.get("permissions") or []
            if perms and "SPOT" not in perms:
                continue
            symbols.add(s["symbol"])
        return symbols

    async def get_order_book(self, symbol: str, limit: int = 5) -> dict:
        return await self._get("/api/v3/depth", {"symbol": symbol, "limit": limit})

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 24) -> list:
        return await self._get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )

    async def get_ticker_price(self, symbol: str) -> float:
        raw = await self._get("/api/v3/ticker/price", {"symbol": symbol})
        return float(raw["price"])
