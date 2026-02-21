from __future__ import annotations

"""Live runtime entrypoint for afternoon monitoring session."""

import asyncio
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger

from .config import Settings, get_settings
from .engine import StrategyEngine
from .fetcher import EastMoneyFetcher
from .notifier import NotificationGateway
from .pool_manager import PoolManager, parse_hhmm
from .runtime_status import RuntimeStatus


def configure_logger() -> None:
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


def now_in_trading_timezone(timezone_name: str) -> datetime:
    """Return current wall-clock datetime in configured trading timezone."""
    return datetime.now(ZoneInfo(timezone_name)).replace(tzinfo=None)


async def run_live(
    settings: Settings | None = None,
    notifier: NotificationGateway | None = None,
    runtime_status: RuntimeStatus | None = None,
    trade_date: date | None = None,
    *,
    wait_until_start: bool = True,
    preset_codes: set[str] | None = None,
) -> dict[str, Any]:
    """Execute one full monitoring session for the current trading day."""
    settings = settings or get_settings()
    configure_logger()
    runtime_status = runtime_status or RuntimeStatus()

    trade_date = trade_date or now_in_trading_timezone(settings.TRADING_TIMEZONE).date()
    pool_manager = PoolManager(settings)
    pool = pool_manager.build_daily_pool(trade_date)
    if preset_codes is not None:
        normalized_codes = {str(code).strip() for code in preset_codes if str(code).strip()}
        pool = [item for item in pool if item.code in normalized_codes]
        logger.info("preset monitor list applied: {} symbols", len(pool))

    logger.info("daily pool built: {} symbols", len(pool))

    engine = StrategyEngine(
        ask_drop_threshold=settings.ASK_DROP_THRESHOLD if settings.ASK_DROP_THRESHOLD is not None else settings.VOL_DROP_THRESHOLD,
        confirm_minutes=settings.LIVE_CONFIRM_MINUTES,
        min_abs_delta_ask=settings.MIN_ABS_DELTA_ASK,
    )
    engine.register_pool(pool)

    fetcher = EastMoneyFetcher(settings)
    notifier = notifier or NotificationGateway(settings.DINGTALK_URL, keyword=settings.DINGTALK_KEYWORD)

    start = parse_hhmm(settings.MONITOR_START_TIME)
    end = parse_hhmm(settings.MONITOR_END_TIME)

    now = now_in_trading_timezone(settings.TRADING_TIMEZONE)
    runtime_status.set_monitor_window(in_monitor_window(now, start, end), now=now)
    runtime_status.mark_live_started(now)
    if now.time() > end:
        logger.info("current time is after monitor window; exit")
        runtime_status.mark_live_finished(now)
        return {"rounds": 0, "alerts": 0, "state": engine.summary()}
    if now.time() < start:
        if not wait_until_start:
            logger.info("current time is before monitor window and wait_until_start=false; skip")
            runtime_status.mark_live_finished(now)
            return {"rounds": 0, "alerts": 0, "state": engine.summary()}
        # Allow pre-start launch and sleep until market monitor window begins.
        wait_seconds = (datetime.combine(now.date(), start) - now).total_seconds()
        logger.info("waiting {} seconds until monitor window", int(wait_seconds))
        await asyncio.sleep(max(wait_seconds, 0))

    rounds = 0
    alerts = 0

    def _send_event(event) -> None:
        nonlocal alerts
        if notifier.send_alert(event):
            alerts += 1
            runtime_status.mark_alert()
            logger.info("alert sent: {} rule={} drop={:.2%}", event.code, event.trigger_rule, event.drop_ratio)

    try:
        while in_monitor_window(now_in_trading_timezone(settings.TRADING_TIMEZONE), start, end):
            runtime_status.set_monitor_window(True)
            runtime_status.mark_poll()
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
                _send_event(event)

            await asyncio.sleep(settings.POLL_INTERVAL_SEC)

        for event in engine.flush_pending():
            _send_event(event)
    except Exception as exc:
        runtime_status.mark_error(str(exc))
        raise
    finally:
        runtime_status.set_monitor_window(False)
        runtime_status.mark_live_finished()

    summary = engine.summary()
    logger.info("runtime summary rounds={} alerts={} state={}", rounds, alerts, summary)
    return {"rounds": rounds, "alerts": alerts, "state": summary}


def main() -> None:
    """Sync CLI entrypoint that boots the async live loop."""
    asyncio.run(run_live())


if __name__ == "__main__":
    main()
