import pytest
import respx
from httpx import Response

from app.binance.market_data import BinanceMarketDataClient
from app.strategies import gainer, hot_market, recovery
from tests.fixtures.binance_samples import (
    EXCHANGE_INFO_SAMPLE, TICKER_24HR_SAMPLE, depth_sample, klines_sample,
)


def _mock_universe(mock):
    mock.get("/api/v3/ticker/24hr").mock(return_value=Response(200, json=TICKER_24HR_SAMPLE))
    mock.get("/api/v3/exchangeInfo").mock(return_value=Response(200, json=EXCHANGE_INFO_SAMPLE))
    # Tight spread for every symbol by default; individual tests can override.
    mock.get("/api/v3/depth").mock(return_value=Response(200, json=depth_sample(10.0, 10.02)))
    # Rising closes with increasing volume => healthy momentum + volume confirmation.
    closes = [10.0 + i * 0.05 for i in range(24)]
    volumes = [1000 + i * 50 for i in range(24)]
    mock.get("/api/v3/klines").mock(return_value=Response(200, json=klines_sample(closes, volumes)))


@pytest.mark.asyncio
async def test_gainer_hunter_excludes_illiquid_and_ranks_by_change():
    with respx.mock(base_url="https://api.binance.com") as mock:
        _mock_universe(mock)
        client = BinanceMarketDataClient()
        candidates = await gainer.discover_gainer_candidates(client)
        await client.close()

    symbols = [c["symbol"] for c in candidates]
    assert "DUSTUSDT" not in symbols  # excluded: below min_quote_volume_24h_usdt
    assert "ZORROUSDT" in symbols  # top gainer at +38.5%, liquid
    # Descending by 24h change among included candidates' source order
    assert candidates[0]["symbol"] == "ZORROUSDT"
    for c in candidates:
        assert 0 <= c["opportunity_score"] <= 100
        assert c["spread_bps"] is not None


@pytest.mark.asyncio
async def test_gainer_hunter_excludes_wide_spread_symbol():
    with respx.mock(base_url="https://api.binance.com", assert_all_called=False) as mock:
        mock.get("/api/v3/ticker/24hr").mock(return_value=Response(200, json=TICKER_24HR_SAMPLE))
        mock.get("/api/v3/exchangeInfo").mock(return_value=Response(200, json=EXCHANGE_INFO_SAMPLE))
        # Wide spread (way beyond max_spread_bps=50) should exclude every candidate
        # BEFORE the klines call — that route is deliberately never hit here.
        mock.get("/api/v3/depth").mock(return_value=Response(200, json=depth_sample(10.0, 12.0)))
        closes = [10.0 + i * 0.05 for i in range(24)]
        volumes = [1000] * 24
        mock.get("/api/v3/klines").mock(return_value=Response(200, json=klines_sample(closes, volumes)))

        client = BinanceMarketDataClient()
        candidates = await gainer.discover_gainer_candidates(client)
        await client.close()

    assert candidates == []


@pytest.mark.asyncio
async def test_recovery_hunter_targets_losers_only():
    with respx.mock(base_url="https://api.binance.com") as mock:
        _mock_universe(mock)
        client = BinanceMarketDataClient()
        candidates = await recovery.discover_recovery_candidates(client)
        await client.close()

    symbols = [c["symbol"] for c in candidates]
    assert "CRASHUSDT" in symbols  # -42%, the deepest loser
    assert "ZORROUSDT" not in symbols  # gainer, must never appear here
    for c in candidates:
        assert c["daily_change_pct"] < 0
        assert c["classification"] in ("HIGH_RECOVERY_POTENTIAL", "MEDIUM", "LOW", "AVOID")


@pytest.mark.asyncio
async def test_hot_market_scores_and_margin_eligibility():
    with respx.mock(base_url="https://api.binance.com") as mock:
        _mock_universe(mock)
        client = BinanceMarketDataClient()
        candidates = await hot_market.discover_hot_candidates(client, limit=5)
        await client.close()

    assert len(candidates) > 0
    for c in candidates:
        assert 0 <= c["hot_score"] <= 100

    # A candidate below the HOT threshold must never be margin-eligible,
    # regardless of market regime.
    low_score_candidate = {**candidates[0], "hot_score": 10.0}
    eligible, reasons = hot_market.margin_eligibility(low_score_candidate, "BULLISH")
    assert eligible is False
    assert any("HOT score" in r for r in reasons)

    # RISK_OFF regime must block margin even for an otherwise-excellent candidate.
    strong_candidate = {
        "hot_score": 95.0, "quote_volume_24h": 50_000_000, "spread_bps": 5.0, "volatility_pct": 1.0,
    }
    eligible_riskoff, reasons_riskoff = hot_market.margin_eligibility(strong_candidate, "RISK_OFF")
    assert eligible_riskoff is False
    assert any("regime" in r for r in reasons_riskoff)

    eligible_bullish, _ = hot_market.margin_eligibility(strong_candidate, "BULLISH")
    assert eligible_bullish is True
