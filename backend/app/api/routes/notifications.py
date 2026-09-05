from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.models import Notification

router = APIRouter()


@router.get("/{user_id}")
async def list_notifications(user_id: str, unread_only: bool = False, db: AsyncSession = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc())
    if unread_only:
        stmt = stmt.where(Notification.read.is_(False))
    result = await db.execute(stmt.limit(50))
    return result.scalars().all()


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, db: AsyncSession = Depends(get_db)):
    n = await db.get(Notification, notification_id)
    if n:
        n.read = True
        await db.commit()
    return {"id": notification_id, "read": True}


@router.post("/{user_id}/read-all")
async def mark_all_read(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id, Notification.read.is_(False))
    )
    for n in result.scalars().all():
        n.read = True
    await db.commit()
    return {"user_id": user_id, "marked_read": True}
