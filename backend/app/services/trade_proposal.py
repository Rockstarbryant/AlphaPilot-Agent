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

# ---------------------------------------------------------------------------
# Exchange practical minima (most USDT pairs)
# ---------------------------------------------------------------------------
MIN_SPOT_NOTIONAL_USDT = 5.0
MIN_FUTURES_NOTIONAL_USDT = 5.0

# Hard ceiling for chat-requested proposals (overrides low RiskPolicy defaults)
CHAT_MAX_ALLOCATION_PCT = 40.0
CHAT_MAX_LEVERAGE = 25.0

# Stop-loss: never risk more than this fraction of the margin
MAX_MARGIN_LOSS_PCT = 50.0


def _confidence_to_allocation_pct(confidence: float) -> float:
    """
    Map confidence (0-100) → target portfolio allocation %.

    15% conf → \~2.5%
    30% conf → 5%
    50% conf → \~15%
    70% conf → 25%
    100% conf → 40%
    """
    c = max(0.0, min(100.0, confidence))
    if c <= 30:
        # 0 → 30  maps to 1% → 5%
        return 1.0 + (5.0 - 1.0) * (c / 30.0)
    if c <= 70:
        # 30 → 70 maps to 5% → 25%
        return 5.0 + (25.0 - 5.0) * ((c - 30.0) / 40.0)
    # 70 → 100 maps to 25% → 40%
    return 25.0 + (40.0 - 25.0) * ((c - 70.0) / 30.0)


def _confidence_to_leverage(confidence: float) -> float:
    """
    Map confidence (0-100) → leverage.

    40% conf → \~10x
    60% conf → \~18x
    100% conf → 25x
    """
    c = max(0.0, min(100.0, confidence))
    if c <= 40:
        # 0 → 40 maps to 1x → 10x
        return 1.0 + (10.0 - 1.0) * (c / 40.0)
    # 40 → 100 maps to 10x → 25x
    return 10.0 + (25.0 - 10.0) * ((c - 40.0) / 60.0)


def _stop_loss_pct_for_leverage(leverage: float) -> float:
    """
    Price-move stop that risks at most MAX_MARGIN_LOSS_PCT of the margin.
    loss_pct_of_margin ≈ |price_move_pct| * leverage
    → |price_move_pct| = MAX_MARGIN_LOSS_PCT / leverage
    """
    if leverage <= 0:
        return -8.0
    return -round(MAX_MARGIN_LOSS_PCT / leverage, 2)


def _take_profit_targets(confidence: float) -> dict[str, float]:
    """
    Scale take-profit distances with confidence.
    Returns { "tp1_pct": weight, "tp2_pct": weight } style dict
    compatible with existing TradePlan.profit_targets_pct.
    """
    c = max(0.0, min(100.0, confidence))
    if c < 40:
        # Conservative targets
        return {"8": 0.5, "15": 0.5}
    if c < 70:
        return {"12": 0.5, "22": 0.5}
    # High confidence — wider targets
    return {"18": 0.5, "30": 0.5}


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
    confidence = max(0.0, float(analysis.confidence))

    # ------------------------------------------------------------------
    # 1. Confidence-scaled allocation %
    # ------------------------------------------------------------------
    target_alloc_pct = _confidence_to_allocation_pct(confidence)
    # Cap at the higher of policy value or our chat ceiling
    effective_max_alloc = max(
        policy.max_margin_allocation_pct if is_margin else policy.max_spot_allocation_pct,
        CHAT_MAX_ALLOCATION_PCT,
    )
    target_alloc_pct = min(target_alloc_pct, effective_max_alloc)

    size_by_confidence = snapshot.portfolio_value_usdt * (target_alloc_pct / 100.0)

    # ------------------------------------------------------------------
    # 2. Confidence-scaled leverage
    # ------------------------------------------------------------------
    leverage = 1.0
    if is_margin:
        lev_from_conf = _confidence_to_leverage(confidence)
        effective_max_lev = max(policy.max_leverage, CHAT_MAX_LEVERAGE)
        leverage = round(
            min(requested_leverage or lev_from_conf, effective_max_lev),
            2,
        )

    # ------------------------------------------------------------------
    # 3. Position size (margin for futures, notional for spot)
    # ------------------------------------------------------------------
    max_trade = (
        max(policy.max_margin_trade_usdt, snapshot.portfolio_value_usdt * 0.4)
        if is_margin
        else max(policy.max_spot_trade_usdt, snapshot.portfolio_value_usdt * 0.4)
    )

    position_size_usdt = min(
        requested_size_usdt or size_by_confidence,
        size_by_confidence,
        max_trade,
        snapshot.portfolio_value_usdt,  # never more than available
    )

    # ------------------------------------------------------------------
    # 4. Enforce Binance minimum notional (make small accounts tradeable)
    # ------------------------------------------------------------------
    if is_margin:
        notional = position_size_usdt * leverage
        if notional < MIN_FUTURES_NOTIONAL_USDT and snapshot.portfolio_value_usdt > 0:
            # Raise margin and/or leverage just enough to clear the floor
            # Prefer raising leverage first (keeps margin small), then margin.
            required_notional = MIN_FUTURES_NOTIONAL_USDT
            # Try higher leverage first (up to our chat max)
            needed_lev = required_notional / max(position_size_usdt, 1e-9)
            if needed_lev <= CHAT_MAX_LEVERAGE:
                leverage = round(min(max(leverage, needed_lev), CHAT_MAX_LEVERAGE), 2)
                notional = position_size_usdt * leverage
            # If still short, raise margin
            if notional < required_notional:
                needed_margin = required_notional / max(leverage, 1e-9)
                if needed_margin <= snapshot.portfolio_value_usdt:
                    position_size_usdt = round(needed_margin, 2)
                else:
                    # Account simply cannot meet exchange minimum
                    position_size_usdt = 0.0
    else:
        # Spot
        if position_size_usdt < MIN_SPOT_NOTIONAL_USDT:
            if MIN_SPOT_NOTIONAL_USDT <= snapshot.portfolio_value_usdt:
                position_size_usdt = MIN_SPOT_NOTIONAL_USDT
            else:
                position_size_usdt = 0.0

    position_size_usdt = max(0.0, round(position_size_usdt, 2))

    # ------------------------------------------------------------------
    # 5. Stop-loss & take-profit (confidence / leverage aware)
    # ------------------------------------------------------------------
    if is_margin:
        stop_loss_pct = _stop_loss_pct_for_leverage(leverage)
    else:
        # Spot: fixed conservative stop
        stop_loss_pct = -8.0

    profit_targets = _take_profit_targets(confidence)

    # ------------------------------------------------------------------
    # Opportunity score for risk engine
    # ------------------------------------------------------------------
    opportunity_score = confidence if confidence > 0 else 0.0

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
        score_breakdown={
            "confidence": analysis.confidence,
            "bias": analysis.bias,
            "target_alloc_pct": round(target_alloc_pct, 2),
            "leverage": leverage,
        },
        reason="; ".join(analysis.rationale),
        data_source_timestamp=now,
    )
    db.add(candidate)
    await db.flush()

    idempotency_key = hashlib.sha256(
        f"user_requested:{user_id}:{symbol}:{intent}:{now.isoformat()}".encode()
    ).hexdigest()

    # ------------------------------------------------------------------
    # Risk engine validation
    # ------------------------------------------------------------------
    engine = RiskEngine(policy)
    trade_intent = TradeIntent(
        symbol=symbol,
        strategy="user_requested",
        position_size_usdt=position_size_usdt,
        entry_price=analysis.price,
        estimated_slippage_bps=0.0,
        stop_loss_pct=stop_loss_pct,
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

    # Extra explicit rejection when we could not meet exchange minimum
    if position_size_usdt <= 0:
        risk_result.passed = False
        risk_result.fail(
            "min_notional",
            f"Account too small to meet Binance minimum notional "
            f"(\~{MIN_FUTURES_NOTIONAL_USDT if is_margin else MIN_SPOT_NOTIONAL_USDT} USDT) "
            f"under current balance and risk limits.",
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
        stop_loss_pct=stop_loss_pct,
        profit_targets_pct=profit_targets,
        opportunity_score=opportunity_score,
        risk_score=100.0 - len([c for c in risk_result.checks.values() if not c]) * 15,
        reason=(
            f"Chat-requested {intent} on {symbol}. "
            f"Bias={analysis.bias} ({analysis.confidence}%). "
            f"Alloc={target_alloc_pct:.1f}%, Lev={leverage}x. "
            + "; ".join(analysis.rationale)
        ),
        market_conditions={
            "rsi": analysis.rsi,
            "macd": analysis.macd,
            "momentum": analysis.momentum,
            "regime": analysis.market_regime,
            "target_alloc_pct": round(target_alloc_pct, 2),
        },
        risk_check_passed=risk_result.passed,
        risk_check_notes=risk_result.notes,
        idempotency_key=idempotency_key,
        status="proposed" if risk_result.passed else "risk_rejected",
    )
    db.add(trade_plan)
    candidate.status = (
        CandidateStatus.trade_proposed if risk_result.passed else CandidateStatus.rejected
    )
    db.add(
        AuditEvent(
            user_id=user_id,
            strategy="user_requested",
            action="trade_plan_created",
            asset=symbol,
            decision="proposed" if risk_result.passed else "risk_rejected",
            risk_result=risk_result.notes,
            status="ok",
        )
    )
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
        "stop_loss_pct": stop_loss_pct,
        "take_profit_targets_pct": profit_targets,
        "target_allocation_pct": round(target_alloc_pct, 2),
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