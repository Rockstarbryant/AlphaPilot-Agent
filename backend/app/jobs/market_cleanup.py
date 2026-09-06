"""
Keeps the Opportunities tab honest: a candidate from a scan hours ago that
never turned into a TradePlan is clutter, not history, and gets deleted.

Candidates that DID produce a TradePlan are never deleted here — they're the
audit trail for a real proposal (approved, rejected, or executed) and are
governed by however long you want to keep TradePlan/Position history, not by
this retention window.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import MarketCandidate, TradePlan

settings = get_settings()


async def prune_stale_candidates(db: AsyncSession, retention_hours: int | None = None) -> int:
    hours = retention_hours if retention_hours is not None else settings.candidate_retention_hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    candidate_ids_with_plans = select(TradePlan.candidate_id).where(TradePlan.candidate_id.is_not(None))
    stmt = delete(MarketCandidate).where(
        MarketCandidate.created_at < cutoff,
        MarketCandidate.id.not_in(candidate_ids_with_plans),
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
