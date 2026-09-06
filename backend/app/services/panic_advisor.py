"""
"The trade is going against me, should I close it?" — this is the module
Claude (or any allowlisted MCP client) calls when relaying that question from
a user. It never decides FOR the human and never touches Binance; it re-runs
the same deterministic analysis the original proposal was built on against
*current* price/indicators and reports whether the original thesis still
holds, what would invalidate it, and where the hard stop already sits.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.market.coin_analysis import analyze_symbol
from app.models.models import Position


class PositionNotFound(RuntimeError):
    pass


async def explain_position(db: AsyncSession, *, position_id: str, question: str = "") -> dict:
    position = await db.get(Position, position_id)
    if position is None:
        raise PositionNotFound(f"No position found with id {position_id}.")

    current = await analyze_symbol(position.symbol)
    pnl_pct = (
        (current.price - position.entry_price) / position.entry_price * 100
        if position.entry_price else 0.0
    )

    # A LONG position's thesis is "still valid" as long as the deterministic
    # signals still say LONG, regardless of current P&L sign — P&L alone
    # isn't evidence the thesis broke, only that price is between entry and
    # target/stop right now. (AlphaPilot's strategies are long-only spot/
    # margin-long today, so LONG is the only "thesis intact" bias.)
    thesis_still_valid = current.bias == "LONG"

    distance_to_stop_pct = pnl_pct - position.stop_loss_pct  # negative = past the stop already

    if distance_to_stop_pct <= 0:
        recommendation = "CLOSE"
        headline = (
            f"{position.symbol} is at or past its {position.stop_loss_pct:.1f}% hard stop "
            f"(currently {pnl_pct:+.1f}%). The deterministic risk engine would already be "
            "generating an exit signal for this."
        )
    elif not thesis_still_valid:
        recommendation = "CONSIDER_CLOSING"
        headline = (
            f"{position.symbol} hasn't hit its stop ({pnl_pct:+.1f}% vs {position.stop_loss_pct:.1f}% stop), "
            f"but the original bullish thesis no longer holds — current signals read {current.bias}."
        )
    else:
        recommendation = "HOLD"
        headline = (
            f"{position.symbol} is at {pnl_pct:+.1f}% against a {position.stop_loss_pct:.1f}% stop, and the "
            "underlying signals that supported this position are still intact."
        )

    return {
        "position_id": position.id,
        "symbol": position.symbol,
        "user_question": question,
        "entry_price": position.entry_price,
        "current_price": current.price,
        "pnl_pct": round(pnl_pct, 2),
        "stop_loss_pct": position.stop_loss_pct,
        "distance_to_stop_pct": round(distance_to_stop_pct, 2),
        "current_bias": current.bias,
        "current_confidence": current.confidence,
        "current_rationale": current.rationale,
        "thesis_still_valid": thesis_still_valid,
        "recommendation": recommendation,
        "headline": headline,
        "note": (
            "This is analysis, not an instruction — the human makes the final call. AlphaPilot never "
            "closes a position itself; if they decide to close, do it through Binance Agent OS MCP "
            "directly, then call record_fill / confirm-execution here so AlphaPilot's records match reality."
        ),
    }
