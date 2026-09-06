"""
Market scan job. Despite the filename (kept for git history / import
compat — see the `run_daily_market_reset` alias at the bottom), this no
longer runs once a day: it runs every `settings.scan_interval_minutes`
(default 60) per docs/STRATEGIES.md, and scans BOTH the spot market and
USDⓈ-M futures perpetuals, gated by the Market Regime Engine, persists
results with a `market_type` label and a plain `reason` for every outcome
(qualified, watching, or rejected — not just the winners), and for
candidates clearing their score bar, creates risk-validated TradePlan
proposals.

This job touches ONLY public Binance market data. It creates risk-validated
TradePlans but never submits orders — approval and execution happen through
Binance Agent OS MCP via an allowlisted AI client, confirmed back via
POST /api/trade-plans/{id}/confirm-execution (see BINANCE_AGENT_OS_REFACTOR.md).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.binance.market_data import BinanceMarketDataClient, MarketType
from app.core.config import get_settings
from app.jobs.market_cleanup import prune_stale_candidates
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


async def _process_gainer(db, session_row, agent_run, policy, engine, client, snapshot, market_type: MarketType) -> int:
    raw_candidates = await gainer.discover_gainer_candidates(client)
    created = 0
    for raw in raw_candidates:
        below_bar = raw["opportunity_score"] < policy.min_opportunity_score
        candidate = MarketCandidate(
            session_id=session_row.id, symbol=raw["symbol"], strategy=StrategyType.gainer_hunter,
            market_type=market_type,
            price=raw["price"], daily_change_pct=raw["daily_change_pct"],
            quote_volume_24h=raw["quote_volume_24h"], spread_bps=raw["spread_bps"],
            opportunity_score=raw["opportunity_score"], score_breakdown=raw["score_breakdown"],
            data_source_timestamp=raw["data_source_timestamp"],
        )
        if below_bar:
            candidate.status = "watching"
            candidate.reason = (
                f"Up {raw['daily_change_pct']:.1f}% in 24h, but opportunity score "
                f"{raw['opportunity_score']:.1f}/100 is below the {policy.min_opportunity_score:.0f} "
                "bar — momentum, volume, or spread quality isn't strong enough yet to propose a trade. "
                "AlphaPilot keeps watching in case that changes on the next scan."
            )
            db.add(candidate)
            continue
        candidate.status = "qualified"
        db.add(candidate)
        await db.flush()

        plan_dict = gainer.build_trade_plan_dict(raw, policy.user_id, policy.max_spot_trade_usdt)
        candidate.reason = plan_dict["reason"]
        created += await _validate_and_propose(
            db, candidate, agent_run, policy, engine, raw, plan_dict, StrategyType.gainer_hunter, snapshot=snapshot,
        )
    session_row.gainers_scanned = (session_row.gainers_scanned or 0) + len(raw_candidates)
    return created


async def _process_recovery(db, session_row, agent_run, policy, engine, client, snapshot, market_type: MarketType) -> int:
    raw_candidates = await recovery.discover_recovery_candidates(client)
    created = 0
    for raw in raw_candidates:
        candidate = MarketCandidate(
            session_id=session_row.id, symbol=raw["symbol"], strategy=StrategyType.recovery_hunter,
            market_type=market_type,
            price=raw["price"], daily_change_pct=raw["daily_change_pct"],
            quote_volume_24h=raw["quote_volume_24h"], spread_bps=raw["spread_bps"],
            opportunity_score=raw["recovery_score"], score_breakdown=raw["score_breakdown"],
            data_source_timestamp=raw["data_source_timestamp"],
        )
        if raw["classification"] in ("LOW", "AVOID") or raw["recovery_score"] < policy.min_recovery_score:
            candidate.status = "rejected" if raw["classification"] == "AVOID" else "watching"
            candidate.reason = (
                f"Down {raw['daily_change_pct']:.1f}% in 24h. Recovery classification "
                f"'{raw['classification']}' with score {raw['recovery_score']:.1f}/100 — "
                + (
                    "signals suggest this is still falling, not stabilizing, so AlphaPilot is not "
                    "treating it as a recovery candidate."
                    if raw["classification"] == "AVOID"
                    else "not yet enough stabilization/volume evidence to propose a trade."
                )
            )
            db.add(candidate)
            continue
        candidate.status = "qualified"
        db.add(candidate)
        await db.flush()

        plan_dict = recovery.build_trade_plan_dict(raw, policy.user_id, policy.max_spot_trade_usdt)
        candidate.reason = plan_dict["reason"]
        created += await _validate_and_propose(
            db, candidate, agent_run, policy, engine, raw, plan_dict, StrategyType.recovery_hunter, snapshot=snapshot,
        )
    session_row.losers_scanned = (session_row.losers_scanned or 0) + len(raw_candidates)
    return created


async def _process_hot_market(db, session_row, agent_run, policy, engine, client, regime: str, snapshot, market_type: MarketType) -> int:
    """
    HOT/Margin candidates are recorded for visibility even when margin is
    disabled by regime — the eligibility reasons are part of the audit
    trail (docs/STRATEGIES.md #21). Eligible candidates get a risk-validated
    margin TradePlan proposal, same discipline as Gainer/Recovery.
    """
    raw_candidates = await hot_market.discover_hot_candidates(client, limit=settings.hot_candidate_count)
    found = 0
    created = 0
    for raw in raw_candidates:
        if raw["hot_score"] < policy.hot_score_threshold:
            continue
        found += 1
        eligible, reasons = hot_market.margin_eligibility(raw, regime)
        candidate = MarketCandidate(
            session_id=session_row.id, symbol=raw["symbol"], strategy=StrategyType.hot_market_margin,
            market_type=market_type,
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
    session_row.hot_candidates_found = (session_row.hot_candidates_found or 0) + found
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
    # Portfolio-relative checks use the latest client-reported AccountSnapshot
    # (see app/services/account_context.py) when one exists. With none
    # reported yet, we fall back to $0 — which makes every allocation-%
    # check fail closed (blocks the trade) rather than silently pass on a
    # fabricated balance. See docs/RISK_ENGINE.md.
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
    if not risk_result.passed:
        candidate.reason = (candidate.reason or "") + " Risk check blocked this from becoming an active proposal."
    db.add(AuditEvent(
        agent_run_id=agent_run.id, strategy=strategy.value, action="trade_plan_created",
        asset=raw["symbol"], decision="proposed" if risk_result.passed else "risk_rejected",
        risk_result=risk_result.notes, status="ok",
    ))
    return 1


async def _scan_one_market(db, session_row, agent_run, policy, engine, snapshot, market_type: MarketType, regime_assessment) -> int:
    client = BinanceMarketDataClient(market_type=market_type)
    proposals_created = 0
    try:
        gates = REGIME_STRATEGY_GATES.get(regime_assessment.regime, REGIME_STRATEGY_GATES["UNKNOWN"])

        if gates["gainer_hunter"]:
            proposals_created += await _process_gainer(db, session_row, agent_run, policy, engine, client, snapshot, market_type)
        else:
            db.add(AuditEvent(agent_run_id=agent_run.id, strategy="gainer_hunter",
                               action="strategy_disabled_by_regime", decision=regime_assessment.regime, status="ok"))

        if gates["recovery_hunter"]:
            proposals_created += await _process_recovery(db, session_row, agent_run, policy, engine, client, snapshot, market_type)
        else:
            db.add(AuditEvent(agent_run_id=agent_run.id, strategy="recovery_hunter",
                               action="strategy_disabled_by_regime", decision=regime_assessment.regime, status="ok"))

        # HOT/margin discovery still runs for visibility even when margin
        # execution is regime-blocked — eligibility reasons say why.
        proposals_created += await _process_hot_market(
            db, session_row, agent_run, policy, engine, client, regime_assessment.regime, snapshot, market_type
        )
    finally:
        await client.close()
    return proposals_created


async def run_market_scan(db: AsyncSession, user_id: str) -> MarketSession:
    # Prune first so a scan never has to compete with hours-old clutter for
    # the user's attention, and so this job doubles as the retention sweep
    # without needing a second scheduled loop.
    await prune_stale_candidates(db)

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

    engine = RiskEngine(policy)
    proposals_created = 0
    snapshot = await _get_account_snapshot(db, user_id)

    # Regime assessment uses spot data (it's a market-wide breadth/volatility
    # read, not specific to one contract type) and gates both scans equally.
    spot_client = BinanceMarketDataClient(market_type="spot")
    try:
        regime_assessment = await assess_market_regime(spot_client)
    finally:
        await spot_client.close()
    session_row.market_regime = regime_assessment.regime
    db.add(AuditEvent(
        agent_run_id=agent_run.id, action="market_regime_assessed",
        decision=regime_assessment.regime, risk_result={"notes": regime_assessment.notes}, status="ok",
    ))

    for market_type in ("spot", "futures"):
        try:
            proposals_created += await _scan_one_market(
                db, session_row, agent_run, policy, engine, snapshot, market_type, regime_assessment
            )
        except Exception:
            # A futures-host outage shouldn't take down the spot scan (or
            # vice versa) — log via AuditEvent and keep going.
            db.add(AuditEvent(
                agent_run_id=agent_run.id, action="market_scan_failed",
                decision=market_type, status="error",
            ))

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


# Back-compat alias — several call sites (routes/sessions.py, tests,
# docs) still say "daily" even though the cadence is now hourly; the name
# is kept so nothing else needs to change to pick this up.
run_daily_market_reset = run_market_scan
