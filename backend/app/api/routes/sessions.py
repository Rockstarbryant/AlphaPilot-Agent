from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.jobs.daily_market_reset import run_daily_market_reset
from app.models.models import MarketSession

router = APIRouter()


@router.post("/run")
async def trigger_market_scan(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Manually trigger a market scan (the scheduler calls run_daily_market_reset
    directly at 00:00 UTC; this endpoint exists for the demo and for
    on-demand re-scans).
    """
    session = await run_daily_market_reset(db, user_id=user_id)
    return {"session_id": session.id, "gainers_scanned": session.gainers_scanned}


@router.get("/")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MarketSession).order_by(MarketSession.started_at.desc()).limit(20)
    )
    return result.scalars().all()
