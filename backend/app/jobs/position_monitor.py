"""
Position Monitor. Runs independently of the AI/agent loop. It evaluates
deterministic exit rules and raises ExitSignal rows for the human (or their
connected AI client) to act on. AlphaPilot's backend is not an allowlisted
Binance Agent OS MCP client (see BINANCE_AGENT_OS_REFACTOR.md), so it never
executes an exit itself — see app/services/panic_advisor.py for the
explanation surface, and POST /api/positions/exit-signals/{id}/confirm-execution
for closing the loop once the human/client has placed the exit through
Binance Agent OS MCP directly.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.binance.market_data import BinanceMarketDataClient
from app.core.config import get_settings
from app.models.models import ExitSignal, Position, PositionStatus, RiskPolicy
from app.services.notifications import notify

settings = get_settings()


async def check_positions(db: AsyncSession) -> list[ExitSignal]:
    result = await db.execute(
        select(Position).where(Position.status.in_([PositionStatus.open, PositionStatus.partially_exited]))
    )
    open_positions = result.scalars().all()
    if not open_positions:
        return []

    client = BinanceMarketDataClient()
    signals: list[ExitSignal] = []
    try:
        tickers = {t.symbol: t for t in await client.get_24h_tickers()}

        for pos in open_positions:
            ticker = tickers.get(pos.symbol)
            if ticker is None or ticker.is_stale:
                continue  # stale/missing data: skip this cycle rather than act on it

            price = ticker.last_price
            pnl_pct = (price - pos.entry_price) / pos.entry_price * 100

            pos.last_checked_price = price
            pos.last_checked_at = datetime.now(timezone.utc)
            pos.peak_price_since_entry = max(pos.peak_price_since_entry or pos.entry_price, price)

            policy_result = await db.execute(select(RiskPolicy).where(RiskPolicy.user_id == pos.user_id))
            policy = policy_result.scalar_one_or_none()
            if policy is None:
                continue

            stop = (
                policy.recovery_hard_stop_pct if pos.strategy == "recovery_hunter"
                else policy.gainer_hard_stop_pct
            )

            # --- Hard stop: always checked first, cannot be overridden ---
            if pnl_pct <= stop:
                signal = ExitSignal(
                    position_id=pos.id,
                    reason="hard_stop",
                    detail=f"{pos.symbol} at {pnl_pct:.1f}% pnl hit hard stop {stop:.1f}%. Full exit required.",
                    sell_fraction=1.0 - _fraction_already_sold(pos),
                    price_at_trigger=price,
                )
                signals.append(signal)
                db.add(signal)
                await notify(
                    db, user_id=pos.user_id, kind="stop_loss_triggered",
                    title=f"{pos.symbol} hit its hard stop", detail=signal.detail,
                )
                continue

            # --- Profit ladder (Gainer) / take-profit (Recovery) ---
            for target_pct_str, sell_frac in pos.profit_targets_pct.items():
                target_pct = float(target_pct_str)
                already_hit = pos.targets_hit.get(target_pct_str, False)
                if not already_hit and pnl_pct >= target_pct:
                    signal = ExitSignal(
                        position_id=pos.id,
                        reason="profit_target",
                        detail=(
                            f"{pos.symbol} reached +{target_pct:.1f}% "
                            f"(current {pnl_pct:.1f}%). Sell {sell_frac*100:.0f}%."
                        ),
                        sell_fraction=float(sell_frac),
                        price_at_trigger=price,
                        target_pct=target_pct,
                    )
                    signals.append(signal)
                    db.add(signal)
                    await notify(
                        db, user_id=pos.user_id, kind="profit_target_reached",
                        title=f"{pos.symbol} reached +{target_pct:.0f}%", detail=signal.detail,
                    )

            # --- Stagnation (Recovery Hunter only) ---
            if pos.strategy == "recovery_hunter" and pos.status != PositionStatus.closed:
                hours_open = (datetime.now(timezone.utc) - pos.opened_at).total_seconds() / 3600
                if hours_open >= settings.recovery_max_stagnation_hours:
                    weak_momentum = abs(pnl_pct) < settings.recovery_min_required_momentum_pct
                    if weak_momentum:
                        signal = ExitSignal(
                            position_id=pos.id,
                            reason="stagnation",
                            detail=(
                                f"{pos.symbol} open {hours_open:.0f}h with only {pnl_pct:.1f}% "
                                f"movement — below required momentum. Full exit recommended."
                            ),
                            sell_fraction=1.0 - _fraction_already_sold(pos),
                            price_at_trigger=price,
                        )
                        signals.append(signal)
                        db.add(signal)
                        await notify(
                            db, user_id=pos.user_id, kind="position_stagnant",
                            title=f"{pos.symbol} exited on stagnation", detail=signal.detail,
                        )

        await db.commit()
    finally:
        await client.close()

    # Detection ends here. Execution is intentionally NOT performed by
    # AlphaPilot (see module docstring) — signals surface via
    # GET /api/positions/exit-signals and the notify() calls above for the
    # human, or their connected AI client, to act on through Binance Agent
    # OS MCP directly and then confirm.
    return signals


def _fraction_already_sold(pos: Position) -> float:
    return 1.0 - pos.remaining_fraction
