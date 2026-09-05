from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.models import EarnRecommendation
from app.services.capital_optimizer import evaluate_idle_capital

router = APIRouter()


class CapitalOptimizerRequest(BaseModel):
    user_id: str
    total_capital_usdt: float
    open_positions_value_usdt: float = 0.0
    pending_proposals_value_usdt: float = 0.0


@router.post("/evaluate")
async def evaluate_capital(payload: CapitalOptimizerRequest, db: AsyncSession = Depends(get_db)):
    result = evaluate_idle_capital(
        total_capital_usdt=payload.total_capital_usdt,
        open_positions_value_usdt=payload.open_positions_value_usdt,
        pending_proposals_value_usdt=payload.pending_proposals_value_usdt,
    )
    rec = EarnRecommendation(
        user_id=payload.user_id,
        idle_capital_usdt=result["idle_capital_usdt"],
        trading_reserve_usdt=result["trading_reserve_usdt"],
        emergency_reserve_usdt=result["emergency_reserve_usdt"],
        recommended_earn_usdt=result["recommended_earn_usdt"],
        reason=result["reason"],
    )
    db.add(rec)
    await db.commit()
    return result
