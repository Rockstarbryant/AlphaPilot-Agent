from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.jobs.daily_market_reset import run_market_scan
from app.models.models import MarketSession

router = APIRouter()


@router.post("/run")
async def trigger_market_scan(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Manually trigger a market scan (spot + futures, all strategies). The
    scheduler also runs this automatically every
    `settings.scan_interval_minutes` (default 60); this endpoint exists for
    on-demand re-scans and the demo.
    """
    session = await run_market_scan(db, user_id=user_id)
    return {
        "session_id": session.id,
        "gainers_scanned": session.gainers_scanned,
        "losers_scanned": session.losers_scanned,
        "hot_candidates_found": session.hot_candidates_found,
        "market_regime": session.market_regime,
    }


@router.get("/")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MarketSession).order_by(MarketSession.started_at.desc()).limit(20)
    )
    return result.scalars().all()
