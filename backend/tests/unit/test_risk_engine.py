import pytest

from app.models.models import RiskPolicy
from app.risk.engine import RiskEngine, TradeIntent


@pytest.fixture
def policy():
    return RiskPolicy(
        user_id="u1", max_spot_trade_usdt=100, max_spot_allocation_pct=10,
        max_margin_trade_usdt=30, max_margin_allocation_pct=3, max_leverage=3,
        max_daily_loss_pct=5, max_slippage_bps=50, min_opportunity_score=65,
        min_recovery_score=65, hot_score_threshold=85, gainer_hard_stop_pct=-20,
        recovery_hard_stop_pct=-20, recovery_take_profit_pct=25, trading_reserve_pct=40,
    )


@pytest.fixture
def base_intent():
    return TradeIntent(
        symbol="BNBUSDT", strategy="gainer_hunter", position_size_usdt=75, entry_price=600,
        estimated_slippage_bps=10, stop_loss_pct=-20, opportunity_score=80, data_age_seconds=5,
    )


def _validate(engine, intent, **overrides):
    defaults = dict(
        current_portfolio_value_usdt=1000, current_open_exposure_usdt=0,
        current_margin_exposure_usdt=0, realized_daily_loss_pct=0,
        open_positions_for_symbol=0, pending_plans_for_symbol=0, emergency_halted=False,
    )
    defaults.update(overrides)
    return engine.validate(intent, **defaults)


def test_valid_trade_passes(policy, base_intent):
    result = _validate(RiskEngine(policy), base_intent)
    assert result.passed
    assert result.notes == {}


def test_oversized_trade_fails(policy, base_intent):
    base_intent.position_size_usdt = 500
    result = _validate(RiskEngine(policy), base_intent)
    assert not result.passed
    assert "max_trade_size" in result.notes


def test_stale_data_blocks_trade(policy, base_intent):
    base_intent.data_age_seconds = 999
    result = _validate(RiskEngine(policy), base_intent)
    assert not result.passed
    assert "stale_data" in result.notes


def test_emergency_halt_blocks_everything(policy, base_intent):
    result = _validate(RiskEngine(policy), base_intent, emergency_halted=True)
    assert not result.passed
    assert result.notes["emergency_stop"]


def test_duplicate_open_position_blocks_trade(policy, base_intent):
    result = _validate(RiskEngine(policy), base_intent, open_positions_for_symbol=1)
    assert not result.passed
    assert "duplicate_position" in result.notes


def test_duplicate_pending_plan_blocks_trade(policy, base_intent):
    result = _validate(RiskEngine(policy), base_intent, pending_plans_for_symbol=1)
    assert not result.passed
    assert "duplicate_pending" in result.notes


def test_daily_loss_circuit_breaker(policy, base_intent):
    result = _validate(RiskEngine(policy), base_intent, realized_daily_loss_pct=-6)
    assert not result.passed
    assert "daily_loss_limit" in result.notes


def test_score_below_floor_blocks_trade(policy, base_intent):
    base_intent.opportunity_score = 40
    result = _validate(RiskEngine(policy), base_intent)
    assert not result.passed
    assert "min_score" in result.notes


def test_recovery_uses_recovery_score_floor(policy, base_intent):
    base_intent.strategy = "recovery_hunter"
    base_intent.opportunity_score = 70  # above gainer floor logic irrelevant; recovery floor is 65
    result = _validate(RiskEngine(policy), base_intent)
    assert result.passed


def test_excessive_slippage_blocks_trade(policy, base_intent):
    base_intent.estimated_slippage_bps = 200
    result = _validate(RiskEngine(policy), base_intent)
    assert not result.passed
    assert "max_slippage" in result.notes


def test_margin_leverage_over_limit_blocks_trade(policy, base_intent):
    base_intent.is_margin = True
    base_intent.leverage = 5
    base_intent.position_size_usdt = 20
    result = _validate(RiskEngine(policy), base_intent)
    assert not result.passed
    assert "max_leverage" in result.notes


def test_hard_stop_static_check():
    policy_obj = RiskPolicy(user_id="u1", gainer_hard_stop_pct=-20, recovery_hard_stop_pct=-15)
    assert RiskEngine.check_hard_stop("gainer_hunter", -21, policy_obj) is True
    assert RiskEngine.check_hard_stop("gainer_hunter", -19, policy_obj) is False
    assert RiskEngine.check_hard_stop("recovery_hunter", -16, policy_obj) is True
