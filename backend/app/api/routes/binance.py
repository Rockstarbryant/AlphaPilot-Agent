from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from app.auth.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.models import BinanceConnectionStatus
from app.services.binance_agent_os import BinanceAgentOSService
from app.core.config import get_settings

settings = get_settings()

router = APIRouter()


@router.get("/connection/{user_id}")
async def get_connection(user_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    connection = await BinanceAgentOSService(db).connection(user_id)
    if connection is None:
        return {"status": "disconnected", "authorized": False}
    return {
        "status": connection.status.value,
        "authorized": connection.status == BinanceConnectionStatus.connected,
        "connected_at": connection.connected_at,
        "last_error": connection.last_error,
        "token_expires_at": connection.token_expires_at,
    }


@router.post("/connect/{user_id}")
async def begin_connection(user_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    try:
        return await BinanceAgentOSService(db).begin_authorization(user_id)
    except Exception as exc:
        raise HTTPException(502, f"Could not start Binance Agent OS authorization: {exc}") from exc


@router.get("/oauth/callback")
async def mcp_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None, db: AsyncSession = Depends(get_db)):
    if error:
        return RedirectResponse(url=f"{settings.frontend_public_url}/agent?binance=error&reason={error}")
    if not code or not state:
        raise HTTPException(400, "Missing OAuth code/state.")
    try:
        connection = await BinanceAgentOSService(db).complete_authorization(code=code, state=state)
        return RedirectResponse(url=f"{settings.frontend_public_url}/agent?binance=connected")
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/capabilities/{user_id}")
async def capabilities(user_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    try:
        return {"tools": await BinanceAgentOSService(db).capabilities(user_id)}
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/ticker/{user_id}/{symbol}")
async def ticker(user_id: str, symbol: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    try:
        return await BinanceAgentOSService(db).market_ticker(user_id, symbol.upper())
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/account/{user_id}")
async def account(user_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    try:
        return await BinanceAgentOSService(db).account_state(user_id)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/account/{user_id}/sync")
async def sync_account(user_id: str, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")
    try:
        return await BinanceAgentOSService(db).sync_account_snapshot(user_id)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
