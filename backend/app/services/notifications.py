"""
In-app notification center. Built first per the original spec's own
guidance: "If push notifications cannot be implemented within the timeline,
implement an internal notification center first. Do not block the project
on external notification providers." Push delivery (APNs/FCM/email) is a
Phase 2 addition that would call `notify()` under the hood — the call sites
throughout the codebase don't need to change when that's added.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification


async def notify(db: AsyncSession, *, user_id: str, kind: str, title: str, detail: str = "") -> Notification:
    n = Notification(user_id=user_id, kind=kind, title=title, detail=detail)
    db.add(n)
    await db.flush()
    return n
