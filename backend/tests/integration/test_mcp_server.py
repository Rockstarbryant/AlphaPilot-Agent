"""
Tests AlphaPilot's own MCP server (app/mcp_server.py) using an MCP client
over Streamable HTTP. The server exposes AlphaPilot-owned data; direct Binance
execution is implemented separately by BinanceAgentOSService.

Note on fixtures: the MCP server runs as its own subprocess with its own
database connection — a real, separate connection, not the same one this
test's Python process holds. The shared `db_session` fixture from
conftest.py deliberately keeps everything inside an uncommitted outer
transaction (that's what makes it safe for the rest of the suite — see its
docstring), which means data seeded through it is invisible to a different
connection, exactly like real Postgres transaction isolation should behave.
So this file uses its own fixture that commits for real and cleans up
explicitly afterward, rather than relying on rollback-based isolation.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.models.models import MarketCandidate, MarketSession, RiskPolicy, StrategyType, TradePlan, User

MCP_TEST_PORT = 9101
MCP_URL = f"http://127.0.0.1:{MCP_TEST_PORT}/mcp"


@pytest_asyncio.fixture
async def mcp_server_process():
    """
    Runs the real MCP server as a subprocess against the same Postgres
    instance, over real HTTP — proving the module actually starts and
    serves the way `python -m app.mcp_server` would in production, not
    just that its Python objects construct correctly.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = os.environ.copy()
    backend_dir = Path(__file__).resolve().parents[2]  # backend/tests/integration -> backend
    proc = subprocess.Popen(
        [
            sys.executable, "-c",
            f"from app.mcp_server import server; "
            f"server.run(transport='streamable-http', host='127.0.0.1', port={MCP_TEST_PORT})",
        ],
        env=env, cwd=str(backend_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    import httpx
    for _ in range(30):
        try:
            httpx.get(MCP_URL, timeout=1.0)
            break
        except httpx.ConnectError:
            await asyncio.sleep(0.5)
    else:
        proc.kill()
        out, _ = proc.communicate(timeout=5)
        raise RuntimeError(f"MCP server did not start in time. Output:\n{out.decode(errors='replace')}")

    yield proc

    proc.kill()
    proc.wait(timeout=5)


@pytest_asyncio.fixture
async def seeded_proposal():
    """
    Seeds real, actually-committed rows (not savepoint-isolated) so the
    MCP server subprocess's separate connection can see them, then cleans
    up explicitly in a finally block regardless of test outcome.
    """
    async with AsyncSessionLocal() as db:
        user = User(id=str(uuid.uuid4()), email=f"mcp-{uuid.uuid4()}@example.com", hashed_password="x")
        db.add(user)
        await db.flush()
        db.add(RiskPolicy(user_id=user.id))
        session = MarketSession(session_date=datetime.now(timezone.utc))
        db.add(session)
        await db.flush()
        candidate = MarketCandidate(
            session_id=session.id, symbol="ETHUSDT", strategy=StrategyType.gainer_hunter,
            price=3200.0, daily_change_pct=12.0, quote_volume_24h=5_000_000, spread_bps=4.0,
            opportunity_score=78.0, data_source_timestamp=session.session_date,
        )
        db.add(candidate)
        await db.flush()
        plan = TradePlan(
            candidate_id=candidate.id, user_id=user.id, symbol="ETHUSDT",
            strategy=StrategyType.gainer_hunter, entry_price=3200.0, position_size_usdt=60.0,
            estimated_slippage_bps=4.0, stop_loss_pct=-20.0,
            profit_targets_pct={"15": 0.25, "30": 0.25}, opportunity_score=78.0, risk_score=100.0,
            reason="test seed", risk_check_passed=True, idempotency_key=str(uuid.uuid4()),
            status="proposed",
        )
        db.add(plan)
        await db.commit()
        await db.refresh(plan)
        plan_id, user_id, candidate_id, session_id = plan.id, user.id, candidate.id, session.id

    yield plan

    async with AsyncSessionLocal() as db:
        from app.models.models import AuditEvent, Position
        await db.execute(delete(Position).where(Position.trade_plan_id == plan_id))
        await db.execute(delete(TradePlan).where(TradePlan.id == plan_id))
        await db.execute(delete(MarketCandidate).where(MarketCandidate.id == candidate_id))
        await db.execute(delete(MarketSession).where(MarketSession.id == session_id))
        await db.execute(delete(AuditEvent).where(AuditEvent.user_id == user_id))
        await db.execute(delete(RiskPolicy).where(RiskPolicy.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.mark.asyncio
async def test_mcp_server_full_flow(mcp_server_process, seeded_proposal):
    """AlphaPilot's own MCP surface is read-only; direct Binance execution is
    performed by BinanceAgentOSService rather than by an external execution hand-off.
    """
    async with streamable_http_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            assert {
                "list_pending_proposals", "get_approval_brief",
                "binance_connection_status", "list_open_positions",
            }.issubset(tool_names)

            result = await session.call_tool("list_pending_proposals", {})
            proposals = [json.loads(block.text) for block in result.content]
            matching = [p for p in proposals if p["plan_id"] == seeded_proposal.id]
            assert len(matching) == 1
            assert matching[0]["symbol"] == "ETHUSDT"

            brief = await session.call_tool("get_approval_brief", {"plan_id": seeded_proposal.id})
            brief_text = brief.content[0].text
            assert "ETHUSDT" in brief_text
            assert "$60.00" in brief_text
            assert "Binance Agent OS" in brief_text


@pytest.mark.asyncio
async def test_get_approval_brief_refuses_risk_rejected_plan(mcp_server_process):
    async with AsyncSessionLocal() as db:
        user = User(id=str(uuid.uuid4()), email=f"mcp2-{uuid.uuid4()}@example.com", hashed_password="x")
        db.add(user)
        await db.flush()
        session = MarketSession(session_date=datetime.now(timezone.utc))
        db.add(session)
        await db.flush()
        candidate = MarketCandidate(
            session_id=session.id, symbol="DOGEUSDT", strategy=StrategyType.gainer_hunter,
            price=0.1, daily_change_pct=5.0, quote_volume_24h=1_000_000, spread_bps=10.0,
            opportunity_score=40.0, data_source_timestamp=session.session_date,
        )
        db.add(candidate)
        await db.flush()
        rejected_plan = TradePlan(
            candidate_id=candidate.id, user_id=user.id, symbol="DOGEUSDT",
            strategy=StrategyType.gainer_hunter, entry_price=0.1, position_size_usdt=500.0,
            estimated_slippage_bps=10.0, stop_loss_pct=-20.0, profit_targets_pct={},
            opportunity_score=40.0, risk_score=20.0, reason="oversized",
            risk_check_passed=False, risk_check_notes={"max_trade_size": "too big"},
            idempotency_key=str(uuid.uuid4()), status="risk_rejected",
        )
        db.add(rejected_plan)
        await db.commit()
        await db.refresh(rejected_plan)
        plan_id, user_id, candidate_id, session_id = rejected_plan.id, user.id, candidate.id, session.id

    try:
        async with streamable_http_client(MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                brief = await session.call_tool("get_approval_brief", {"plan_id": plan_id})
                text = brief.content[0].text
                assert "failed risk validation" in text
                assert "cannot be executed" in text
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(TradePlan).where(TradePlan.id == plan_id))
            await db.execute(delete(MarketCandidate).where(MarketCandidate.id == candidate_id))
            await db.execute(delete(MarketSession).where(MarketSession.id == session_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
