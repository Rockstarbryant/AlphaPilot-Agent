from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.base import get_db
from app.models.models import AuditEvent, Position, TradePlan, TradePlanStatus

router = APIRouter()


@router.get("/")
async def list_trade_plans(status: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(TradePlan).order_by(TradePlan.created_at.desc())
    if status:
        stmt = stmt.where(TradePlan.status == status)
    result = await db.execute(stmt.limit(50))
    return result.scalars().all()


@router.get("/{plan_id}/approval-brief")
async def get_approval_brief(plan_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    plan = await db.get(TradePlan, plan_id)
    if not plan:
        raise HTTPException(404, "Trade plan not found")
    if plan.user_id != current_user.id:
        raise HTTPException(403, "Forbidden")
    if not plan.risk_check_passed:
        raise HTTPException(400, "This plan failed risk validation and cannot be executed.")
    targets = ", ".join(f"+{k}% -> sell {float(v)*100:.0f}%" for k, v in plan.profit_targets_pct.items())
    return {
        "plan_id": plan.id,
        "brief": (
            f"AlphaPilot trade proposal — {plan.strategy.value} — risk-validated.\n\n"
            f"Symbol: {plan.symbol}\nSide: {plan.side}\nSuggested size: ${plan.position_size_usdt:.2f} USDT\n"
            f"Reference entry: {plan.entry_price}\nHard stop: {plan.stop_loss_pct:.1f}%\n"
            f"Profit ladder: {targets}\nOpportunity score: {plan.opportunity_score:.1f}/100\n"
            f"Reason: {plan.reason}\n\n"
            "AlphaPilot cannot submit this order itself — Binance's agent allowlist does not "
            "include AlphaPilot's backend. Place this order through Binance Agent OS MCP with an "
            "allowlisted AI client (Claude, ChatGPT, Codex, etc.), then confirm it below so "
            "AlphaPilot opens a Position and starts monitoring stops/targets."
        ),
    }


class ConfirmExecutionRequest(BaseModel):
    binance_order_id: str
    fill_price: float | None = None
    filled_quantity: float | None = None


@router.post("/{plan_id}/confirm-execution")
async def confirm_execution(
    plan_id: str,
    payload: ConfirmExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    The production execution-confirmation path. AlphaPilot never places
    Binance orders itself (see BINANCE_AGENT_OS_REFACTOR.md) — after the
    human (or the allowlisted AI client on their behalf) places the order
    directly through Binance Agent OS MCP and it fills, call this (or the
    equivalent MCP tool, ``record_fill``) with the resulting order id and
    fill details so AlphaPilot opens/updates a Position and starts
    monitoring stops and profit targets.
    """
    plan = await db.get(TradePlan, plan_id)
    if not plan:
        raise HTTPException(404, "Trade plan not found")
    if plan.user_id != current_user.id:
        raise HTTPException(403, "Forbidden")
    if plan.status not in (TradePlanStatus.proposed, TradePlanStatus.approved):
        raise HTTPException(400, f"Plan is '{plan.status}', not awaiting execution confirmation.")
    if not plan.risk_check_passed:
        raise HTTPException(400, "Risk-rejected trade plan cannot be confirmed as executed.")

    fill_price = payload.fill_price or plan.entry_price
    quantity = payload.filled_quantity or (plan.position_size_usdt / fill_price if fill_price else 0.0)
    plan.status = TradePlanStatus.open
    plan.binance_order_id = payload.binance_order_id
    plan.executed_at = datetime.now(timezone.utc)

    existing = (await db.execute(select(Position).where(Position.trade_plan_id == plan.id))).scalar_one_or_none()
    if existing is None:
        position = Position(
            trade_plan_id=plan.id, user_id=plan.user_id, symbol=plan.symbol, strategy=plan.strategy,
            entry_price=fill_price, quantity=quantity, remaining_fraction=1.0,
            stop_loss_pct=plan.stop_loss_pct, profit_targets_pct=plan.profit_targets_pct,
            targets_hit={}, peak_price_since_entry=fill_price,
        )
        db.add(position)
    else:
        existing.entry_price = fill_price
        existing.quantity = quantity
        position = existing
    db.add(AuditEvent(
        user_id=plan.user_id, strategy=plan.strategy.value, action="position_opened_confirmed",
        asset=plan.symbol, decision="OPEN", status="ok",
        risk_result={"binance_order_id": payload.binance_order_id, "fill_price": fill_price},
    ))
    await db.commit()
    return {"plan_id": plan.id, "status": plan.status, "position_id": position.id}
