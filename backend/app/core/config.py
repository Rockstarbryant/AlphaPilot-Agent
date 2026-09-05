"""
Central configuration for AlphaPilot.

Everything that affects trading behavior (thresholds, allocations, stops)
is env-driven so it can be tuned without a code change and so the Risk
Engine's decisions are auditable against a known config snapshot.

Binance trading is performed through the hosted Binance Agent OS MCP endpoint.
No Binance API key/secret is stored. MCP authorization credentials are encrypted at rest.
Binance itself may still require confirmation for every write action.
"""
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# asyncpg rejects some query params that appear on managed-Postgres URLs
# (Supabase / Neon / Render copies of libpq-style DSNs).
_ASYNCPG_UNSUPPORTED_PARAMS = {
    "channel_binding",
    "sslmode",
    "options",
    "target_session_attrs",
}


def sanitize_database_url(url: str) -> str:
    """Strip libpq-only query params so asyncpg can connect.

    Used by ``app.db.base`` (and alembic env) so the same DATABASE_URL works
    whether it was copied from a psycopg/libpq UI or written for asyncpg.
    """
    parts = urlsplit(url)
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _ASYNCPG_UNSUPPORTED_PARAMS
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query_pairs), parts.fragment)
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development")
    database_url: str = Field(
        default="postgresql+asyncpg://alphapilot:alphapilot@localhost:5432/alphapilot"
    )
    jwt_secret: str = Field(default="change-me-in-.env")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # AI provider (analysis/reasoning only — never trade execution or hard risk)
    ai_provider: str = Field(default="openrouter")
    openrouter_api_key: str = Field(default="")
    openrouter_model: str = Field(default="")

    # Binance public REST is used for scheduled market discovery. Agent OS MCP
    # is the direct authenticated account/execution boundary.
    binance_public_rest_base: str = Field(default="https://api.binance.com")
    binance_mcp_endpoint: str = Field(default="https://agent.binance.com/mcp/agentic")
    # MCP OAuth is the standard authorization mechanism used by protected MCP
    # servers. These settings are provider-neutral; Binance controls the actual
    # authorization page, scopes, and Agentic-account permissions.
    mcp_client_name: str = Field(default="AlphaPilot Agent")
    mcp_oauth_redirect_uri: str = Field(default="http://localhost:8000/api/binance/oauth/callback")
    mcp_oauth_encryption_key: str = Field(default="")
    # HTTPS URL of the public Client ID Metadata Document (CIMD).
    # When empty, derived as {PUBLIC_BASE_URL}/.well-known/oauth-client-metadata.json
    # Binance Agent OS requires CIMD (client_id_metadata_document_supported=true).
    mcp_client_metadata_url: str = Field(default="")
    public_base_url: str = Field(default="http://localhost:8000")
    frontend_public_url: str = Field(default="http://localhost:3000")

    # --- Market session ---
    daily_session_hour_utc: int = 0
    daily_session_minute_utc: int = 0
    gainer_candidate_count: int = 15
    loser_candidate_count: int = 5

    # --- Liquidity / eligibility filters (Gainer + Recovery universe) ---
    min_quote_volume_24h_usdt: float = 500_000.0
    max_spread_bps: float = 50.0  # basis points

    # --- Scoring thresholds ---
    min_opportunity_score: float = 65.0
    min_recovery_score: float = 65.0
    hot_score_threshold: float = 85.0

    # --- Risk policy (defaults; overridable per-user in risk_policies table) ---
    max_spot_trade_usdt: float = 100.0
    max_spot_allocation_pct: float = 10.0
    max_margin_trade_usdt: float = 30.0
    max_margin_allocation_pct: float = 3.0
    max_leverage: float = 3.0
    max_daily_loss_pct: float = 5.0
    max_slippage_bps: float = 50.0

    # --- Gainer strategy exits ---
    gainer_hard_stop_pct: float = -20.0
    gainer_ladder_targets_pct: str = "15,30,45,60"  # csv, parsed at use site
    gainer_ladder_sell_fraction: float = 0.25

    # --- Recovery strategy exits ---
    recovery_take_profit_pct: float = 25.0
    recovery_hard_stop_pct: float = -20.0
    recovery_max_stagnation_hours: int = 48
    recovery_min_required_momentum_pct: float = 1.0
    recovery_min_required_volume_ratio: float = 0.8

    # --- Trading reserve / Earn ---
    trading_reserve_pct: float = 40.0
    emergency_reserve_usdt: float = 100.0

    trading_mode_default: str = "approval_required"  # read_only | approval_required | autonomous


@lru_cache
def get_settings() -> Settings:
    return Settings()
