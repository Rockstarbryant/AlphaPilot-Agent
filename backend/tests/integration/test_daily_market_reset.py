import uuid

import pytest
import respx
from httpx import Response
from sqlalchemy import select

from app.jobs.daily_market_reset import run_daily_market_reset
from app.models.models import AuditEvent, MarketCandidate, RiskPolicy, TradePlan, User
from tests.fixtures.binance_samples import (
    EXCHANGE_INFO_SAMPLE, TICKER_24HR_SAMPLE, depth_sample, klines_sample,
)


def _mock_binance(mock):
    mock.get("/api/v3/ticker/24hr").mock(return_value=Response(200, json=TICKER_24HR_SAMPLE))
    mock.get("/api/v3/exchangeInfo").mock(return_value=Response(200, json=EXCHANGE_INFO_SAMPLE))
    mock.get("/api/v3/depth").mock(return_value=Response(200, json=depth_sample(10.0, 10.02)))
    closes = [10.0 + i * 0.05 for i in range(24)]
    volumes = [1000 + i * 50 for i in range(24)]
    mock.get("/api/v3/klines").mock(return_value=Response(200, json=klines_sample(closes, volumes)))


# db_session fixture now lives in tests/conftest.py, shared across all test
# files — see its docstring for why the local per-file version each test
# file used to define was silently leaking committed rows into the real
# dev database.


@pytest.fixture
async def user_with_policy(db_session):
    user = User(id=str(uuid.uuid4()), email=f"test-{uuid.uuid4()}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(RiskPolicy(
        user_id=user.id, max_spot_trade_usdt=100, max_spot_allocation_pct=10,
        max_margin_trade_usdt=30, max_margin_allocation_pct=3, max_leverage=3,
        max_daily_loss_pct=5, max_slippage_bps=50, min_opportunity_score=1,  # low bar so fixtures qualify
        min_recovery_score=1, hot_score_threshold=1, gainer_hard_stop_pct=-20,
        recovery_hard_stop_pct=-20, recovery_take_profit_pct=25, trading_reserve_pct=40,
    ))
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_daily_market_reset_creates_session_candidates_and_plans(db_session, user_with_policy):
    with respx.mock(base_url="https://api.binance.com") as mock:
        _mock_binance(mock)
        session = await run_daily_market_reset(db_session, user_id=user_with_policy.id)

    assert session.status == "completed"
    assert session.market_regime is not None
    assert session.gainers_scanned > 0

    candidates = (await db_session.execute(
        select(MarketCandidate).where(MarketCandidate.session_id == session.id)
    )).scalars().all()
    assert len(candidates) > 0

    plans = (await db_session.execute(
        select(TradePlan).where(TradePlan.user_id == user_with_policy.id)
    )).scalars().all()
    assert len(plans) > 0
    # every plan must carry a risk decision, never silently skip validation
    assert all(p.risk_check_notes is not None for p in plans)

    audit = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert any(a.action == "market_regime_assessed" for a in audit)
    assert any(a.action == "trade_plan_created" for a in audit)


@pytest.mark.asyncio
async def test_missing_risk_policy_refuses_to_run(db_session):
    with pytest.raises(RuntimeError, match="No RiskPolicy configured"):
        await run_daily_market_reset(db_session, user_id=str(uuid.uuid4()))
