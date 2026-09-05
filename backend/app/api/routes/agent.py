from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.models import AgentConfig, AuditEvent, TradingMode

router = APIRouter()


@router.get("/{user_id}")
async def get_agent_config(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentConfig).where(AgentConfig.user_id == user_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "Agent config not found")
    return config


class TradingModeRequest(BaseModel):
    trading_mode: TradingMode


@router.post("/{user_id}/trading-mode")
async def set_trading_mode(user_id: str, payload: TradingModeRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentConfig).where(AgentConfig.user_id == user_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "Agent config not found")
    config.trading_mode = payload.trading_mode
    db.add(AuditEvent(user_id=user_id, action="trading_mode_changed", decision=payload.trading_mode.value, status="ok"))
    await db.commit()
    return config


class EmergencyStopRequest(BaseModel):
    reason: str


@router.post("/{user_id}/emergency-stop")
async def emergency_stop(user_id: str, payload: EmergencyStopRequest, db: AsyncSession = Depends(get_db)):
    """
    Halts new autonomous proposals server-side. Per docs/AGENT.md, this does
    NOT touch any existing Binance position — Binance's own emergency stop
    (disconnect agents + cancel all orders/positions) lives in their
    sub-account management UI and isn't callable remotely today. This is
    intentional, not an oversight: we never want a bug in this backend to be
    able to secretly liquidate a user's real positions.
    """
    result = await db.execute(select(AgentConfig).where(AgentConfig.user_id == user_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "Agent config not found")
    config.emergency_halted = True
    config.halted_reason = payload.reason
    db.add(AuditEvent(user_id=user_id, action="emergency_stop_activated", decision="HALTED",
                       risk_result={"reason": payload.reason}, status="ok"))
    from app.services.notifications import notify
    await notify(db, user_id=user_id, kind="agent_error", title="Emergency stop activated", detail=payload.reason)
    await db.commit()
    return {
        "halted": True,
        "note": (
            "New AlphaPilot trade proposals are stopped. To also cancel/close existing "
            "Binance positions, use Binance's own Emergency Stop in Profile -> Dashboard -> "
            "Sub-account -> Account Management, or disconnect the agent from your MCP client."
        ),
    }


@router.post("/{user_id}/resume")
async def resume_agent(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentConfig).where(AgentConfig.user_id == user_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "Agent config not found")
    config.emergency_halted = False
    config.halted_reason = None
    db.add(AuditEvent(user_id=user_id, action="agent_resumed", decision="ACTIVE", status="ok"))
    await db.commit()
    return config
