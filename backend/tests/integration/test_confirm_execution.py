import uuid

import pytest
from sqlalchemy import select

from app.models.models import (
    MarketCandidate, MarketSession, Position, RiskPolicy, StrategyType, TradePlan,
    TradePlanStatus, User,
)


# db_session fixture now lives in tests/conftest.py, shared across all test
# files — see its docstring.


@pytest.fixture
async def proposed_plan(db_session):
    user = User(id=str(uuid.uuid4()), email=f"t-{uuid.uuid4()}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    db_session.add(RiskPolicy(user_id=user.id))
    session = MarketSession(session_date=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    db_session.add(session)
    await db_session.flush()
    candidate = MarketCandidate(
        session_id=session.id, symbol="BTCUSDT", strategy=StrategyType.gainer_hunter,
        price=100.0, daily_change_pct=5.0, quote_volume_24h=1_000_000, spread_bps=5.0,
        opportunity_score=80.0, data_source_timestamp=session.session_date,
    )
    db_session.add(candidate)
    await db_session.flush()
    plan = TradePlan(
        candidate_id=candidate.id, user_id=user.id, symbol="BTCUSDT",
        strategy=StrategyType.gainer_hunter, entry_price=100.0, position_size_usdt=50.0,
        estimated_slippage_bps=5.0, stop_loss_pct=-20.0,
        profit_targets_pct={"15": 0.25, "30": 0.25}, opportunity_score=80.0, risk_score=100.0,
        reason="test", risk_check_passed=True, idempotency_key=str(uuid.uuid4()),
        status=TradePlanStatus.proposed,
    )
    db_session.add(plan)
    await db_session.commit()
    return plan


@pytest.mark.asyncio
async def test_confirm_execution_creates_position(db_session, proposed_plan):
    from app.api.routes.trade_plans import ConfirmExecutionRequest, confirm_execution

    result = await confirm_execution(
        proposed_plan.id, ConfirmExecutionRequest(binance_order_id="12345"), db_session
    )
    assert result["status"] == TradePlanStatus.open

    positions = (await db_session.execute(
        select(Position).where(Position.trade_plan_id == proposed_plan.id)
    )).scalars().all()
    assert len(positions) == 1
    pos = positions[0]
    assert pos.symbol == "BTCUSDT"
    assert pos.entry_price == 100.0
    assert pos.quantity == pytest.approx(0.5)  # $50 / $100
    assert pos.remaining_fraction == 1.0
    assert pos.profit_targets_pct == {"15": 0.25, "30": 0.25}


@pytest.mark.asyncio
async def test_confirm_execution_uses_actual_fill_price_when_given(db_session, proposed_plan):
    from app.api.routes.trade_plans import ConfirmExecutionRequest, confirm_execution

    await confirm_execution(
        proposed_plan.id,
        ConfirmExecutionRequest(binance_order_id="12345", fill_price=105.0, filled_quantity=0.476),
        db_session,
    )
    positions = (await db_session.execute(
        select(Position).where(Position.trade_plan_id == proposed_plan.id)
    )).scalars().all()
    assert positions[0].entry_price == 105.0
    assert positions[0].quantity == pytest.approx(0.476)
