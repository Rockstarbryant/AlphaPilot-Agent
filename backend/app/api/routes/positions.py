from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.jobs.position_monitor import check_positions
from app.models.models import ExitSignal, Position
from app.services.binance_agent_os import BinanceAgentOSService

router = APIRouter()


@router.get("/")
async def list_positions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Position).order_by(Position.opened_at.desc()).limit(50))
    return result.scalars().all()


@router.post("/monitor/run")
async def run_position_monitor(db: AsyncSession = Depends(get_db)):
    """Manually trigger a monitoring pass (the scheduler runs this continuously)."""
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
    """
    Marks an exit signal as acknowledged. Direct execution is handled by
    /execute and BinanceAgentOSService; acknowledgement alone never represents
    a confirmed Binance fill.
    """
    signal = await db.get(ExitSignal, signal_id)
    if signal:
        signal.acknowledged = True
        await db.commit()
    return {"signal_id": signal_id, "acknowledged": True}


@router.post("/exit-signals/{signal_id}/execute")
async def execute_exit_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    signal = await db.get(ExitSignal, signal_id)
    if signal is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Exit signal not found")
    try:
        return {"signal_id": signal_id, **(await BinanceAgentOSService(db).execute_exit_signal(signal))}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(502, str(exc)) from exc
