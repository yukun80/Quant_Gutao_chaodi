from __future__ import annotations

"""Unified entrypoint: pre-open summary + live monitor scheduler."""

import asyncio
from datetime import date, datetime

from loguru import logger

from .config import Settings, get_settings
from .fetcher import EastMoneyFetcher
from .main import configure_logger, in_monitor_window, now_in_trading_timezone, run_live
from .models import StockSnapshot
from .notifier import NotificationGateway
from .pool_manager import PoolManager, parse_hhmm
from .runtime_status import RuntimeStatus
from .trading_calendar import is_trading_day


def format_preopen_summary_messages(
    *,
    trade_date: date,
    run_at: datetime,
    snapshots: list[StockSnapshot],
    max_rows_per_chunk: int,
) -> list[str]:
    """Build summary messages for 09:26 one-word limit-down scan."""
    head = [
        f"时间: {run_at:%Y-%m-%d %H:%M:%S}",
        f"交易日: {trade_date:%Y-%m-%d}",
        f"09:26一字跌停统计: {len(snapshots)}只",
    ]
    if not snapshots:
        return ["\n".join(head + ["结果: 0只"])]

    lines = [f"{idx}) {item.code} {item.name} 卖1单数: {item.ask_v1}" for idx, item in enumerate(snapshots, start=1)]
    chunk_size = max(max_rows_per_chunk, 1)
    message_list: list[str] = []
    total_chunks = (len(lines) + chunk_size - 1) // chunk_size
    for chunk_idx in range(total_chunks):
        begin = chunk_idx * chunk_size
        end = begin + chunk_size
        chunk_lines = lines[begin:end]
        chunk_head = list(head)
        if total_chunks > 1:
            chunk_head.append(f"分片: {chunk_idx + 1}/{total_chunks}")
        message_list.append("\n".join(chunk_head + [""] + chunk_lines))
    return message_list


async def scan_preopen_one_word_limit_down(
    settings: Settings,
    trade_date: date,
) -> list[StockSnapshot]:
    """Fetch full market snapshots once and keep one-word limit-down symbols."""
    pool = PoolManager(settings).build_daily_pool(trade_date=trade_date)
    codes = [item.code for item in pool]
    if not codes:
        return []

    snapshots = await EastMoneyFetcher(settings).fetch_snapshots(codes)
    selected = [item for item in snapshots if item.is_one_word_limit_down]
    # Keep output deterministic for easier alert review and regression tests.
    selected.sort(key=lambda item: (item.code, item.name))
    return selected


def notify_preopen_summary(
    *,
    settings: Settings,
    notifier: NotificationGateway,
    runtime_status: RuntimeStatus,
    trade_date: date,
    run_at: datetime,
    snapshots: list[StockSnapshot],
) -> None:
    """Send formatted pre-open summary messages via DingTalk webhook."""
    messages = format_preopen_summary_messages(
        trade_date=trade_date,
        run_at=run_at,
        snapshots=snapshots,
        max_rows_per_chunk=settings.PREOPEN_MESSAGE_MAX_ROWS_PER_CHUNK,
    )
    for body in messages:
        ok = notifier.send_text(title="Gutao_Chaodi 09:26 一字跌停统计", body=body, code="preopen_summary")
        if ok:
            runtime_status.mark_alert(now=run_at)


async def run_live_scheduler(
    runtime_status: RuntimeStatus,
    notifier: NotificationGateway,
) -> None:
    """Run daily pre-open summary then one live session in monitor window."""
    settings = get_settings()
    start = parse_hhmm(settings.MONITOR_START_TIME)
    end = parse_hhmm(settings.MONITOR_END_TIME)
    preopen_scan_time = parse_hhmm(settings.PREOPEN_SCAN_TIME)

    state_date: date | None = None
    preopen_done = False
    is_trade_day = False
    selected_codes: set[str] = set()

    while True:
        now = now_in_trading_timezone(settings.TRADING_TIMEZONE)
        if state_date != now.date():
            state_date = now.date()
            preopen_done = False
            is_trade_day = False
            selected_codes = set()

        in_window = in_monitor_window(now, start, end)
        runtime_status.set_monitor_window(in_window, now=now)

        if not preopen_done and now.time() >= preopen_scan_time:
            try:
                is_trade_day = is_trading_day(now.date())
            except Exception as exc:
                runtime_status.mark_error(f"trading day check failed: {exc}", now=now)
                logger.exception("trading day check failed: {}", exc)
                is_trade_day = False

            if not is_trade_day:
                preopen_done = True
                logger.info("today is not trading day, skip pre-open summary and live session")
            else:
                try:
                    snapshots = await scan_preopen_one_word_limit_down(settings=settings, trade_date=now.date())
                    notify_preopen_summary(
                        settings=settings,
                        notifier=notifier,
                        runtime_status=runtime_status,
                        trade_date=now.date(),
                        run_at=now,
                        snapshots=snapshots,
                    )
                    selected_codes = {item.code for item in snapshots}
                    logger.info("pre-open summary done, selected {} symbols", len(selected_codes))
                except Exception as exc:
                    runtime_status.mark_error(f"pre-open scan failed: {exc}", now=now)
                    logger.exception("pre-open scan failed: {}", exc)
                    selected_codes = set()
                preopen_done = True

        if in_window:
            if runtime_status.last_live_date == now.date():
                await asyncio.sleep(15)
                continue
            if not preopen_done:
                await asyncio.sleep(5)
                continue
            if not is_trade_day:
                await asyncio.sleep(30)
                continue

            logger.info("monitor window entered, launching live session with {} symbols", len(selected_codes))
            try:
                await run_live(
                    settings=settings,
                    notifier=notifier,
                    runtime_status=runtime_status,
                    trade_date=now.date(),
                    wait_until_start=False,
                    preset_codes=selected_codes,
                )
            except Exception as exc:
                runtime_status.mark_error(str(exc))
                logger.exception("live scheduler session failed: {}", exc)
            await asyncio.sleep(5)
            continue

        if not preopen_done and now.time() < preopen_scan_time:
            sleep_sec = min(
                int((datetime.combine(now.date(), preopen_scan_time) - now).total_seconds()),
                30,
            )
            await asyncio.sleep(max(sleep_sec, 5))
            continue

        if now.time() < start:
            sleep_sec = min(
                int((datetime.combine(now.date(), start) - now).total_seconds()),
                30,
            )
            await asyncio.sleep(max(sleep_sec, 5))
        else:
            await asyncio.sleep(30)


async def run_app() -> None:
    """Boot scheduler service in one process."""
    settings = get_settings()
    configure_logger()

    runtime_status = RuntimeStatus()
    notifier = NotificationGateway(settings.DINGTALK_URL, keyword=settings.DINGTALK_KEYWORD)
    scheduler_task = asyncio.create_task(run_live_scheduler(runtime_status=runtime_status, notifier=notifier))

    try:
        while True:
            runtime_status.mark_heartbeat(now=now_in_trading_timezone(settings.TRADING_TIMEZONE))
            await asyncio.sleep(5)
    finally:
        scheduler_task.cancel()
        await asyncio.gather(scheduler_task, return_exceptions=True)


def main() -> None:
    """Console script entrypoint for unified service."""
    asyncio.run(run_app())


if __name__ == "__main__":
    main()
