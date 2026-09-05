"""
Fixtures shaped exactly like real Binance public REST responses (field names
and types verified against developers.binance.com/en/docs/binance-spot-api-docs).
Used only in tests/ — never mixed into production code paths. See
docs/BINANCE_CAPABILITY_MATRIX.md and the "no fake data" rule in
docs/HACKATHON_DEMO.md: this fixture data never reaches a real user-facing
response, only test assertions.
"""

TICKER_24HR_SAMPLE = [
    {
        "symbol": "BTCUSDT", "priceChange": "450.00", "priceChangePercent": "1.20",
        "lastPrice": "38250.50", "quoteVolume": "980000000.00", "openPrice": "37800.00",
    },
    {
        "symbol": "ZORROUSDT", "priceChange": "0.045", "priceChangePercent": "38.50",
        "lastPrice": "0.162", "quoteVolume": "12500000.00", "openPrice": "0.117",
    },
    {
        "symbol": "NOVAUSDT", "priceChange": "0.80", "priceChangePercent": "22.10",
        "lastPrice": "4.42", "quoteVolume": "8200000.00", "openPrice": "3.62",
    },
    {
        "symbol": "DUSTUSDT", "priceChange": "0.0001", "priceChangePercent": "15.00",
        "lastPrice": "0.00077", "quoteVolume": "45000.00", "openPrice": "0.00067",  # illiquid, must be excluded
    },
    {
        "symbol": "SLIDEUSDT", "priceChange": "-1.10", "priceChangePercent": "-18.40",
        "lastPrice": "4.88", "quoteVolume": "6100000.00", "openPrice": "5.98",
    },
    {
        "symbol": "CRASHUSDT", "priceChange": "-9.00", "priceChangePercent": "-42.00",
        "lastPrice": "12.40", "quoteVolume": "3300000.00", "openPrice": "21.40",
    },
    {
        "symbol": "FLATUSDT", "priceChange": "0.01", "priceChangePercent": "0.30",
        "lastPrice": "3.35", "quoteVolume": "2000000.00", "openPrice": "3.34",
    },
]

EXCHANGE_INFO_SAMPLE = {
    "symbols": [
        {"symbol": "BTCUSDT", "status": "TRADING", "quoteAsset": "USDT", "isSpotTradingAllowed": True},
        {"symbol": "ZORROUSDT", "status": "TRADING", "quoteAsset": "USDT", "isSpotTradingAllowed": True},
        {"symbol": "NOVAUSDT", "status": "TRADING", "quoteAsset": "USDT", "isSpotTradingAllowed": True},
        {"symbol": "DUSTUSDT", "status": "TRADING", "quoteAsset": "USDT", "isSpotTradingAllowed": True},
        {"symbol": "SLIDEUSDT", "status": "TRADING", "quoteAsset": "USDT", "isSpotTradingAllowed": True},
        {"symbol": "CRASHUSDT", "status": "TRADING", "quoteAsset": "USDT", "isSpotTradingAllowed": True},
        {"symbol": "FLATUSDT", "status": "TRADING", "quoteAsset": "USDT", "isSpotTradingAllowed": True},
        {"symbol": "HALTEDUSDT", "status": "BREAK", "quoteAsset": "USDT", "isSpotTradingAllowed": True},
    ]
}


def depth_sample(best_bid: float, best_ask: float) -> dict:
    return {
        "bids": [[f"{best_bid:.8f}", "10.0"]],
        "asks": [[f"{best_ask:.8f}", "10.0"]],
    }


def klines_sample(closes: list[float], volumes: list[float]) -> list[list]:
    """Builds klines rows in Binance's raw array format: [open_time, open, high, low, close, volume, ...]."""
    rows = []
    prev_close = closes[0]
    for i, (c, v) in enumerate(zip(closes, volumes)):
        o = prev_close
        h = max(o, c) * 1.001
        l = min(o, c) * 0.999
        rows.append([1700000000000 + i * 3600000, str(o), str(h), str(l), str(c), str(v), 0, "0", 0, "0", "0", "0"])
        prev_close = c
    return rows
