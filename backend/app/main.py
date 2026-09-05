from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import (
    account, agent, auth, binance, candidates, capital, notifications, positions, sessions, trade_plans,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="AlphaPilot", version="0.1.0")
app.state.limiter = auth.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_public_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(candidates.router, prefix="/api/candidates", tags=["candidates"])
app.include_router(trade_plans.router, prefix="/api/trade-plans", tags=["trade-plans"])
app.include_router(binance.router, prefix="/api/binance", tags=["binance-agent-os"])
app.include_router(positions.router, prefix="/api/positions", tags=["positions"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(capital.router, prefix="/api/capital", tags=["capital"])
app.include_router(account.router, prefix="/api/account", tags=["account"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
