from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.base import get_db
from app.earn.scanner import scan_earn_opportunities
from app.margin.analysis import analyze_margin_symbol
from app.market.coin_analysis import analyze_symbol
from app.services.panic_advisor import PositionNotFound, explain_position
from app.services.trade_proposal import build_trade_proposal

router = APIRouter()


@router.get("/analyze/{symbol}")
async def get_symbol_analysis(symbol: str, interval: str = "1h"):
    """
    Momentum/RSI/MACD-based analysis for a specific symbol, e.g. BTCUSDT —
    "what do you think about trading BTC/USDT?" Public data only; no auth
    or Binance Agent OS connection required.
    """
    try:
        analysis = await analyze_symbol(symbol, interval=interval)
    except Exception as exc:
        raise HTTPException(502, f"Could not analyze {symbol}: {exc}") from exc
    return analysis.__dict__


@router.get("/earn")
async def get_earn_opportunities():
    """Simple Earn flexible-product APY scan (read-only)."""
    return await scan_earn_opportunities()


@router.get("/margin/{symbol}")
async def get_margin_analysis(symbol: str, daily_interest_rate_pct: float | None = None):
    try:
        analysis = await analyze_margin_symbol(symbol, daily_interest_rate_pct=daily_interest_rate_pct)
    except Exception as exc:
        raise HTTPException(502, f"Could not analyze margin for {symbol}: {exc}") from exc
    return analysis.__dict__


class TradeProposalRequest(BaseModel):
    symbol: str
    intent: str  # long | short | spot_hold
    requested_size_usdt: float | None = None
    requested_leverage: float | None = None


@router.post("/proposal/{user_id}")
async def create_trade_proposal(
    user_id: str,
    payload: TradeProposalRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Builds a risk-validated trade proposal (suggested margin, leverage, stop,
    take-profit ladder) using the most recently reported account context.
    Requires a fresh POST /api/binance/account-context/{user_id} first.
    """
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    try:
        result = await build_trade_proposal(
            db,
            user_id=user_id,
            symbol=payload.symbol,
            intent=payload.intent,
            requested_size_usdt=payload.requested_size_usdt,
            requested_leverage=payload.requested_leverage,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(409, result.get("error", "Could not build proposal."))
    return result


@router.get("/panic/{position_id}")
async def get_panic_explanation(
    position_id: str, question: str = "", db: AsyncSession = Depends(get_db)
):
    """
    "The trade is going against me, should I close it?" — re-runs the same
    analysis the original proposal was built on against current price.
    """
    try:
        return await explain_position(db, position_id=position_id, question=question)
    except PositionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
