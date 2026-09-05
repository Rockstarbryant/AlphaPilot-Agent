"""
Capital Optimizer. Per docs/BINANCE_CAPABILITY_MATRIX.md, Simple Earn is not
part of Agent OS's documented scope, so this module NEVER subscribes or
redeems anything — it only produces a recommendation row; it does not submit Earn operations.
If a future capability-matrix update confirms Earn is reachable through
Agent OS with human confirmation, this is the module to extend, not replace.
"""
from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()


def evaluate_idle_capital(
    *,
    total_capital_usdt: float,
    open_positions_value_usdt: float,
    pending_proposals_value_usdt: float,
) -> dict:
    """
    Philosophy: capital should have a reason for being where it is. This
    never allocates 100% to Earn — trading_reserve_pct and
    emergency_reserve_usdt are always protected first.
    """
    trading_reserve = total_capital_usdt * (settings.trading_reserve_pct / 100)
    emergency_reserve = settings.emergency_reserve_usdt

    committed = open_positions_value_usdt + pending_proposals_value_usdt
    protected = trading_reserve + emergency_reserve

    idle = max(0.0, total_capital_usdt - committed - protected)

    if idle <= 0:
        return {
            "idle_capital_usdt": 0.0,
            "trading_reserve_usdt": trading_reserve,
            "emergency_reserve_usdt": emergency_reserve,
            "recommended_earn_usdt": 0.0,
            "reason": (
                "No idle capital — funds are committed to open positions, pending "
                "proposals, the configured trading reserve, or the emergency reserve."
            ),
        }

    return {
        "idle_capital_usdt": idle,
        "trading_reserve_usdt": trading_reserve,
        "emergency_reserve_usdt": emergency_reserve,
        "recommended_earn_usdt": idle,
        "reason": (
            f"${idle:.2f} is idle after reserving ${trading_reserve:.2f} for trading "
            f"({settings.trading_reserve_pct:.0f}%) and ${emergency_reserve:.2f} emergency "
            f"reserve. Recommend moving it to a verified Binance Simple Earn Flexible "
            f"product manually — Agent OS does not currently expose Earn subscribe/redeem, "
            f"so AlphaPilot will not and cannot execute this automatically. "
            f"See docs/BINANCE_CAPABILITY_MATRIX.md."
        ),
    }
