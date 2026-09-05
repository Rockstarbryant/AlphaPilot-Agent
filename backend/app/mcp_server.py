"""
AlphaPilot's optional MCP server exposes AlphaPilot-owned data to external
MCP clients. It is NOT the Binance execution client. Direct Binance execution
now happens inside AlphaPilot through app.services.binance_agent_os.

Tools exposed:
    list_pending_proposals
    get_approval_brief
    binance_connection_status
    list_open_positions

Run standalone (see docker-compose.yml, service "mcp-server") on
Streamable HTTP, the same transport Binance's own MCP server uses, so a
client that already knows how to add Binance's server knows how to add
this one too.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.models.models import Position, TradePlan, TradePlanStatus

server = MCPServer(
    name="alphapilot",
    title="AlphaPilot",
    description=(
        "AlphaPilot's own trade-proposal and position data. Use alongside the "
        "Binance MCP server: read proposals here, execute them through Binance's "
        "MCP data; direct Binance execution is performed by AlphaPilot itself."
    ),
    version="0.1.0",
)


@server.tool()
async def list_pending_proposals() -> list[dict]:
    """
    List risk-validated trade proposals currently awaiting execution.
    Only returns plans where risk_check_passed is true — a plan the
    deterministic Risk Engine rejected is never surfaced here for
    execution, regardless of what an AI client might otherwise decide.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TradePlan)
            .where(TradePlan.status == TradePlanStatus.proposed, TradePlan.risk_check_passed.is_(True))
            .order_by(TradePlan.opportunity_score.desc())
        )
        plans = result.scalars().all()
        return [
            {
                "plan_id": p.id,
                "symbol": p.symbol,
                "strategy": p.strategy.value,
                "side": p.side,
                "position_size_usdt": p.position_size_usdt,
                "entry_price_reference": p.entry_price,
                "opportunity_score": p.opportunity_score,
                "reason": p.reason,
            }
            for p in plans
        ]


@server.tool()
async def get_approval_brief(plan_id: str) -> str:
    """
    Full plain-text approval brief for one trade plan — the same content
    the AlphaPilot dashboard's 'Get approval brief' button produces.
    Returns an error string (not a tool failure) if the plan doesn't
    exist or failed risk validation, so the calling AI can explain that
    to the human rather than attempting the trade anyway.
    """
    async with AsyncSessionLocal() as db:
        plan = await db.get(TradePlan, plan_id)
        if not plan:
            return f"No trade plan found with id {plan_id}."
        if not plan.risk_check_passed:
            return (
                f"Plan {plan_id} ({plan.symbol}) failed risk validation and cannot be "
                f"executed. Reasons: {plan.risk_check_notes}"
            )
        targets = ", ".join(
            f"+{k}% -> sell {float(v) * 100:.0f}%" for k, v in plan.profit_targets_pct.items()
        )
        return (
            f"AlphaPilot trade proposal — {plan.strategy.value} — risk-validated.\n\n"
            f"Symbol: {plan.symbol}\n"
            f"Side: {plan.side}\n"
            f"Position size: ${plan.position_size_usdt:.2f} USDT\n"
            f"Reference entry: {plan.entry_price}\n"
            f"Hard stop: {plan.stop_loss_pct:.1f}%\n"
            f"Profit ladder: {targets}\n"
            f"Opportunity score: {plan.opportunity_score:.1f}/100\n"
            f"Reason: {plan.reason}\n\n"
            f"Direct execution is handled by AlphaPilot through Binance Agent OS MCP; this server is read-only with respect to Binance."
        )


@server.tool()
async def binance_connection_status(user_id: str) -> dict:
    """Return AlphaPilot's direct Binance Agent OS connection state."""
    from app.services.binance_agent_os import BinanceAgentOSService
    async with AsyncSessionLocal() as db:
        connection = await BinanceAgentOSService(db).connection(user_id)
        if connection is None:
            return {"status": "disconnected", "authorized": False}
        return {
            "status": connection.status.value,
            "authorized": connection.status.value == "connected",
            "connected_at": connection.connected_at.isoformat() if connection.connected_at else None,
        }


@server.tool()
async def list_open_positions() -> list[dict]:
    """List positions AlphaPilot is currently monitoring."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Position).where(Position.status.in_(["open", "partially_exited"]))
        )
        positions = result.scalars().all()
        return [
            {
                "position_id": p.id,
                "symbol": p.symbol,
                "strategy": p.strategy.value,
                "entry_price": p.entry_price,
                "quantity": p.quantity,
                "remaining_fraction": p.remaining_fraction,
                "status": p.status.value,
                "last_checked_price": p.last_checked_price,
            }
            for p in positions
        ]


def run():
    """Entry point for `python -m app.mcp_server`. Host/port are
    configurable via env so this can run inside Docker (0.0.0.0) or
    locally (127.0.0.1) without a code change."""
    import os
    host = os.environ.get("MCP_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_SERVER_PORT", "9000"))
    server.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    run()
