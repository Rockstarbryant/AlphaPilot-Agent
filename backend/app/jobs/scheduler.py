"""
Background worker process. Run as a separate process from the API server
(see docker-compose.yml / render.yaml's alphapilot-scheduler service) — this
is what makes recurring market scans and continuous position monitoring
actually autonomous, rather than only triggerable by a manual API call.

Market scans run every `settings.scan_interval_minutes` (default 60), not
once a day — see docs/STRATEGIES.md. Deliberately simple (asyncio loop +
sleep, not Celery/APScheduler) — see docs/DEPLOYMENT.md for the tradeoff.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import AsyncSessionLocal
from app.jobs.daily_market_reset import run_market_scan
from app.jobs.position_monitor import check_positions
from app.models.models import RiskPolicy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("alphapilot.scheduler")

settings = get_settings()

POSITION_MONITOR_INTERVAL_SECONDS = 60


async def _run_market_scan_for_all_users():
    async with AsyncSessionLocal() as db:
        policies = (await db.execute(select(RiskPolicy))).scalars().all()
        if not policies:
            logger.info("No users with a RiskPolicy yet — skipping market scan.")
            return
        for policy in policies:
            try:
                session = await run_market_scan(db, user_id=policy.user_id)
                logger.info(
                    "Market scan complete for user=%s session=%s regime=%s spot+futures gainers=%s losers=%s hot=%s",
                    policy.user_id, session.id, session.market_regime,
                    session.gainers_scanned, session.losers_scanned, session.hot_candidates_found,
                )
            except Exception:
                logger.exception("Market scan failed for user=%s", policy.user_id)


async def _run_position_monitor_once():
    async with AsyncSessionLocal() as db:
        try:
            signals = await check_positions(db)
            if signals:
                logger.info("Position monitor generated %d exit signal(s).", len(signals))
        except Exception:
            logger.exception("Position monitor pass failed.")


async def market_scan_loop():
    interval_seconds = max(60, settings.scan_interval_minutes * 60)
    while True:
        logger.info("Running market scan (spot + futures, all strategies).")
        started = datetime.now(timezone.utc)
        await _run_market_scan_for_all_users()
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        await asyncio.sleep(max(1.0, interval_seconds - elapsed))


async def position_monitor_loop():
    while True:
        await _run_position_monitor_once()
        await asyncio.sleep(POSITION_MONITOR_INTERVAL_SECONDS)


async def main():
    logger.info("AlphaPilot scheduler starting. Market scan interval: %d minutes.",
                settings.scan_interval_minutes)
    await asyncio.gather(market_scan_loop(), position_monitor_loop())


if __name__ == "__main__":
    asyncio.run(main())
