from __future__ import annotations

"""Live runtime entrypoint for afternoon monitoring session."""

import asyncio
from datetime import date, datetime, time

from loguru import logger

from .config import get_settings
from .engine import StrategyEngine
from .fetcher import EastMoneyFetcher
from .notifier import NotificationGateway
from .pool_manager import PoolManager, parse_hhmm


def _configure_logger() -> None:
    """Configure file and stdout log sinks for runtime observability."""
    logger.remove()
    logger.add(
        "logs/runtime_{time:YYYY-MM-DD}.log",
        level="INFO",
        rotation="00:00",
        retention="14 days",
        enqueue=True,
    )
    logger.add(lambda msg: print(msg, end=""), level="INFO")


def in_monitor_window(now: datetime, start: time, end: time) -> bool:
    """Check whether current wall-clock time is within monitor range."""
    return start <= now.time() <= end


async def run_live() -> None:
    """Execute one full monitoring session for the current trading day."""
    settings = get_settings()
    _configure_logger()

    pool_manager = PoolManager(settings)
    pool = pool_manager.build_daily_pool(date.today())
    logger.info("daily pool built: {} symbols", len(pool))

    engine = StrategyEngine(
        ask_drop_threshold=settings.ASK_DROP_THRESHOLD if settings.ASK_DROP_THRESHOLD is not None else settings.VOL_DROP_THRESHOLD,
        volume_spike_threshold=settings.VOLUME_SPIKE_THRESHOLD,
        confirm_minutes=settings.BACKTEST_CONFIRM_MINUTES,
        signal_combination=settings.SIGNAL_COMBINATION,  # type: ignore[arg-type]
        min_abs_delta_ask=settings.MIN_ABS_DELTA_ASK,
        min_abs_delta_volume=settings.MIN_ABS_DELTA_VOLUME,
    )
    engine.register_pool(pool)

    fetcher = EastMoneyFetcher(settings)
    notifier = NotificationGateway(settings.DINGTALK_URL, keyword=settings.DINGTALK_KEYWORD)

    start = parse_hhmm(settings.MONITOR_START_TIME)
    end = parse_hhmm(settings.MONITOR_END_TIME)

    now = datetime.now()
    if now.time() > end:
        logger.info("current time is after monitor window; exit")
        return
    if now.time() < start:
        # Allow pre-start launch and sleep until market monitor window begins.
        wait_seconds = (datetime.combine(now.date(), start) - now).total_seconds()
        logger.info("waiting {} seconds until monitor window", int(wait_seconds))
        await asyncio.sleep(max(wait_seconds, 0))

    rounds = 0
    alerts = 0

    while in_monitor_window(datetime.now(), start, end):
        rounds += 1
        codes = engine.monitorable_codes()
        if not codes:
            logger.info("no monitorable symbols left; stopping early")
            break

        snapshots = await fetcher.fetch_snapshots(codes)
        for snapshot in snapshots:
            event = engine.evaluate(snapshot)
            if event is None:
                continue

            if notifier.send_alert(event):
                alerts += 1
                logger.info("alert sent: {} drop={:.2%}", event.code, event.drop_ratio)

        await asyncio.sleep(settings.POLL_INTERVAL_SEC)

    logger.info("runtime summary rounds={} alerts={} state={}", rounds, alerts, engine.summary())


def main() -> None:
    """Sync CLI entrypoint that boots the async live loop."""
    asyncio.run(run_live())


if __name__ == "__main__":
    main()
