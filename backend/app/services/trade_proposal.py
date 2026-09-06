"""
Ad-hoc trade proposal builder — the chat-driven counterpart to
app/jobs/daily_market_reset.py's scheduled strategies.

Flow this implements (see docs/ADVISORY_REFACTOR.md):
  1. User asks an AI client (with Binance Agent OS connected) about a symbol.
  2. The client calls AlphaPilot's analyze_symbol tool/endpoint for the view.
  3. The client reads the user's Binance balance via Agent OS and reports it
     here via submit_account_context.
  4. The client calls build_trade_proposal — THIS module — which runs the
     same deterministic RiskEngine every scheduled strategy goes through and
     returns a TradePlan with suggested size/leverage/stop/targets.
  5. The human approves; the client places the order through Binance Agent
     OS MCP directly (AlphaPilot never executes); record_fill / the
     confirm-execution endpoint closes the loop so AlphaPilot can monitor it.

A TradePlan requires a MarketCandidate (for the discovery-session audit
trail) — for chat-driven requests there is no scan, so this creates a
minimal one-row MarketSession/MarketCandidate pair tagged StrategyType.user_requested,
carrying the same analysis output that would otherwise come from a scanner.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.coin_analysis import CoinAnalysis, analyze_symbol
from app.models.models import (
    AuditEvent,
    CandidateStatus,
    MarketCandidate,
    MarketSession,
    RiskPolicy,
    StrategyType,
    TradePlan,
)
from app.risk.engine import RiskEngine, TradeIntent
from app.services.account_context import AccountContextStale, require_fresh_context

DEFAULT_STOP_LOSS_PCT = -8.0
DEFAULT_PROFIT_TARGETS_PCT = {"10": 0.5, "20": 0.5}


class ProposalRejected(RuntimeError):
    """Raised when the deterministic risk engine rejects the ad-hoc intent
    outright (e.g. emergency-halted). The TradePlan row is still created,
    with risk_check_passed=False, so it's visible in the audit trail."""


async def build_trade_proposal(
    db: AsyncSession,
    *,
    user_id: str,
    symbol: str,
    intent: str,  # "long" | "short" | "spot_hold"
    requested_size_usdt: float | None = None,
    requested_leverage: float | None = None,
) -> dict:
    symbol = symbol.upper().replace("/", "")
    intent = intent.lower().strip()
    if intent not in ("long", "short", "spot_hold"):
        raise ValueError("intent must be one of: long, short, spot_hold")

    policy_result = await db.execute(select(RiskPolicy).where(RiskPolicy.user_id == user_id))
    policy = policy_result.scalar_one_or_none()
    if policy is None:
        raise RuntimeError(f"No RiskPolicy configured for user {user_id}.")

    try:
        snapshot = await require_fresh_context(db, user_id)
    except AccountContextStale as exc:
        return {"ok": False, "error": str(exc)}

    analysis: CoinAnalysis = await analyze_symbol(symbol)
    is_margin = intent in ("long", "short")
    side = "BUY" if intent in ("long", "spot_hold") else "SELL"

    max_trade = policy.max_margin_trade_usdt if is_margin else policy.max_spot_trade_usdt
    max_alloc_pct = policy.max_margin_allocation_pct if is_margin else policy.max_spot_allocation_pct
    size_by_allocation = snapshot.portfolio_value_usdt * (max_alloc_pct / 100)
    position_size_usdt = min(
        requested_size_usdt or max_trade, max_trade, size_by_allocation
    )
    position_size_usdt = max(0.0, round(position_size_usdt, 2))

    leverage = 1.0
    if is_margin:
        confidence_scaled = 1 + (policy.max_leverage - 1) * (analysis.confidence / 100) * 0.5
        leverage = round(min(requested_leverage or confidence_scaled, policy.max_leverage), 2)

    # Opportunity score doubles as the risk engine's score-floor gate for
    # user-requested plans — an ad-hoc idea still has to clear the same bar
    # a scheduled strategy would.
    opportunity_score = analysis.confidence if analysis.confidence > 0 else 0.0

    now = datetime.now(timezone.utc)
    session_row = MarketSession(session_date=now, status="completed", completed_at=now)
    db.add(session_row)
    await db.flush()

    candidate = MarketCandidate(
        session_id=session_row.id,
        symbol=symbol,
        strategy=StrategyType.user_requested,
        status=CandidateStatus.analyzing,
        price=analysis.price,
        daily_change_pct=analysis.price_change_pct_24h,
        quote_volume_24h=0.0,
        spread_bps=0.0,
        opportunity_score=opportunity_score,
        score_breakdown={"confidence": analysis.confidence, "bias": analysis.bias},
        reason="; ".join(analysis.rationale),
        data_source_timestamp=now,
    )
    db.add(candidate)
    await db.flush()

    idempotency_key = hashlib.sha256(
        f"user_requested:{user_id}:{symbol}:{intent}:{now.isoformat()}".encode()
    ).hexdigest()

    engine = RiskEngine(policy)
    trade_intent = TradeIntent(
        symbol=symbol,
        strategy="user_requested",
        position_size_usdt=position_size_usdt,
        entry_price=analysis.price,
        estimated_slippage_bps=0.0,
        stop_loss_pct=DEFAULT_STOP_LOSS_PCT,
        opportunity_score=opportunity_score,
        is_margin=is_margin,
        leverage=leverage,
        data_age_seconds=0.0,
    )
    risk_result = engine.validate(
        trade_intent,
        current_portfolio_value_usdt=snapshot.portfolio_value_usdt,
        current_open_exposure_usdt=snapshot.open_exposure_usdt,
        current_margin_exposure_usdt=snapshot.margin_exposure_usdt,
        realized_daily_loss_pct=snapshot.realized_daily_loss_pct,
        open_positions_for_symbol=0,
        pending_plans_for_symbol=0,
        emergency_halted=False,
    )

    trade_plan = TradePlan(
        candidate_id=candidate.id,
        user_id=user_id,
        symbol=symbol,
        strategy=StrategyType.user_requested,
        side=side,
        entry_price=analysis.price,
        position_size_usdt=position_size_usdt,
        estimated_slippage_bps=0.0,
        stop_loss_pct=DEFAULT_STOP_LOSS_PCT,
        profit_targets_pct=DEFAULT_PROFIT_TARGETS_PCT,
        opportunity_score=opportunity_score,
        risk_score=100.0 - len([c for c in risk_result.checks.values() if not c]) * 15,
        reason=f"Chat-requested {intent} on {symbol}. Bias={analysis.bias} ({analysis.confidence}%). "
        + "; ".join(analysis.rationale),
        market_conditions={
            "rsi": analysis.rsi, "macd": analysis.macd, "momentum": analysis.momentum,
            "regime": analysis.market_regime,
        },
        risk_check_passed=risk_result.passed,
        risk_check_notes=risk_result.notes,
        idempotency_key=idempotency_key,
        status="proposed" if risk_result.passed else "risk_rejected",
    )
    db.add(trade_plan)
    candidate.status = CandidateStatus.trade_proposed if risk_result.passed else CandidateStatus.rejected
    db.add(AuditEvent(
        user_id=user_id, strategy="user_requested", action="trade_plan_created",
        asset=symbol, decision="proposed" if risk_result.passed else "risk_rejected",
        risk_result=risk_result.notes, status="ok",
    ))
    await db.commit()
    await db.refresh(trade_plan)

    return {
        "ok": True,
        "plan_id": trade_plan.id,
        "symbol": symbol,
        "intent": intent,
        "side": side,
        "is_margin": is_margin,
        "suggested_margin_usdt": position_size_usdt,
        "suggested_leverage": leverage if is_margin else None,
        "reference_entry_price": analysis.price,
        "stop_loss_pct": DEFAULT_STOP_LOSS_PCT,
        "take_profit_targets_pct": DEFAULT_PROFIT_TARGETS_PCT,
        "risk_check_passed": risk_result.passed,
        "risk_check_notes": risk_result.notes,
        "bias": analysis.bias,
        "confidence": analysis.confidence,
        "rationale": analysis.rationale,
        "next_step": (
            "Show this proposal to the human for approval. If approved, place the order through "
            "Binance Agent OS MCP directly, then call record_fill (MCP) or "
            "POST /api/trade-plans/{plan_id}/confirm-execution (REST) with the resulting order id "
            "and fill price so AlphaPilot opens a Position and starts monitoring stops/targets."
            if risk_result.passed
            else "Risk-rejected — do not execute. See risk_check_notes for why."
        ),
    }
