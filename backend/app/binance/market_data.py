"""
Public Binance REST market-data adapter (Option A).

Uses the market-data-only host when possible so cloud datacenter IPs
(e.g. Render) are less likely to get HTTP 418 from api.binance.com.

Normalizes klines to dict rows ({close, volume, ...}) so strategies that
were written against dict-shaped candles keep working.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings

MAX_DATA_AGE_SECONDS = 30
settings = get_settings()

# Prefer vision data host for unauthenticated market data from cloud hosts.
_DEFAULT_BASES = (
    "https://data-api.binance.vision",
    "https://api.binance.com",
)


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


def _normalize_kline(row: Any) -> dict[str, float] | None:
    """REST array or dict → {open, high, low, close, volume}."""
    try:
        if isinstance(row, (list, tuple)) and len(row) >= 6:
            return {
                "open_time": float(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        if isinstance(row, dict):
            close = row.get("close", row.get("c"))
            volume = row.get("volume", row.get("v", row.get("baseVolume", 0)))
            if close is None:
                return None
            return {
                "open_time": float(row.get("open_time") or row.get("t") or 0),
                "open": float(row.get("open", row.get("o", close))),
                "high": float(row.get("high", row.get("h", close))),
                "low": float(row.get("low", row.get("l", close))),
                "close": float(close),
                "volume": float(volume or 0),
            }
    except (TypeError, ValueError, IndexError):
        return None
    return None


class BinanceMarketDataClient:
    """Public REST market data — no Agent OS OAuth required."""

    def __init__(self, connection: Any = None):
        configured = (settings.binance_public_rest_base or "").rstrip("/")
        if configured and configured not in _DEFAULT_BASES:
            self._bases = (configured, *_DEFAULT_BASES)
        elif configured:
            # Put configured first, then the other default
            self._bases = (configured,) + tuple(b for b in _DEFAULT_BASES if b != configured)
        else:
            self._bases = _DEFAULT_BASES
        self._timeout = httpx.Timeout(30.0, connect=10.0)
        self._working_base: str | None = None

    async def close(self):
        pass

    async def _get(self, path: str, params: dict | None = None) -> Any:
        last_error: Exception | None = None
        bases = [self._working_base] if self._working_base else list(self._bases)
        # Always allow fallback if preferred fails
        for b in self._bases:
            if b not in bases:
                bases.append(b)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for base in bases:
                if not base:
                    continue
                url = f"{base}{path}"
                try:
                    response = await client.get(url, params=params or {})
                    # 418 = WAF/geo teapot; try next host
                    if response.status_code == 418:
                        last_error = httpx.HTTPStatusError(
                            f"418 from {base}",
                            request=response.request,
                            response=response,
                        )
                        continue
                    response.raise_for_status()
                    self._working_base = base
                    return response.json()
                except Exception as exc:
                    last_error = exc
                    continue
        raise RuntimeError(f"Binance public market data failed for {path}: {last_error}")

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

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 24) -> list[dict]:
        raw = await self._get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        out: list[dict] = []
        if not isinstance(raw, list):
            return out
        for row in raw:
            norm = _normalize_kline(row)
            if norm:
                out.append(norm)
        return out

    async def get_ticker_price(self, symbol: str) -> float:
        raw = await self._get("/api/v3/ticker/price", {"symbol": symbol})
        return float(raw["price"])

    async def get_spread_bps(self, symbol: str) -> float:
        """Best bid/ask spread in basis points from the order book."""
        book = await self.get_order_book(symbol, limit=5)
        try:
            bid = float(book["bids"][0][0])
            ask = float(book["asks"][0][0])
        except (KeyError, IndexError, TypeError, ValueError):
            return 9999.0
        mid = (bid + ask) / 2.0
        if mid <= 0:
            return 9999.0
        return ((ask - bid) / mid) * 10_000.0
