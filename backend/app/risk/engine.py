"""
Deterministic Risk Engine.

Rule from docs/RISK_ENGINE.md, non-negotiable: the LLM/agent layer may
recommend a trade plan, but only this module decides whether it is allowed to
reach the execution service. Nothing here reads an AI-produced number for a
limit — every threshold comes from RiskPolicy (DB, user-set) or Settings
(env). If you're tempted to let the model override a check here, don't — put
that logic in the strategy/analysis layer instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.models import RiskPolicy, TradePlan


@dataclass
class RiskCheckResult:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)

    def fail(self, check: str, note: str):
        self.passed = False
        self.checks[check] = False
        self.notes[check] = note

    def ok(self, check: str):
        self.checks[check] = True


@dataclass
class TradeIntent:
    """What a strategy wants to do, before risk validation."""
    symbol: str
    strategy: str
    position_size_usdt: float
    entry_price: float
    estimated_slippage_bps: float
    stop_loss_pct: float
    opportunity_score: float
    is_margin: bool = False
    leverage: float = 1.0
    data_age_seconds: float = 0.0
    max_data_age_seconds: float = 30.0


class RiskEngine:
    def __init__(self, policy: RiskPolicy):
        self.policy = policy

    def validate(
        self,
        intent: TradeIntent,
        *,
        current_portfolio_value_usdt: float,
        current_open_exposure_usdt: float,
        current_margin_exposure_usdt: float,
        realized_daily_loss_pct: float,
        open_positions_for_symbol: int,
        pending_plans_for_symbol: int,
        emergency_halted: bool,
    ) -> RiskCheckResult:
        result = RiskCheckResult(passed=True)

        # --- Emergency stop always wins, first check, no exceptions ---
        if emergency_halted:
            result.fail("emergency_stop", "Agent is emergency-halted; no new trades permitted.")
            return result
        result.ok("emergency_stop")

        # --- Stale data protection ---
        if intent.data_age_seconds > intent.max_data_age_seconds:
            result.fail(
                "stale_data",
                f"Market data is {intent.data_age_seconds:.1f}s old "
                f"(max {intent.max_data_age_seconds}s). Trade blocked.",
            )
        else:
            result.ok("stale_data")

        # --- Duplicate trade protection ---
        if open_positions_for_symbol > 0:
            result.fail("duplicate_position", f"{intent.symbol} already has an open position.")
        elif pending_plans_for_symbol > 0:
            result.fail("duplicate_pending", f"{intent.symbol} already has a pending trade plan.")
        else:
            result.ok("duplicate_trade")

        # --- Max trade size ---
        limit = (
            self.policy.max_margin_trade_usdt if intent.is_margin
            else self.policy.max_spot_trade_usdt
        )
        if intent.position_size_usdt > limit:
            result.fail(
                "max_trade_size",
                f"${intent.position_size_usdt:.2f} exceeds max trade size ${limit:.2f}.",
            )
        else:
            result.ok("max_trade_size")

        # --- Max allocation (this trade as % of portfolio) ---
        if current_portfolio_value_usdt > 0:
            alloc_pct = (intent.position_size_usdt / current_portfolio_value_usdt) * 100
            alloc_limit = (
                self.policy.max_margin_allocation_pct if intent.is_margin
                else self.policy.max_spot_allocation_pct
            )
            if alloc_pct > alloc_limit:
                result.fail(
                    "max_allocation",
                    f"{alloc_pct:.1f}% of portfolio exceeds max allocation {alloc_limit:.1f}%.",
                )
            else:
                result.ok("max_allocation")
        else:
            result.fail("max_allocation", "Portfolio value is zero or unknown.")

        # --- Max portfolio exposure after this trade ---
        projected_exposure = current_open_exposure_usdt + intent.position_size_usdt
        if current_portfolio_value_usdt > 0:
            exposure_pct = (projected_exposure / current_portfolio_value_usdt) * 100
            max_total_exposure_pct = (
                self.policy.max_spot_allocation_pct + self.policy.max_margin_allocation_pct
            ) * 3  # generous ceiling across many concurrent positions; tune via policy later
            if exposure_pct > max_total_exposure_pct:
                result.fail(
                    "portfolio_exposure",
                    f"Projected total exposure {exposure_pct:.1f}% exceeds ceiling "
                    f"{max_total_exposure_pct:.1f}%.",
                )
            else:
                result.ok("portfolio_exposure")

        # --- Margin-specific: leverage ---
        if intent.is_margin:
            if intent.leverage > self.policy.max_leverage:
                result.fail(
                    "max_leverage",
                    f"Leverage {intent.leverage}x exceeds max {self.policy.max_leverage}x.",
                )
            else:
                result.ok("max_leverage")

            margin_exposure_pct = (
                (current_margin_exposure_usdt + intent.position_size_usdt)
                / current_portfolio_value_usdt * 100
                if current_portfolio_value_usdt > 0 else 100.0
            )
            if margin_exposure_pct > self.policy.max_margin_allocation_pct:
                result.fail(
                    "margin_exposure",
                    f"Margin exposure {margin_exposure_pct:.1f}% exceeds max "
                    f"{self.policy.max_margin_allocation_pct:.1f}%.",
                )
            else:
                result.ok("margin_exposure")

        # --- Daily loss circuit breaker ---
        if realized_daily_loss_pct <= -abs(self.policy.max_daily_loss_pct):
            result.fail(
                "daily_loss_limit",
                f"Realized daily loss {realized_daily_loss_pct:.1f}% has hit the "
                f"{self.policy.max_daily_loss_pct:.1f}% circuit breaker. No new trades today.",
            )
        else:
            result.ok("daily_loss_limit")

        # --- Slippage ---
        if intent.estimated_slippage_bps > self.policy.max_slippage_bps:
            result.fail(
                "max_slippage",
                f"Estimated slippage {intent.estimated_slippage_bps:.1f}bps exceeds max "
                f"{self.policy.max_slippage_bps:.1f}bps.",
            )
        else:
            result.ok("max_slippage")

        # --- Minimum opportunity/recovery score gate ---
        # Scheduled scanners (gainer/recovery/hot) use high floors (default 65)
        # because they already pre-filter for strong setups.
        # user_requested (chat-driven) uses analysis.confidence, which is a
        # conservative |composite| * 100 scale (directional bias starts \~15).
        # Applying the scanner floor of 65 made every chat proposal fail.
        # Keep a modest floor so pure noise still fails, while mild-but-real
        # directional signals can pass. Size/leverage are already scaled by
        # confidence and capped by policy.
        if intent.strategy == "recovery_hunter":
            score_floor = self.policy.min_recovery_score
        elif intent.strategy == "user_requested":
            score_floor = 20.0  # allow moderate-confidence chat proposals
        else:
            score_floor = self.policy.min_opportunity_score

        if intent.opportunity_score < score_floor:
            result.fail(
                "min_score",
                f"Score {intent.opportunity_score:.1f} is below required {score_floor:.1f} "
                f"for {intent.strategy}.",
            )
        else:
            result.ok("min_score")

        return result

    @staticmethod
    def check_hard_stop(strategy: str, pnl_pct: float, policy: RiskPolicy) -> bool:
        """
        Returns True if a position must be force-exited. This check must run
        on every price update independent of the AI/agent loop being up.
        """
        stop = (
            policy.recovery_hard_stop_pct if strategy == "recovery_hunter"
            else policy.gainer_hard_stop_pct
        )
        return pnl_pct <= stop