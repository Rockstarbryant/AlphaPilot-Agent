from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.jobs.position_monitor import check_positions
from app.models.models import ExitSignal, Position, PositionStatus

router = APIRouter()


@router.get("/")
async def list_positions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Position).order_by(Position.opened_at.desc()).limit(50))
    return result.scalars().all()


@router.post("/monitor/run")
async def run_position_monitor(db: AsyncSession = Depends(get_db)):
    """Manually trigger a monitoring pass (the scheduler runs this continuously).
    Detection is deterministic and always runs; execution of the resulting
    exit signal is never automatic — see app/jobs/position_monitor.py."""
    signals = await check_positions(db)
    return {"exit_signals_generated": len(signals)}


@router.get("/exit-signals")
async def list_exit_signals(acknowledged: bool | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(ExitSignal).order_by(ExitSignal.triggered_at.desc())
    if acknowledged is not None:
        stmt = stmt.where(ExitSignal.acknowledged == acknowledged)
    result = await db.execute(stmt.limit(50))
    return result.scalars().all()


@router.post("/exit-signals/{signal_id}/acknowledge")
async def acknowledge_exit_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    """Marks an exit signal as acknowledged. This never represents a
    confirmed Binance fill — see confirm-execution below."""
    signal = await db.get(ExitSignal, signal_id)
    if signal:
        signal.acknowledged = True
        await db.commit()
    return {"signal_id": signal_id, "acknowledged": True}


class ConfirmExitRequest(BaseModel):
    binance_order_id: str
    fill_price: float | None = None


@router.post("/exit-signals/{signal_id}/confirm-execution")
async def confirm_exit_execution(
    signal_id: str, payload: ConfirmExitRequest, db: AsyncSession = Depends(get_db)
):
    """
    AlphaPilot never places the exit order itself (see
    BINANCE_AGENT_OS_REFACTOR.md — its backend is not an allowlisted Binance
    Agent OS MCP client). Once the human (or their connected AI client) has
    placed and confirmed the exit through Binance Agent OS MCP directly,
    call this so AlphaPilot's Position/ExitSignal records match reality and
    the monitor stops re-flagging it.
    """
    signal = await db.get(ExitSignal, signal_id)
    if signal is None:
        raise HTTPException(404, "Exit signal not found")
    position = await db.get(Position, signal.position_id)
    signal.execution_status = "filled"
    signal.binance_order_id = payload.binance_order_id
    signal.acknowledged = True
    if position is not None:
        position.remaining_fraction = max(0.0, position.remaining_fraction - signal.sell_fraction)
        if position.remaining_fraction <= 0.0001:
            from datetime import datetime, timezone

            position.status = PositionStatus.closed
            position.closed_at = datetime.now(timezone.utc)
        else:
            position.status = PositionStatus.partially_exited
    await db.commit()
    return {"signal_id": signal_id, "execution_status": "filled", "position_id": signal.position_id}
