from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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


def _oauth_client_metadata() -> dict:
    """OAuth Client ID Metadata Document (CIMD) for Binance Agent OS MCP.

    Binance advertises ``client_id_metadata_document_supported: true`` and does
    not expose a dynamic-registration endpoint. The ``client_id`` used in the
    authorize request is this document's public HTTPS URL.
    """
    base = (settings.public_base_url or "").rstrip("/")
    metadata_url = (settings.mcp_client_metadata_url or "").strip()
    if not metadata_url:
        metadata_url = f"{base}/.well-known/oauth-client-metadata.json"
    redirect = settings.mcp_oauth_redirect_uri
    return {
        "client_id": metadata_url,
        "client_name": settings.mcp_client_name or "AlphaPilot Agent",
        "client_uri": base or None,
        "redirect_uris": [redirect] if redirect else [],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "web",
    }


@app.get("/.well-known/oauth-client-metadata.json")
async def oauth_client_metadata():
    return JSONResponse(
        content=_oauth_client_metadata(),
        headers={"Cache-Control": "public, max-age=3600"},
    )


# Alias so either path works if MCP_CLIENT_METADATA_URL is customized.
@app.get("/oauth/client-metadata.json")
async def oauth_client_metadata_alias():
    return JSONResponse(
        content=_oauth_client_metadata(),
        headers={"Cache-Control": "public, max-age=3600"},
    )
