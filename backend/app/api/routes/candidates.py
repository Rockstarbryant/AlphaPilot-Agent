from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.models import MarketCandidate

router = APIRouter()


@router.get("/")
async def list_candidates(session_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(MarketCandidate).order_by(MarketCandidate.opportunity_score.desc())
    if session_id:
        stmt = stmt.where(MarketCandidate.session_id == session_id)
    result = await db.execute(stmt.limit(50))
    return result.scalars().all()
