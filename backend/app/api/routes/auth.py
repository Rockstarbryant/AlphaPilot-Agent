from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.base import get_db
from app.models.models import AgentConfig, RiskPolicy, User

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


@router.post("/register", response_model=TokenResponse)
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.flush()

    # Every user gets a RiskPolicy and AgentConfig at creation time — the
    # scheduler refuses to run strategies for a user without one (see
    # jobs/daily_market_reset.py). Defaults come from Settings, not from
    # anything the AI could influence.
    from app.core.config import get_settings
    s = get_settings()
    db.add(RiskPolicy(
        user_id=user.id,
        max_spot_trade_usdt=s.max_spot_trade_usdt,
        max_spot_allocation_pct=s.max_spot_allocation_pct,
        max_margin_trade_usdt=s.max_margin_trade_usdt,
        max_margin_allocation_pct=s.max_margin_allocation_pct,
        max_leverage=s.max_leverage,
        max_daily_loss_pct=s.max_daily_loss_pct,
        max_slippage_bps=s.max_slippage_bps,
        min_opportunity_score=s.min_opportunity_score,
        min_recovery_score=s.min_recovery_score,
        hot_score_threshold=s.hot_score_threshold,
        gainer_hard_stop_pct=s.gainer_hard_stop_pct,
        recovery_hard_stop_pct=s.recovery_hard_stop_pct,
        recovery_take_profit_pct=s.recovery_take_profit_pct,
        trading_reserve_pct=s.trading_reserve_pct,
    ))
    db.add(AgentConfig(user_id=user.id, trading_mode=s.trading_mode_default))
    await db.commit()

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user_id=user.id)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user_id=user.id)


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
