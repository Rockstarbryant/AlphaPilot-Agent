import pytest
import respx
from httpx import Response

from app.binance.market_data import BinanceMarketDataClient
from tests.fixtures.binance_samples import (
    EXCHANGE_INFO_SAMPLE, TICKER_24HR_SAMPLE, depth_sample, klines_sample,
)


@pytest.mark.asyncio
async def test_get_24h_tickers_parses_real_shape():
    with respx.mock(base_url="https://api.binance.com") as mock:
        mock.get("/api/v3/ticker/24hr").mock(return_value=Response(200, json=TICKER_24HR_SAMPLE))
        client = BinanceMarketDataClient()
        tickers = await client.get_24h_tickers()
        await client.close()

    assert len(tickers) == len(TICKER_24HR_SAMPLE)
    btc = next(t for t in tickers if t.symbol == "BTCUSDT")
    assert btc.last_price == 38250.50
    assert btc.price_change_pct_24h == 1.20
    assert not btc.is_stale


@pytest.mark.asyncio
async def test_get_exchange_info_excludes_halted_symbols():
    with respx.mock(base_url="https://api.binance.com") as mock:
        mock.get("/api/v3/exchangeInfo").mock(return_value=Response(200, json=EXCHANGE_INFO_SAMPLE))
        client = BinanceMarketDataClient()
        symbols = await client.get_exchange_info_symbols("USDT")
        await client.close()

    assert "BTCUSDT" in symbols
    assert "HALTEDUSDT" not in symbols  # status=BREAK, correctly excluded


@pytest.mark.asyncio
async def test_get_spread_bps_computes_correctly():
    with respx.mock(base_url="https://api.binance.com") as mock:
        mock.get("/api/v3/depth").mock(return_value=Response(200, json=depth_sample(100.0, 100.5)))
        client = BinanceMarketDataClient()
        spread = await client.get_spread_bps("BTCUSDT")
        await client.close()

    # (100.5 - 100.0) / 100.25 * 10000 ≈ 49.88 bps
    assert 49.0 < spread < 51.0


@pytest.mark.asyncio
async def test_retries_on_429(monkeypatch):
    call_count = {"n": 0}

    def responder(request):
        call_count["n"] += 1
        if call_count["n"] < 3:
            return Response(429, json={"code": -1003, "msg": "Too many requests"})
        return Response(200, json=TICKER_24HR_SAMPLE)

    with respx.mock(base_url="https://api.binance.com") as mock:
        mock.get("/api/v3/ticker/24hr").mock(side_effect=responder)
        client = BinanceMarketDataClient()
        tickers = await client.get_24h_tickers()
        await client.close()

    assert call_count["n"] == 3  # two 429s then success, per tenacity retry config
    assert len(tickers) == len(TICKER_24HR_SAMPLE)
