"""
Runs at 00:00 UTC (see docs/STRATEGIES.md — this is discovery time, not
forced execution time). Scans the market with all three discovery
strategies, gated by the Market Regime Engine, persists results, and for
candidates clearing their score bar, creates risk-validated TradePlan
proposals.

This job touches ONLY public Binance market data. It creates risk-validated
TradePlans but does not submit orders. Direct execution is a separate service
step owned by BinanceAgentOSService.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.binance.market_data import BinanceMarketDataClient
from app.core.config import get_settings
from app.market.regime import REGIME_STRATEGY_GATES, assess_market_regime
from app.models.models import (
    AccountSnapshot, AgentRun, AuditEvent, MarketCandidate, MarketSession, RiskPolicy, StrategyType, TradePlan,
)
from app.risk.engine import RiskEngine, TradeIntent
from app.services.notifications import notify
from app.strategies import gainer, hot_market, recovery

settings = get_settings()


async def _get_account_snapshot(db, user_id: str) -> AccountSnapshot | None:
    result = await db.execute(
        select(AccountSnapshot)
        .where(AccountSnapshot.user_id == user_id)
        .order_by(AccountSnapshot.reported_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _process_gainer(db, session_row, agent_run, policy, engine, client, snapshot) -> int:
    raw_candidates = await gainer.discover_gainer_candidates(client)
    created = 0
    for raw in raw_candidates:
        candidate = MarketCandidate(
            session_id=session_row.id, symbol=raw["symbol"], strategy=StrategyType.gainer_hunter,
            price=raw["price"], daily_change_pct=raw["daily_change_pct"],
            quote_volume_24h=raw["quote_volume_24h"], spread_bps=raw["spread_bps"],
            opportunity_score=raw["opportunity_score"], score_breakdown=raw["score_breakdown"],
            data_source_timestamp=raw["data_source_timestamp"],
        )
        if raw["opportunity_score"] < policy.min_opportunity_score:
            candidate.status = "watching"
            db.add(candidate)
            continue
        candidate.status = "qualified"
        db.add(candidate)
        await db.flush()

        plan_dict = gainer.build_trade_plan_dict(raw, policy.user_id, policy.max_spot_trade_usdt)
        created += await _validate_and_propose(
            db, candidate, agent_run, policy, engine, raw, plan_dict, StrategyType.gainer_hunter, snapshot=snapshot,
        )
    session_row.gainers_scanned = len(raw_candidates)
    return created


async def _process_recovery(db, session_row, agent_run, policy, engine, client, snapshot) -> int:
    raw_candidates = await recovery.discover_recovery_candidates(client)
    created = 0
    for raw in raw_candidates:
        candidate = MarketCandidate(
            session_id=session_row.id, symbol=raw["symbol"], strategy=StrategyType.recovery_hunter,
            price=raw["price"], daily_change_pct=raw["daily_change_pct"],
            quote_volume_24h=raw["quote_volume_24h"], spread_bps=raw["spread_bps"],
            opportunity_score=raw["recovery_score"], score_breakdown=raw["score_breakdown"],
            data_source_timestamp=raw["data_source_timestamp"],
        )
        if raw["classification"] in ("LOW", "AVOID") or raw["recovery_score"] < policy.min_recovery_score:
            candidate.status = "rejected" if raw["classification"] == "AVOID" else "watching"
            db.add(candidate)
            continue
        candidate.status = "qualified"
        db.add(candidate)
        await db.flush()

        plan_dict = recovery.build_trade_plan_dict(raw, policy.user_id, policy.max_spot_trade_usdt)
        created += await _validate_and_propose(
            db, candidate, agent_run, policy, engine, raw, plan_dict, StrategyType.recovery_hunter, snapshot=snapshot,
        )
    session_row.losers_scanned = len(raw_candidates)
    return created


async def _process_hot_market(db, session_row, agent_run, policy, engine, client, regime: str, snapshot) -> int:
    """
    HOT/Margin candidates are recorded for visibility even when margin is
    disabled by regime — the eligibility reasons are part of the audit
    trail (docs/STRATEGIES.md #21). Eligible candidates get a risk-validated
    margin TradePlan proposal, same discipline as Gainer/Recovery.
    """
    raw_candidates = await hot_market.discover_hot_candidates(client)
    found = 0
    created = 0
    for raw in raw_candidates:
        if raw["hot_score"] < policy.hot_score_threshold:
            continue
        found += 1
        eligible, reasons = hot_market.margin_eligibility(raw, regime)
        candidate = MarketCandidate(
            session_id=session_row.id, symbol=raw["symbol"], strategy=StrategyType.hot_market_margin,
            price=raw["price"], daily_change_pct=raw["daily_change_pct"],
            quote_volume_24h=raw["quote_volume_24h"], spread_bps=raw["spread_bps"],
            opportunity_score=raw["hot_score"], score_breakdown=raw["score_breakdown"],
            data_source_timestamp=raw["data_source_timestamp"],
            status="qualified" if eligible else "rejected",
            reason="; ".join(reasons),
        )
        db.add(candidate)
        db.add(AuditEvent(
            agent_run_id=agent_run.id, strategy="hot_market_margin", action="margin_eligibility_checked",
            asset=raw["symbol"], decision="MARGIN_ELIGIBLE" if eligible else "MARGIN_TRADE_BLOCKED",
            risk_result={"reasons": reasons}, status="ok",
        ))
        if eligible:
            await db.flush()
            plan_dict = hot_market.build_margin_trade_plan_dict(
                raw, policy.user_id, policy.max_margin_trade_usdt, min(policy.max_leverage, 2.0)
            )
            created += await _validate_and_propose(
                db, candidate, agent_run, policy, engine, raw, plan_dict, StrategyType.hot_market_margin,
                is_margin=True, leverage=plan_dict["leverage"], snapshot=snapshot,
            )
    session_row.hot_candidates_found = found
    return created


async def _validate_and_propose(
    db, candidate, agent_run, policy, engine, raw, plan_dict, strategy: StrategyType,
    is_margin: bool = False, leverage: float = 1.0, snapshot=None,
) -> int:
    intent = TradeIntent(
        symbol=plan_dict["symbol"], strategy=plan_dict["strategy"],
        position_size_usdt=plan_dict["position_size_usdt"], entry_price=plan_dict["entry_price"],
        estimated_slippage_bps=plan_dict["estimated_slippage_bps"], stop_loss_pct=plan_dict["stop_loss_pct"],
        opportunity_score=plan_dict["opportunity_score"], data_age_seconds=raw["data_age_seconds"],
        is_margin=is_margin, leverage=leverage,
    )
    # Portfolio-relative checks use the latest Agent OS-synchronized AccountSnapshot
    # (see app/api/routes/account.py) when one exists. With none reported
    # yet, we fall back to $0 — which makes every allocation-% check fail
    # closed (blocks the trade) rather than silently pass on a fabricated
    # balance. See docs/RISK_ENGINE.md.
    risk_result = engine.validate(
        intent,
        current_portfolio_value_usdt=snapshot.portfolio_value_usdt if snapshot else 0.0,
        current_open_exposure_usdt=snapshot.open_exposure_usdt if snapshot else 0.0,
        current_margin_exposure_usdt=snapshot.margin_exposure_usdt if snapshot else 0.0,
        realized_daily_loss_pct=snapshot.realized_daily_loss_pct if snapshot else 0.0,
        open_positions_for_symbol=0, pending_plans_for_symbol=0, emergency_halted=False,
    )
    trade_plan = TradePlan(
        candidate_id=candidate.id, user_id=policy.user_id, symbol=plan_dict["symbol"],
        strategy=strategy, side=plan_dict["side"], entry_price=plan_dict["entry_price"],
        position_size_usdt=plan_dict["position_size_usdt"],
        estimated_slippage_bps=plan_dict["estimated_slippage_bps"],
        stop_loss_pct=plan_dict["stop_loss_pct"], profit_targets_pct=plan_dict["profit_targets_pct"],
        opportunity_score=plan_dict["opportunity_score"],
        risk_score=100.0 - len([c for c in risk_result.checks.values() if not c]) * 15,
        reason=plan_dict["reason"], market_conditions=plan_dict["market_conditions"],
        risk_check_passed=risk_result.passed, risk_check_notes=risk_result.notes,
        idempotency_key=plan_dict["idempotency_key"],
        status="proposed" if risk_result.passed else "risk_rejected",
    )
    db.add(trade_plan)
    candidate.status = "trade_proposed" if risk_result.passed else "rejected"
    db.add(AuditEvent(
        agent_run_id=agent_run.id, strategy=strategy.value, action="trade_plan_created",
        asset=raw["symbol"], decision="proposed" if risk_result.passed else "risk_rejected",
        risk_result=risk_result.notes, status="ok",
    ))
    return 1


async def run_daily_market_reset(db: AsyncSession, user_id: str) -> MarketSession:
    session_row = MarketSession(session_date=datetime.now(timezone.utc), status="running")
    db.add(session_row)
    await db.flush()

    agent_run = AgentRun(strategy=StrategyType.gainer_hunter, status="running")
    db.add(agent_run)
    await db.flush()

    policy_result = await db.execute(select(RiskPolicy).where(RiskPolicy.user_id == user_id))
    policy = policy_result.scalar_one_or_none()
    if policy is None:
        raise RuntimeError(f"No RiskPolicy configured for user {user_id}; refusing to trade blind.")

    client = BinanceMarketDataClient()
    engine = RiskEngine(policy)
    proposals_created = 0
    snapshot = await _get_account_snapshot(db, user_id)
    try:
        regime_assessment = await assess_market_regime(client)
        session_row.market_regime = regime_assessment.regime
        gates = REGIME_STRATEGY_GATES.get(regime_assessment.regime, REGIME_STRATEGY_GATES["UNKNOWN"])

        db.add(AuditEvent(
            agent_run_id=agent_run.id, action="market_regime_assessed",
            decision=regime_assessment.regime, risk_result={"notes": regime_assessment.notes}, status="ok",
        ))

        if gates["gainer_hunter"]:
            proposals_created += await _process_gainer(db, session_row, agent_run, policy, engine, client, snapshot)
        else:
            db.add(AuditEvent(agent_run_id=agent_run.id, strategy="gainer_hunter",
                               action="strategy_disabled_by_regime", decision=regime_assessment.regime, status="ok"))

        if gates["recovery_hunter"]:
            proposals_created += await _process_recovery(db, session_row, agent_run, policy, engine, client, snapshot)
        else:
            db.add(AuditEvent(agent_run_id=agent_run.id, strategy="recovery_hunter",
                               action="strategy_disabled_by_regime", decision=regime_assessment.regime, status="ok"))

        # HOT/margin discovery still runs for visibility even when margin
        # execution is regime-blocked — eligibility reasons say why.
        proposals_created += await _process_hot_market(
            db, session_row, agent_run, policy, engine, client, regime_assessment.regime, snapshot
        )

    finally:
        await client.close()

    session_row.completed_at = datetime.now(timezone.utc)
    session_row.status = "completed"
    agent_run.completed_at = datetime.now(timezone.utc)
    agent_run.status = "completed"
    agent_run.proposals_created = proposals_created

    if proposals_created > 0:
        await notify(
            db, user_id=user_id, kind="new_opportunity",
            title=f"{proposals_created} new trade proposal(s) awaiting approval",
            detail=f"Market regime: {session_row.market_regime}.",
        )

    await db.commit()
    return session_row
