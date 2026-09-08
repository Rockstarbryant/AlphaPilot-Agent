from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.models import RiskPolicy

router = APIRouter()


class RiskPolicyOut(BaseModel):
    user_id: str
    max_spot_trade_usdt: float
    max_spot_allocation_pct: float
    max_margin_trade_usdt: float
    max_margin_allocation_pct: float
    max_leverage: float
    max_daily_loss_pct: float
    max_slippage_bps: float
    min_opportunity_score: float
    min_recovery_score: float
    hot_score_threshold: float
    gainer_hard_stop_pct: float
    recovery_hard_stop_pct: float
    recovery_take_profit_pct: float
    trading_reserve_pct: float

    class Config:
        from_attributes = True


class RiskPolicyUpdate(BaseModel):
    max_spot_trade_usdt: float | None = Field(None, ge=1)
    max_spot_allocation_pct: float | None = Field(None, ge=0.1, le=100)
    max_margin_trade_usdt: float | None = Field(None, ge=1)
    max_margin_allocation_pct: float | None = Field(None, ge=0.1, le=100)
    max_leverage: float | None = Field(None, ge=1, le=125)
    max_daily_loss_pct: float | None = Field(None, ge=0.1, le=100)
    max_slippage_bps: float | None = Field(None, ge=1)
    min_opportunity_score: float | None = Field(None, ge=0, le=100)
    min_recovery_score: float | None = Field(None, ge=0, le=100)
    hot_score_threshold: float | None = Field(None, ge=0, le=100)
    gainer_hard_stop_pct: float | None = Field(None, le=0)
    recovery_hard_stop_pct: float | None = Field(None, le=0)
    recovery_take_profit_pct: float | None = Field(None, ge=1)
    trading_reserve_pct: float | None = Field(None, ge=0, le=100)


@router.get("/{user_id}", response_model=RiskPolicyOut)
async def get_risk_policy(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RiskPolicy).where(RiskPolicy.user_id == user_id))
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="Risk policy not found for this user")
    return policy


@router.patch("/{user_id}", response_model=RiskPolicyOut)
async def update_risk_policy(
    user_id: str,
    payload: RiskPolicyUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RiskPolicy).where(RiskPolicy.user_id == user_id))
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="Risk policy not found for this user")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(policy, key, value)

    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy