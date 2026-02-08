"""Worker process for scheduled accrual jobs.

Replaces the placeholder command in docker-compose.yml.
Runs an asyncio loop that executes time-based accruals once daily.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from app.db import get_session_factory

logger = logging.getLogger(__name__)

ACCRUAL_INTERVAL_SECONDS = 86400  # 24 hours


async def run_accrual_loop() -> None:
    """Main worker loop that runs time-based accruals, carryover, and expiration daily."""
    from app.services.accrual import run_time_based_accruals
    from app.services.carryover import run_carryover_processing, run_expiration_processing

    logger.info("Accrual worker started")
    session_factory = get_session_factory()

    while True:
        today = date.today()
        logger.info("Running time-based accruals for %s", today)
        try:
            async with session_factory() as session:
                result = await run_time_based_accruals(session, today)
            logger.info(
                "Accrual run complete for %s: processed=%d accrued=%d skipped=%d errors=%d",
                today,
                result.processed,
                result.accrued,
                result.skipped,
                result.errors,
            )
        except Exception:
            logger.exception("Accrual run failed for %s", today)

        # Year-end carryover (only fires on Jan 1)
        try:
            async with session_factory() as session:
                co_result = await run_carryover_processing(session, today)
            if co_result.carryovers_processed > 0 or co_result.expirations_processed > 0:
                logger.info(
                    "Carryover run for %s: carried=%d expired=%d skipped=%d errors=%d",
                    today,
                    co_result.carryovers_processed,
                    co_result.expirations_processed,
                    co_result.skipped,
                    co_result.errors,
                )
        except Exception:
            logger.exception("Carryover run failed for %s", today)

        # Balance expiration (calendar-date + post-carryover)
        try:
            async with session_factory() as session:
                exp_result = await run_expiration_processing(session, today)
            if exp_result.expirations_processed > 0:
                logger.info(
                    "Expiration run for %s: expired=%d skipped=%d errors=%d",
                    today,
                    exp_result.expirations_processed,
                    exp_result.skipped,
                    exp_result.errors,
                )
        except Exception:
            logger.exception("Expiration run failed for %s", today)

        await asyncio.sleep(ACCRUAL_INTERVAL_SECONDS)


def main() -> None:
    """Entry point for the worker process."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(run_accrual_loop())


if __name__ == "__main__":
    main()
