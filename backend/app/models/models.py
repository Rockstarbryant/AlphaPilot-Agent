"""
Phase 1 database models.

Deliberately scoped to what the Gainer/Recovery discovery pipeline, the risk
engine, and the direct Agent OS execution workflow actually needs. Margin, Earn, and
notification tables are added in Phase 2 once those strategies are built —
see docs/STRATEGIES.md priority order.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, JSON
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TradingMode(str, PyEnum):
    read_only = "read_only"
    approval_required = "approval_required"
    autonomous = "autonomous"


class StrategyType(str, PyEnum):
    gainer_hunter = "gainer_hunter"
    recovery_hunter = "recovery_hunter"
    hot_market_margin = "hot_market_margin"
    capital_optimizer = "capital_optimizer"


class CandidateStatus(str, PyEnum):
    analyzing = "analyzing"
    watching = "watching"
    qualified = "qualified"
    rejected = "rejected"
    trade_proposed = "trade_proposed"
    executed = "executed"


class TradePlanStatus(str, PyEnum):
    proposed = "proposed"
    approved = "approved"
    submitting = "submitting"
    open = "open"
    partially_exited = "partially_exited"
    closing = "closing"
    closed = "closed"
    failed = "failed"
    cancelled = "cancelled"
    risk_rejected = "risk_rejected"




class BinanceConnectionStatus(str, PyEnum):
    pending = "pending"
    connected = "connected"
    revoked = "revoked"
    error = "error"


class BinanceConnection(Base):
    """Per-user protected MCP connection to Binance Agent OS.

    Binance performs the interactive authorization through the MCP connection.
    AlphaPilot stores only the resulting MCP OAuth material, encrypted at rest,
    so it can act as the MCP client for subsequent account/data/tool calls.
    """
    __tablename__ = "binance_connections"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    status: Mapped[BinanceConnectionStatus] = mapped_column(
        Enum(BinanceConnectionStatus), default=BinanceConnectionStatus.pending
    )
    client_id: Mapped[str | None] = mapped_column(String, nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oauth_state: Mapped[str | None] = mapped_column(String, nullable=True)
    code_verifier_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    risk_policy: Mapped["RiskPolicy"] = relationship(back_populates="user", uselist=False)
    agent_config: Mapped["AgentConfig"] = relationship(back_populates="user", uselist=False)


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    trading_mode: Mapped[TradingMode] = mapped_column(
        Enum(TradingMode), default=TradingMode.approval_required
    )
    emergency_halted: Mapped[bool] = mapped_column(Boolean, default=False)
    halted_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship(back_populates="agent_config")


class RiskPolicy(Base):
    """
    Server-side, deterministic. The LLM never writes to this table and the
    trade-validation path never reads a value the AI produced instead of one
    stored here. See app/risk/engine.py.
    """
    __tablename__ = "risk_policies"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)

    max_spot_trade_usdt: Mapped[float] = mapped_column(Float, default=100.0)
    max_spot_allocation_pct: Mapped[float] = mapped_column(Float, default=10.0)
    max_margin_trade_usdt: Mapped[float] = mapped_column(Float, default=30.0)
    max_margin_allocation_pct: Mapped[float] = mapped_column(Float, default=3.0)
    max_leverage: Mapped[float] = mapped_column(Float, default=3.0)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, default=5.0)
    max_slippage_bps: Mapped[float] = mapped_column(Float, default=50.0)
    min_opportunity_score: Mapped[float] = mapped_column(Float, default=65.0)
    min_recovery_score: Mapped[float] = mapped_column(Float, default=65.0)
    hot_score_threshold: Mapped[float] = mapped_column(Float, default=85.0)
    gainer_hard_stop_pct: Mapped[float] = mapped_column(Float, default=-20.0)
    recovery_hard_stop_pct: Mapped[float] = mapped_column(Float, default=-20.0)
    recovery_take_profit_pct: Mapped[float] = mapped_column(Float, default=25.0)
    trading_reserve_pct: Mapped[float] = mapped_column(Float, default=40.0)

    user: Mapped["User"] = relationship(back_populates="risk_policy")


class MarketSession(Base):
    __tablename__ = "market_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    session_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    market_regime: Mapped[str | None] = mapped_column(String, nullable=True)
    gainers_scanned: Mapped[int] = mapped_column(Integer, default=0)
    losers_scanned: Mapped[int] = mapped_column(Integer, default=0)
    hot_candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="running")

    candidates: Mapped[list["MarketCandidate"]] = relationship(back_populates="session")


class MarketCandidate(Base):
    __tablename__ = "market_candidates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("market_sessions.id"))
    symbol: Mapped[str] = mapped_column(String, index=True)
    strategy: Mapped[StrategyType] = mapped_column(Enum(StrategyType))
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus), default=CandidateStatus.analyzing
    )

    price: Mapped[float] = mapped_column(Float)
    daily_change_pct: Mapped[float] = mapped_column(Float)
    quote_volume_24h: Mapped[float] = mapped_column(Float)
    spread_bps: Mapped[float] = mapped_column(Float)

    opportunity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    data_source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session: Mapped["MarketSession"] = relationship(back_populates="candidates")
    trade_plans: Mapped[list["TradePlan"]] = relationship(back_populates="candidate")


class TradePlan(Base):
    """
    A risk-validated execution intent. AlphaPilot submits it directly through
    Binance Agent OS MCP; Binance remains the external authorization/execution
    authority.
    """
    __tablename__ = "trade_plans"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("market_candidates.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))

    symbol: Mapped[str] = mapped_column(String)
    strategy: Mapped[StrategyType] = mapped_column(Enum(StrategyType))
    side: Mapped[str] = mapped_column(String, default="BUY")
    entry_price: Mapped[float] = mapped_column(Float)
    position_size_usdt: Mapped[float] = mapped_column(Float)
    estimated_slippage_bps: Mapped[float] = mapped_column(Float)
    stop_loss_pct: Mapped[float] = mapped_column(Float)
    profit_targets_pct: Mapped[dict] = mapped_column(JSON)  # e.g. {"15": 0.25, "30": 0.25, ...}

    opportunity_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    market_conditions: Mapped[dict] = mapped_column(JSON, default=dict)

    risk_check_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_check_notes: Mapped[dict] = mapped_column(JSON, default=dict)

    idempotency_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    status: Mapped[TradePlanStatus] = mapped_column(
        Enum(TradePlanStatus), default=TradePlanStatus.proposed
    )

    # Filled in after AlphaPilot submits through Binance Agent OS MCP and
    # reconciles the resulting order.
    binance_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    candidate: Mapped["MarketCandidate"] = relationship(back_populates="trade_plans")


class PositionStatus(str, PyEnum):
    open = "open"
    partially_exited = "partially_exited"
    closed = "closed"


class Position(Base):
    """
    Created once a TradePlan's Binance Agent OS execution is confirmed. The
    position monitor job
    watches this against live prices for stop-loss / profit-ladder / recovery
    exit / stagnation conditions — all deterministic, independent of whether
    the AI/agent loop is even running (see docs/RISK_ENGINE.md).
    """
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    trade_plan_id: Mapped[str] = mapped_column(ForeignKey("trade_plans.id"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    symbol: Mapped[str] = mapped_column(String, index=True)
    strategy: Mapped[StrategyType] = mapped_column(Enum(StrategyType))

    entry_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    remaining_fraction: Mapped[float] = mapped_column(Float, default=1.0)  # reduced by ladder sells
    stop_loss_pct: Mapped[float] = mapped_column(Float)
    profit_targets_pct: Mapped[dict] = mapped_column(JSON)
    targets_hit: Mapped[dict] = mapped_column(JSON, default=dict)  # {"15": true, ...}

    status: Mapped[PositionStatus] = mapped_column(Enum(PositionStatus), default=PositionStatus.open)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_checked_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Stagnation tracking (Recovery Hunter) — see docs/STRATEGIES.md #18.
    peak_price_since_entry: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExitSignal(Base):
    """
    A deterministic exit condition detected by the Position Monitor. When
    execution is enabled, AlphaPilot routes it through its direct Binance
    Agent OS execution service.
    """
    __tablename__ = "exit_signals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    position_id: Mapped[str] = mapped_column(ForeignKey("positions.id"))
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reason: Mapped[str] = mapped_column(String)  # hard_stop | profit_target | stagnation
    detail: Mapped[str] = mapped_column(Text)
    sell_fraction: Mapped[float] = mapped_column(Float)
    price_at_trigger: Mapped[float] = mapped_column(Float)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_status: Mapped[str] = mapped_column(String, default="pending")  # pending | submitted | filled | failed | confirmation_required
    binance_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class EarnRecommendation(Base):
    """
    Capital Optimizer output. Per docs/BINANCE_CAPABILITY_MATRIX.md, Simple
    Earn isn't part of Agent OS's documented scope, so this is always a
    recommendation only — it is not an Agent OS trading execution path
    record. See docs/STRATEGIES.md #24.
    """
    __tablename__ = "earn_recommendations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    idle_capital_usdt: Mapped[float] = mapped_column(Float)
    trading_reserve_usdt: Mapped[float] = mapped_column(Float)
    emergency_reserve_usdt: Mapped[float] = mapped_column(Float)
    recommended_earn_usdt: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="recommended")  # recommended only, never "executed" by us


class AccountSnapshot(Base):
    """
    Portfolio-relative risk checks need authenticated Binance Agent OS account
    state. AlphaPilot can persist a conservative snapshot from its direct MCP
    account read. Full portfolio valuation is not inferred from raw quantities.
    """
    __tablename__ = "account_snapshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    portfolio_value_usdt: Mapped[float] = mapped_column(Float)
    open_exposure_usdt: Mapped[float] = mapped_column(Float, default=0.0)
    margin_exposure_usdt: Mapped[float] = mapped_column(Float, default=0.0)
    realized_daily_loss_pct: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String, default="manual")  # manual | agent_os_mcp


class Notification(Base):
    """
    In-app notification center — see docs/STRATEGIES.md #55. Built first per
    the spec's own guidance ("if push notifications cannot be implemented
    within the timeline, implement an internal notification center first").
    """
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    kind: Mapped[str] = mapped_column(String)  # new_opportunity | approval_required | trade_executed |
    # stop_loss_triggered | profit_target_reached | margin_risk_elevated | position_stagnant |
    # capital_moved_to_earn | agent_error | binance_connection_failure
    title: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    strategy: Mapped[StrategyType] = mapped_column(Enum(StrategyType))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    candidates_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    proposals_created: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditEvent(Base):
    """Append-only. Never store secrets here — see docs/SECURITY.md."""
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String)
    asset: Mapped[str | None] = mapped_column(String, nullable=True)
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_result: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
