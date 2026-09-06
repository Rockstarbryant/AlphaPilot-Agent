"""
AlphaPilot MCP server — Option A workflow layer.

This is NOT Binance's execution server. It exposes AlphaPilot-owned market
analysis, Earn/margin scans, risk-validated proposals, approvals, and fill
recording so an *allowlisted* MCP client (Claude Code, Cursor, ChatGPT,
Codex, VS Code, Grok Bot) can:

  1. Connect to Binance Agent OS MCP (OAuth on desktop — supported client)
  2. Connect to AlphaPilot MCP (this server)
  3. Ask analyze_symbol / get_earn_opportunities / get_margin_analysis for a view
  4. Read the user's Binance balance via Binance MCP and relay it here with
     submit_account_context
  5. Call build_trade_proposal to get a risk-validated size/leverage/TP/SL proposal
  6. Get human approval, place the order via Binance MCP tools
  7. Call record_fill here so AlphaPilot opens a Position and monitors exits
  8. If a position moves against the user, call explain_panic to relay
     AlphaPilot's read on whether the original thesis still holds

AlphaPilot never completes Binance Agentic OAuth itself (self-built clients
are currently blocked by Binance's agent allowlist) and never stores a
Binance credential of any kind — account state only ever arrives through
submit_account_context, reported by the calling client.
"""
from __future__ import annotations

from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.earn.scanner import scan_earn_opportunities
from app.margin.analysis import analyze_margin_symbol
from app.market.coin_analysis import analyze_symbol as _analyze_symbol
from app.models.models import (
    AuditEvent,
    Position,
    PositionStatus,
    TradePlan,
    TradePlanStatus,
)
from app.services.account_context import AccountContextStale, ingest_account_context
from app.services.panic_advisor import PositionNotFound, explain_position
from app.services.trade_proposal import build_trade_proposal as _build_trade_proposal

server = MCPServer(
    name="alphapilot",
    title="AlphaPilot",
    description=(
        "AlphaPilot Binance research & trading advisory. Use WITH the Binance MCP server: "
        "get market analysis and Earn/margin scans here (no auth needed), relay account "
        "state here after reading it from Binance Agent OS, get a risk-validated proposal, "
        "execute orders through Binance Agent OS MCP (allowlisted client only), then "
        "record_fill here. AlphaPilot does not hold Binance trading OAuth tokens."
    ),
    version="0.4.0-advisory",
)


def _plan_dict(p: TradePlan) -> dict:
    targets = p.profit_targets_pct or {}
    return {
        "plan_id": p.id,
        "user_id": p.user_id,
        "symbol": p.symbol,
        "strategy": p.strategy.value if hasattr(p.strategy, "value") else str(p.strategy),
        "side": p.side,
        "position_size_usdt": p.position_size_usdt,
        "entry_price_reference": p.entry_price,
        "stop_loss_pct": p.stop_loss_pct,
        "profit_targets_pct": targets,
        "opportunity_score": p.opportunity_score,
        "risk_score": p.risk_score,
        "risk_check_passed": p.risk_check_passed,
        "status": p.status.value if hasattr(p.status, "value") else str(p.status),
        "reason": p.reason,
        "binance_order_id": p.binance_order_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@server.tool()
async def wiring_instructions() -> str:
    """
    How to wire AlphaPilot + Binance Agent OS with an allowlisted MCP client.
    Call this first if the operator is unsure how Option A works.
    """
    return (
        "AlphaPilot Option A — dual MCP wiring\n"
        "=====================================\n"
        "1. On DESKTOP, open a supported client: Claude Code, Cursor, ChatGPT, Codex, VS Code, or Grok Bot.\n"
        "2. Add Binance MCP: https://agent.binance.com/mcp/agentic\n"
        "   Authenticate in the browser, grant Market data + Account + Trade as needed.\n"
        "3. Add AlphaPilot MCP (this server) — Streamable HTTP URL from your deploy\n"
        "   (e.g. https://YOUR-MCP-HOST:9000/mcp or the path your host documents).\n"
        "4. Advisory workflow (no trade intent yet):\n"
        "   - analyze_symbol(symbol) for RSI/MACD/momentum + long/short/hold bias\n"
        "   - get_earn_opportunities() for Simple Earn flexible-product APY\n"
        "   - get_margin_analysis(symbol) for margin-trade eligibility + leverage/cost estimate\n"
        "5. Sized-proposal workflow (needs a trade intent):\n"
        "   - Read the user's balance/positions via Binance MCP\n"
        "   - submit_account_context(user_id, portfolio_value_usdt, ...) to relay it here\n"
        "   - build_trade_proposal(user_id, symbol, intent) for a risk-validated size/leverage/TP/SL\n"
        "   - approve_trade_plan(plan_id) after human confirmation\n"
        "   - place order via Binance MCP tools (MARKET BUY/SELL for the plan size)\n"
        "   - record_fill(plan_id, order_id, fill_price, quantity) so AlphaPilot opens a Position\n"
        "6. If the human panics about an open position: explain_panic(position_id, question)\n"
        "   relays whether the original thesis still holds — for you to answer them with.\n"
        "7. AlphaPilot does NOT complete Binance Agentic OAuth itself (self-built clients are "
        "blocked) and never stores a Binance credential — account state only ever arrives via "
        "submit_account_context.\n"
        "8. Analysis/Earn/margin scans use public REST; they do not need Binance MCP at all.\n"
    )


@server.tool()
async def analyze_symbol(symbol: str, interval: str = "1h") -> dict:
    """
    Momentum/RSI/MACD-based analysis for one symbol, e.g. "BTCUSDT" — answers
    "what do you think about trading BTC/USDT, should I long or short, or
    buy spot and hold?" Public Binance data only — works without any Binance
    Agent OS connection.
    """
    result = await _analyze_symbol(symbol, interval=interval)
    return result.__dict__


@server.tool()
async def get_earn_opportunities() -> dict:
    """Scan Binance Simple Earn flexible products for current APY (read-only)."""
    return await scan_earn_opportunities()


@server.tool()
async def get_margin_analysis(symbol: str, daily_interest_rate_pct: float | None = None) -> dict:
    """
    Spot margin trading analysis for one symbol: eligibility (liquidity,
    spread, regime, conviction), suggested leverage within the account's
    ceiling, and an interest-cost estimate. If you already know the live
    Binance margin daily interest rate from Binance MCP, pass it in for an
    exact cost figure instead of AlphaPilot's conservative estimate.
    """
    result = await analyze_margin_symbol(symbol, daily_interest_rate_pct=daily_interest_rate_pct)
    return result.__dict__


@server.tool()
async def submit_account_context(
    user_id: str,
    portfolio_value_usdt: float,
    open_exposure_usdt: float = 0.0,
    margin_exposure_usdt: float = 0.0,
    realized_daily_loss_pct: float = 0.0,
) -> dict:
    """
    Relay Binance account state you just read from Binance Agent OS MCP.
    AlphaPilot holds no Binance credential and cannot read this itself —
    call this before build_trade_proposal, and again if more than ~10
    minutes pass before the user wants a sized proposal.
    """
    async with AsyncSessionLocal() as db:
        snapshot = await ingest_account_context(
            db,
            user_id=user_id,
            portfolio_value_usdt=portfolio_value_usdt,
            open_exposure_usdt=open_exposure_usdt,
            margin_exposure_usdt=margin_exposure_usdt,
            realized_daily_loss_pct=realized_daily_loss_pct,
        )
        return {"ok": True, "reported_at": snapshot.reported_at.isoformat()}


@server.tool()
async def build_trade_proposal(
    user_id: str,
    symbol: str,
    intent: str,
    requested_size_usdt: float | None = None,
    requested_leverage: float | None = None,
) -> dict:
    """
    Build a risk-validated trade proposal (suggested margin, leverage, hard
    stop, take-profit ladder) for `symbol`. `intent` is one of: long, short,
    spot_hold. Requires a fresh submit_account_context call first — without
    one, this returns ok=false with an explanation rather than sizing a
    trade off unknown balance.
    """
    async with AsyncSessionLocal() as db:
        try:
            return await _build_trade_proposal(
                db, user_id=user_id, symbol=symbol, intent=intent,
                requested_size_usdt=requested_size_usdt, requested_leverage=requested_leverage,
            )
        except (ValueError, AccountContextStale) as exc:
            return {"ok": False, "error": str(exc)}


@server.tool()
async def explain_panic(position_id: str, question: str = "") -> dict:
    """
    Relay this when a human panics about an open position ("it's going
    against me, should I close it?"). Re-runs AlphaPilot's analysis against
    the position's current price and reports whether the original thesis
    still holds, distance to the hard stop, and a recommendation — for you
    to phrase back to the human. AlphaPilot never closes anything itself.
    """
    async with AsyncSessionLocal() as db:
        try:
            return await explain_position(db, position_id=position_id, question=question)
        except PositionNotFound as exc:
            return {"ok": False, "error": str(exc)}


@server.tool()
async def list_pending_proposals(user_id: str | None = None) -> list[dict]:
    """
    List risk-validated trade proposals awaiting human/agent handling.
    Only plans with risk_check_passed=true and status in proposed|approved.
    Optional user_id filters to one operator.
    """
    async with AsyncSessionLocal() as db:
        q = (
            select(TradePlan)
            .where(
                TradePlan.risk_check_passed.is_(True),
                TradePlan.status.in_([TradePlanStatus.proposed, TradePlanStatus.approved]),
            )
            .order_by(TradePlan.opportunity_score.desc())
        )
        if user_id:
            q = q.where(TradePlan.user_id == user_id)
        result = await db.execute(q)
        return [_plan_dict(p) for p in result.scalars().all()]


@server.tool()
async def get_trade_plan(plan_id: str) -> dict | str:
    """Full structured trade plan by id."""
    async with AsyncSessionLocal() as db:
        plan = await db.get(TradePlan, plan_id)
        if not plan:
            return f"No trade plan found with id {plan_id}."
        return _plan_dict(plan)


@server.tool()
async def get_approval_brief(plan_id: str) -> str:
    """
    Plain-text approval brief for one plan. Use before placing a Binance order.
    """
    async with AsyncSessionLocal() as db:
        plan = await db.get(TradePlan, plan_id)
        if not plan:
            return f"No trade plan found with id {plan_id}."
        if not plan.risk_check_passed:
            return (
                f"Plan {plan_id} ({plan.symbol}) FAILED risk validation — do not execute. "
                f"Notes: {plan.risk_check_notes}"
            )
        targets = ", ".join(
            f"+{k}% → sell {float(v) * 100:.0f}%" for k, v in (plan.profit_targets_pct or {}).items()
        )
        return (
            f"AlphaPilot trade proposal — {plan.strategy.value} — RISK-VALIDATED\n\n"
            f"plan_id: {plan.id}\n"
            f"Symbol: {plan.symbol}\n"
            f"Side: {plan.side}\n"
            f"Size: ${plan.position_size_usdt:.2f} USDT\n"
            f"Reference entry: {plan.entry_price}\n"
            f"Hard stop: {plan.stop_loss_pct:.1f}%\n"
            f"Profit ladder: {targets}\n"
            f"Opportunity score: {plan.opportunity_score:.1f}/100\n"
            f"Status: {plan.status.value}\n"
            f"Reason: {plan.reason}\n\n"
            "Next steps (Option A):\n"
            "1) approve_trade_plan(plan_id) if the human agrees\n"
            "2) Place order via Binance Agent OS MCP (supported client)\n"
            "3) record_fill(plan_id, order_id, fill_price, quantity)\n"
        )


@server.tool()
async def approve_trade_plan(plan_id: str) -> dict | str:
    """
    Mark a risk-validated proposed plan as approved (ready for Binance execution
    by the allowlisted MCP client). Does not place an order.
    """
    async with AsyncSessionLocal() as db:
        plan = await db.get(TradePlan, plan_id)
        if not plan:
            return f"No trade plan found with id {plan_id}."
        if not plan.risk_check_passed:
            return f"Plan {plan_id} failed risk validation and cannot be approved."
        if plan.status not in (TradePlanStatus.proposed, TradePlanStatus.approved):
            return f"Plan {plan_id} status is {plan.status.value}; cannot approve."
        plan.status = TradePlanStatus.approved
        db.add(
            AuditEvent(
                user_id=plan.user_id,
                strategy=plan.strategy.value if hasattr(plan.strategy, "value") else str(plan.strategy),
                action="trade_plan_approved_via_mcp",
                asset=plan.symbol,
                decision="approved",
                status="ok",
                risk_result={"plan_id": plan.id},
            )
        )
        await db.commit()
        return {"ok": True, "plan": _plan_dict(plan)}


@server.tool()
async def reject_trade_plan(plan_id: str, reason: str = "rejected_by_operator") -> dict | str:
    """Cancel a proposed/approved plan so it will not be executed."""
    async with AsyncSessionLocal() as db:
        plan = await db.get(TradePlan, plan_id)
        if not plan:
            return f"No trade plan found with id {plan_id}."
        if plan.status not in (TradePlanStatus.proposed, TradePlanStatus.approved):
            return f"Plan {plan_id} status is {plan.status.value}; cannot reject."
        plan.status = TradePlanStatus.cancelled
        db.add(
            AuditEvent(
                user_id=plan.user_id,
                strategy=plan.strategy.value if hasattr(plan.strategy, "value") else str(plan.strategy),
                action="trade_plan_rejected_via_mcp",
                asset=plan.symbol,
                decision="cancelled",
                status="ok",
                risk_result={"plan_id": plan.id, "reason": reason},
            )
        )
        await db.commit()
        return {"ok": True, "plan_id": plan_id, "status": "cancelled", "reason": reason}


@server.tool()
async def record_fill(
    plan_id: str,
    order_id: str,
    fill_price: float,
    quantity: float,
) -> dict | str:
    """
    After the allowlisted client places an order on Binance Agent OS MCP and
    confirms a fill, call this so AlphaPilot creates/updates a Position and
    can run the position monitor.
    """
    async with AsyncSessionLocal() as db:
        plan = await db.get(TradePlan, plan_id)
        if not plan:
            return f"No trade plan found with id {plan_id}."
        if not plan.risk_check_passed:
            return f"Plan {plan_id} failed risk validation; refusing to record fill."
        if quantity <= 0 or fill_price <= 0:
            return "fill_price and quantity must be positive."

        plan.binance_order_id = str(order_id)
        plan.executed_at = datetime.now(timezone.utc)
        plan.status = TradePlanStatus.open

        existing = (
            await db.execute(select(Position).where(Position.trade_plan_id == plan.id))
        ).scalar_one_or_none()
        if existing is None:
            position = Position(
                trade_plan_id=plan.id,
                user_id=plan.user_id,
                symbol=plan.symbol,
                strategy=plan.strategy,
                entry_price=float(fill_price),
                quantity=float(quantity),
                remaining_fraction=1.0,
                stop_loss_pct=plan.stop_loss_pct,
                profit_targets_pct=plan.profit_targets_pct or {},
                targets_hit={},
                peak_price_since_entry=float(fill_price),
                status=PositionStatus.open,
            )
            db.add(position)
        else:
            existing.entry_price = float(fill_price)
            existing.quantity = float(quantity)
            existing.status = PositionStatus.open
            position = existing

        db.add(
            AuditEvent(
                user_id=plan.user_id,
                strategy=plan.strategy.value if hasattr(plan.strategy, "value") else str(plan.strategy),
                action="fill_recorded_via_mcp",
                asset=plan.symbol,
                decision="OPEN",
                status="ok",
                risk_result={
                    "plan_id": plan.id,
                    "order_id": order_id,
                    "fill_price": fill_price,
                    "quantity": quantity,
                },
            )
        )
        await db.commit()
        await db.refresh(position)
        return {
            "ok": True,
            "plan_id": plan.id,
            "position_id": position.id,
            "symbol": plan.symbol,
            "entry_price": float(fill_price),
            "quantity": float(quantity),
            "binance_order_id": order_id,
        }


@server.tool()
async def list_open_positions(user_id: str | None = None) -> list[dict]:
    """Positions AlphaPilot is monitoring (opened via record_fill or legacy paths)."""
    async with AsyncSessionLocal() as db:
        q = select(Position).where(
            Position.status.in_([PositionStatus.open, PositionStatus.partially_exited])
        )
        if user_id:
            q = q.where(Position.user_id == user_id)
        result = await db.execute(q)
        positions = result.scalars().all()
        return [
            {
                "position_id": p.id,
                "trade_plan_id": p.trade_plan_id,
                "user_id": p.user_id,
                "symbol": p.symbol,
                "strategy": p.strategy.value if hasattr(p.strategy, "value") else str(p.strategy),
                "entry_price": p.entry_price,
                "quantity": p.quantity,
                "remaining_fraction": p.remaining_fraction,
                "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                "last_checked_price": getattr(p, "last_checked_price", None),
            }
            for p in positions
        ]


@server.tool()
async def execution_checklist(plan_id: str) -> str:
    """
    Step-by-step checklist for the allowlisted client to execute one plan
    safely against Binance Agent OS MCP.
    """
    async with AsyncSessionLocal() as db:
        plan = await db.get(TradePlan, plan_id)
        if not plan:
            return f"No trade plan found with id {plan_id}."
        if not plan.risk_check_passed:
            return f"STOP: plan {plan_id} failed risk. Do not trade."
        qty_hint = ""
        if plan.entry_price and plan.position_size_usdt:
            approx = plan.position_size_usdt / plan.entry_price
            qty_hint = f"Approx base qty ≈ {approx:.8f} (size/entry); prefer quoteOrderQty if tool supports it.\n"
        return (
            f"Execution checklist for {plan.symbol} (plan {plan.id})\n"
            f"Status: {plan.status.value} | side: {plan.side} | size: ${plan.position_size_usdt:.2f}\n"
            f"{qty_hint}\n"
            "1. Confirm plan status is approved (call approve_trade_plan if still proposed).\n"
            "2. In Binance MCP: check Agentic sub-account balance (USDT free).\n"
            "3. In Binance MCP: place MARKET order for symbol/side/size (user may need to confirm).\n"
            "4. Read order status / fill price / executed qty from Binance MCP.\n"
            "5. Call AlphaPilot record_fill(plan_id, order_id, fill_price, quantity).\n"
            "6. AlphaPilot position monitor will track stops/targets from here.\n"
        )


def run():
    import os

    host = os.environ.get("MCP_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_SERVER_PORT", "9000"))
    server.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    run()
