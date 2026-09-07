from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import get_db
from app.models.models import MarketCandidate
from app.services.candidate_explainer import explain_candidate

router = APIRouter()
settings = get_settings()


@router.get("/")
async def list_candidates(
    session_id: str | None = None,
    market_type: str | None = None,  # spot | futures
    status: str | None = None,
    strategy: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Candidates from the last `candidate_retention_hours` only — older ones
    are pruned by the scan job (app/jobs/market_cleanup.py) and are filtered
    out here too as a second guard so the Opportunities tab never shows a
    stale scan even in the gap before the next cleanup runs.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.candidate_retention_hours)
    stmt = select(MarketCandidate).where(MarketCandidate.created_at >= cutoff)
    if session_id:
        stmt = stmt.where(MarketCandidate.session_id == session_id)
    if market_type:
        stmt = stmt.where(MarketCandidate.market_type == market_type)
    if status:
        stmt = stmt.where(MarketCandidate.status == status)
    if strategy:
        stmt = stmt.where(MarketCandidate.strategy == strategy)
    stmt = stmt.order_by(MarketCandidate.created_at.desc(), MarketCandidate.opportunity_score.desc())
    result = await db.execute(stmt.limit(200))
    return result.scalars().all()


@router.post("/{candidate_id}/explain")
async def explain_candidate_plain_language(candidate_id: str, db: AsyncSession = Depends(get_db)):
    """
    Plain-language "why is this coin where it is" explanation for
    non-technical users, generated on demand and cached on the candidate row.
    """
    candidate = await db.get(MarketCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    already_cached = bool(candidate.ai_explanation)
    explanation, ai_narrated = await explain_candidate(candidate)
    if not already_cached and ai_narrated:
        candidate.ai_explanation = explanation
        await db.commit()
    return {"candidate_id": candidate_id, "explanation": explanation, "ai_narrated": ai_narrated}
