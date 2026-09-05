"""
Position Monitor. Runs independently of the AI/agent loop. It evaluates
deterministic exit rules and, when execution is enabled, routes exit signals
through AlphaPilot's direct Binance Agent OS service.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.binance.market_data import BinanceMarketDataClient
from app.core.config import get_settings
from app.models.models import AgentConfig, ExitSignal, Position, PositionStatus, RiskPolicy, TradingMode
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

    # Execution is a separate phase so the deterministic detector never
    # marks a position closed before Binance confirms the fill.
    from app.services.binance_agent_os import BinanceAgentOSService
    for signal in signals:
        position = await db.get(Position, signal.position_id)
        if position is None:
            continue
        config_result = await db.execute(select(AgentConfig).where(AgentConfig.user_id == position.user_id))
        config = config_result.scalar_one_or_none()
        if config is None or config.trading_mode == TradingMode.read_only:
            continue
        try:
            await BinanceAgentOSService(db).execute_exit_signal(signal)
        except Exception:
            # The signal remains pending/failed and is visible for retry;
            # never convert a detected exit into a false closed state.
            continue

    return signals


def _fraction_already_sold(pos: Position) -> float:
    return 1.0 - pos.remaining_fraction
