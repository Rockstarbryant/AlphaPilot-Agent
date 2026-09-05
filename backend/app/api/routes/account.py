from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.models import AccountSnapshot

router = APIRouter()


class AccountSnapshotRequest(BaseModel):
    user_id: str
    portfolio_value_usdt: float
    open_exposure_usdt: float = 0.0
    margin_exposure_usdt: float = 0.0
    realized_daily_loss_pct: float = 0.0
    source: str = "manual"


@router.post("/snapshot")
async def report_account_snapshot(payload: AccountSnapshotRequest, db: AsyncSession = Depends(get_db)):
    """
    Legacy manual snapshot endpoint. The preferred source for Track A is the
    direct Binance Agent OS account endpoint in app/api/routes/binance.py.
    """
    snapshot = AccountSnapshot(
        user_id=payload.user_id,
        portfolio_value_usdt=payload.portfolio_value_usdt,
        open_exposure_usdt=payload.open_exposure_usdt,
        margin_exposure_usdt=payload.margin_exposure_usdt,
        realized_daily_loss_pct=payload.realized_daily_loss_pct,
        source=payload.source,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


@router.get("/snapshot/{user_id}/latest")
async def get_latest_snapshot(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AccountSnapshot)
        .where(AccountSnapshot.user_id == user_id)
        .order_by(AccountSnapshot.reported_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    return snapshot
