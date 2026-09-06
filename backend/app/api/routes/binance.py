"""
Binance Agent OS relay endpoints.

AlphaPilot is NOT a Binance Agent OS MCP client — Binance's agent allowlist
covers Claude Desktop/Code, ChatGPT, Codex, VS Code, and Grok Bot only, not
self-built backends (see BINANCE_AGENT_OS_REFACTOR.md). So instead of
connecting/OAuth-ing to Binance itself, AlphaPilot exposes a small relay:
whichever AI client the user is chatting with reads their real Binance
Agent OS account state and reports it here (also available as the MCP tool
``submit_account_context`` in app/mcp_server.py) so AlphaPilot's risk engine
and trade-proposal builder have real numbers to work with.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.base import get_db
from app.services.account_context import get_latest_context, ingest_account_context

router = APIRouter()


class AccountContextRequest(BaseModel):
    portfolio_value_usdt: float = Field(..., ge=0)
    open_exposure_usdt: float = Field(0.0, ge=0)
    margin_exposure_usdt: float = Field(0.0, ge=0)
    realized_daily_loss_pct: float = 0.0
    raw_snapshot: dict = Field(default_factory=dict)


@router.post("/account-context/{user_id}")
async def submit_account_context(
    user_id: str,
    payload: AccountContextRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Report Binance Agent OS account state that an AI client already read.
    Powers portfolio-relative risk checks in build_trade_proposal without
    AlphaPilot ever holding a Binance credential.
    """
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    snapshot = await ingest_account_context(db, user_id=user_id, **payload.model_dump())
    return {
        "ok": True,
        "reported_at": snapshot.reported_at,
        "portfolio_value_usdt": snapshot.portfolio_value_usdt,
    }


@router.get("/account-context/{user_id}")
async def get_account_context(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    snapshot = await get_latest_context(db, user_id)
    if snapshot is None:
        return {"status": "none_reported"}
    return {
        "status": "ok",
        "reported_at": snapshot.reported_at,
        "portfolio_value_usdt": snapshot.portfolio_value_usdt,
        "open_exposure_usdt": snapshot.open_exposure_usdt,
        "margin_exposure_usdt": snapshot.margin_exposure_usdt,
        "realized_daily_loss_pct": snapshot.realized_daily_loss_pct,
        "raw_snapshot": snapshot.raw_snapshot,
    }
