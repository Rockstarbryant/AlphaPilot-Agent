"""
Account context relay — the piece that replaces AlphaPilot's own (now-blocked)
Binance Agent OS OAuth client.

AlphaPilot cannot connect to Binance Agent OS MCP itself (Binance's agent
allowlist only covers Claude Desktop/Code, ChatGPT, Codex, and Grok Bot — see
BINANCE_AGENT_OS_REFACTOR.md and docs/ADVISORY_REFACTOR.md). Instead, the
*same* AI client the human is chatting with — which does have Binance Agent
OS connected — reads account balances/positions there and reports them back
to AlphaPilot through this service (via the MCP tool ``submit_account_context``
or the REST endpoint POST /api/binance/account-context/{user_id}). AlphaPilot
never stores a Binance credential; it only stores whatever numbers were
reported, with a timestamp, so downstream risk checks can (a) use them and
(b) refuse to use them once they go stale.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AccountSnapshot

# A trade proposal must not be built on stale account numbers — if the human
# takes 20 minutes to relay a balance and then asks for a trade, AlphaPilot
# should ask them to re-check rather than size a trade off old data.
MAX_CONTEXT_AGE = timedelta(minutes=10)


class AccountContextStale(RuntimeError):
    pass


async def ingest_account_context(
    db: AsyncSession,
    *,
    user_id: str,
    portfolio_value_usdt: float,
    open_exposure_usdt: float = 0.0,
    margin_exposure_usdt: float = 0.0,
    realized_daily_loss_pct: float = 0.0,
    raw_snapshot: dict | None = None,
) -> AccountSnapshot:
    snapshot = AccountSnapshot(
        user_id=user_id,
        portfolio_value_usdt=portfolio_value_usdt,
        open_exposure_usdt=open_exposure_usdt,
        margin_exposure_usdt=margin_exposure_usdt,
        realized_daily_loss_pct=realized_daily_loss_pct,
        source="mcp_client_reported",
        raw_snapshot=raw_snapshot or {},
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def get_latest_context(db: AsyncSession, user_id: str) -> AccountSnapshot | None:
    result = await db.execute(
        select(AccountSnapshot)
        .where(AccountSnapshot.user_id == user_id)
        .order_by(AccountSnapshot.reported_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def require_fresh_context(db: AsyncSession, user_id: str) -> AccountSnapshot:
    """Used by trade-proposal building — raises rather than silently sizing
    a trade off a $0 or ancient balance."""
    snapshot = await get_latest_context(db, user_id)
    if snapshot is None:
        raise AccountContextStale(
            "No account context on file yet. Ask your AI client to read your Binance Agent OS "
            "balance/positions and submit them via submit_account_context before requesting a "
            "sized trade proposal."
        )
    reported_at = snapshot.reported_at
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - reported_at
    if age > MAX_CONTEXT_AGE:
        raise AccountContextStale(
            f"Account context is {age.total_seconds() / 60:.0f} minutes old (max "
            f"{MAX_CONTEXT_AGE.total_seconds() / 60:.0f}). Ask your AI client to re-read Binance "
            "Agent OS account state and submit it again."
        )
    return snapshot
