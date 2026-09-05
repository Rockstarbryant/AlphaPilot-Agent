"""
Binance Agent OS MCP market data adapter.

Market data is a *public, no-auth* scope on Binance's hosted Agent OS MCP
server (tickers, order books, candles, funding — see
https://developers.binance.com/en/docs/agent-native/mcp-server/agentic).
That means AlphaPilot can call it directly with no OAuth/connection at all —
no dynamic client registration, no per-user authorization.

This class is a drop-in replacement for the old direct-REST client: same
class name, same method names, same return shapes. Callers (regime engine,
daily market reset job, position monitor) do not need to change.

Binance's tool schema for market data isn't publicly documented in detail,
so BinanceAgentOSClient tries several likely tool-name candidates and falls
back to substring matching. If a call fails with "Required Binance
capability not exposed...", the error lists every tool the server actually
advertises — use that to correct the candidate list in agent_os_mcp_client.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.binance.agent_os_mcp_client import BinanceAgentOSClient

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
    def __init__(self):
        self._client = BinanceAgentOSClient()

    async def close(self):
        # BinanceAgentOSClient opens a fresh httpx.AsyncClient per RPC call
        # and closes it itself; nothing persistent to tear down here. Kept
        # so existing `await client.close()` call sites keep working.
        pass

    @staticmethod
    def _rows(raw) -> list[dict]:
        """MCP tool results may be a bare list or wrapped in a dict — handle both."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            for key in ("tickers", "symbols", "data", "result", "items"):
                if isinstance(raw.get(key), list):
                    return raw[key]
        return []

    async def get_24h_tickers(self) -> list[TickerSnapshot]:
        """All symbols' 24h stats."""
        raw = await self._client.get_24h_tickers()
        now = datetime.now(timezone.utc)
        out = []
        for row in self._rows(raw):
            try:
                out.append(
                    TickerSnapshot(
                        symbol=row["symbol"],
                        last_price=float(row.get("lastPrice", row.get("last_price"))),
                        price_change_pct_24h=float(
                            row.get("priceChangePercent", row.get("price_change_percent"))
                        ),
                        quote_volume_24h=float(row.get("quoteVolume", row.get("quote_volume", 0)) or 0),
                        fetched_at=now,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue  # skip malformed rows rather than failing the whole scan
        return out

    async def get_exchange_info_symbols(self, quote_asset: str = "USDT") -> set[str]:
        """Tradeable symbols against a quote asset, excluding non-SPOT / halted."""
        raw = await self._client.get_exchange_info()
        symbols = set()
        for s in self._rows(raw):
            status = s.get("status", "TRADING")
            quote = s.get("quoteAsset", s.get("quote_asset"))
            spot_allowed = s.get("isSpotTradingAllowed", s.get("is_spot_trading_allowed", True))
            if status == "TRADING" and quote == quote_asset and spot_allowed and s.get("symbol"):
                symbols.add(s["symbol"])
        return symbols

    async def get_spread_bps(self, symbol: str) -> float | None:
        """Best bid/ask spread in basis points from the order book top level."""
        raw = await self._client.get_order_book(symbol, limit=5)
        bids, asks = raw.get("bids"), raw.get("asks")
        if not bids or not asks:
            return None
        best_bid, best_ask = float(bids[0][0]), float(asks[0][0])
        mid = (best_bid + best_ask) / 2
        if mid <= 0:
            return None
        return ((best_ask - best_bid) / mid) * 10_000

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 24) -> list[dict]:
        raw = await self._client.get_klines(symbol, interval=interval, limit=limit)
        out = []
        for row in self._rows(raw) or (raw if isinstance(raw, list) else []):
            if isinstance(row, list):
                out.append(
                    {
                        "open_time": row[0],
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                )
            elif isinstance(row, dict):
                out.append(
                    {
                        "open_time": row.get("openTime", row.get("open_time")),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row.get("volume", 0) or 0),
                    }
                )
        return out