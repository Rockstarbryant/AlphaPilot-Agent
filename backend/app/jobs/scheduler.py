"""
Background worker process. Run as a separate process from the API server
(see docker-compose.yml) — this is what makes the 00:00 UTC discovery and
continuous position monitoring actually autonomous, rather than only
triggerable by a manual API call.

Deliberately simple (asyncio loop + sleep, not Celery/APScheduler) for a
hackathon timeline — see docs/DEPLOYMENT.md for the tradeoff and what a
production upgrade would look like.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import AsyncSessionLocal
from app.jobs.daily_market_reset import run_daily_market_reset
from app.jobs.position_monitor import check_positions
from app.models.models import RiskPolicy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("alphapilot.scheduler")

settings = get_settings()

POSITION_MONITOR_INTERVAL_SECONDS = 60
DAILY_RESET_CHECK_INTERVAL_SECONDS = 60


async def _run_daily_reset_for_all_users():
    async with AsyncSessionLocal() as db:
        policies = (await db.execute(select(RiskPolicy))).scalars().all()
        if not policies:
            logger.info("No users with a RiskPolicy yet — skipping daily reset.")
            return
        for policy in policies:
            try:
                session = await run_daily_market_reset(db, user_id=policy.user_id)
                logger.info(
                    "Daily reset complete for user=%s session=%s regime=%s gainers=%s losers=%s",
                    policy.user_id, session.id, session.market_regime,
                    session.gainers_scanned, session.losers_scanned,
                )
            except Exception:
                logger.exception("Daily reset failed for user=%s", policy.user_id)


async def _run_position_monitor_once():
    async with AsyncSessionLocal() as db:
        try:
            signals = await check_positions(db)
            if signals:
                logger.info("Position monitor generated %d exit signal(s).", len(signals))
        except Exception:
            logger.exception("Position monitor pass failed.")


async def daily_reset_loop():
    last_run_date: str | None = None
    while True:
        now = datetime.now(timezone.utc)
        target_reached = (
            now.hour == settings.daily_session_hour_utc
            and now.minute >= settings.daily_session_minute_utc
        )
        today_str = now.strftime("%Y-%m-%d")
        if target_reached and last_run_date != today_str:
            logger.info("00:00 UTC reached — running daily market reset.")
            await _run_daily_reset_for_all_users()
            last_run_date = today_str
        await asyncio.sleep(DAILY_RESET_CHECK_INTERVAL_SECONDS)


async def position_monitor_loop():
    while True:
        await _run_position_monitor_once()
        await asyncio.sleep(POSITION_MONITOR_INTERVAL_SECONDS)


async def main():
    logger.info("AlphaPilot scheduler starting. Daily reset target: %02d:%02d UTC",
                settings.daily_session_hour_utc, settings.daily_session_minute_utc)
    await asyncio.gather(daily_reset_loop(), position_monitor_loop())


if __name__ == "__main__":
    asyncio.run(main())
