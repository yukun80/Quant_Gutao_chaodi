from __future__ import annotations

from datetime import date, datetime

from src.app import format_preopen_summary_messages, notify_preopen_summary, scan_preopen_one_word_limit_down
from src.config import Settings
from src.main import run_live
from src.models import PoolStock, StockSnapshot
from src.runtime_status import RuntimeStatus


class DummyNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def send_text(self, title: str, body: str, code: str = "-") -> bool:
        self.messages.append((title, body, code))
        return True


def _snapshot(code: str, name: str, ask_v1: int, *, one_word: bool = True) -> StockSnapshot:
    limit_down = 10.0
    high = limit_down if one_word else limit_down + 0.1
    current = limit_down if one_word else limit_down + 0.1
    return StockSnapshot(
        code=code,
        name=name,
        current_price=current,
        high_price=high,
        limit_down_price=limit_down,
        ask_v1=ask_v1,
        volume=100,
        ts=datetime(2026, 2, 23, 9, 26, 0),
    )


def _seed_settings(**overrides) -> Settings:
    values = {
        "DINGTALK_URL": "https://oapi.dingtalk.com/robot/send?access_token=dummy",
        "MONITOR_START_TIME": "13:00",
        "MONITOR_END_TIME": "13:00",
        "POLL_INTERVAL_SEC": 0.0,
        "PREOPEN_MESSAGE_MAX_ROWS_PER_CHUNK": 2,
    }
    values.update(overrides)
    return Settings(**values)


def test_format_preopen_summary_messages_zero() -> None:
    messages = format_preopen_summary_messages(
        trade_date=date(2026, 2, 23),
        run_at=datetime(2026, 2, 23, 9, 26, 0),
        snapshots=[],
        max_rows_per_chunk=80,
    )
    assert len(messages) == 1
    assert "09:26一字跌停统计: 0只" in messages[0]
    assert "结果: 0只" in messages[0]


def test_format_preopen_summary_messages_chunked() -> None:
    snapshots = [
        _snapshot("000001", "平安银行", 100),
        _snapshot("000002", "万 科A", 200),
        _snapshot("000003", "国农科技", 300),
    ]
    messages = format_preopen_summary_messages(
        trade_date=date(2026, 2, 23),
        run_at=datetime(2026, 2, 23, 9, 26, 0),
        snapshots=snapshots,
        max_rows_per_chunk=2,
    )
    assert len(messages) == 2
    assert "分片: 1/2" in messages[0]
    assert "1) 000001 平安银行 卖1单数: 100" in messages[0]
    assert "3) 000003 国农科技 卖1单数: 300" in messages[1]


def test_notify_preopen_summary_marks_alert_count() -> None:
    notifier = DummyNotifier()
    status = RuntimeStatus()
    settings = _seed_settings(PREOPEN_MESSAGE_MAX_ROWS_PER_CHUNK=1)
    snapshots = [_snapshot("000001", "平安银行", 100), _snapshot("000002", "万 科A", 200)]
    notify_preopen_summary(
        settings=settings,
        notifier=notifier,  # type: ignore[arg-type]
        runtime_status=status,
        trade_date=date(2026, 2, 23),
        run_at=datetime(2026, 2, 23, 9, 26, 0),
        snapshots=snapshots,
    )
    assert len(notifier.messages) == 2
    assert status.alerts_sent == 2


def test_scan_preopen_one_word_limit_down_filters(monkeypatch) -> None:
    settings = _seed_settings()
    pool = [
        PoolStock(code="000001", name="平安银行", is_st=False, pool_type="all"),
        PoolStock(code="000002", name="万 科A", is_st=False, pool_type="all"),
    ]
    snapshots = [_snapshot("000001", "平安银行", 100, one_word=True), _snapshot("000002", "万 科A", 200, one_word=False)]

    monkeypatch.setattr("src.app.PoolManager.build_daily_pool", lambda self, trade_date: pool)

    async def fake_fetch(self, codes):
        _ = codes
        return snapshots

    monkeypatch.setattr("src.app.EastMoneyFetcher.fetch_snapshots", fake_fetch)
    result = __import__("asyncio").run(scan_preopen_one_word_limit_down(settings=settings, trade_date=date(2026, 2, 23)))
    assert [item.code for item in result] == ["000001"]


def test_run_live_uses_preset_codes(monkeypatch) -> None:
    settings = _seed_settings(
        TRADING_TIMEZONE="Asia/Shanghai",
        POOL_CACHE_PATH="data/pool_cache/test_preset_codes.csv",
        ASK_DROP_THRESHOLD=0.5,
    )
    pool = [
        PoolStock(code="000001", name="平安银行", is_st=False, pool_type="all"),
        PoolStock(code="000002", name="万 科A", is_st=False, pool_type="all"),
    ]
    snapshots = [_snapshot("000001", "平安银行", 100, one_word=True)]

    monkeypatch.setattr("src.main.configure_logger", lambda: None)
    now_values = iter(
        [
            datetime(2026, 2, 23, 13, 0, 0),
            datetime(2026, 2, 23, 13, 0, 0),
            datetime(2026, 2, 23, 13, 1, 0),
        ]
    )

    def fake_now(timezone_name: str) -> datetime:
        _ = timezone_name
        return next(now_values)

    monkeypatch.setattr("src.main.now_in_trading_timezone", fake_now)
    monkeypatch.setattr("src.main.PoolManager.build_daily_pool", lambda self, trade_date: pool)

    async def fake_fetch(self, codes):
        assert codes == ["000001"]
        return snapshots

    monkeypatch.setattr("src.main.EastMoneyFetcher.fetch_snapshots", fake_fetch)

    class CaptureNotifier:
        def __init__(self) -> None:
            self.count = 0

        def send_alert(self, event) -> bool:
            _ = event
            self.count += 1
            return True

    notifier = CaptureNotifier()
    result = __import__("asyncio").run(
        run_live(
            settings=settings,
            notifier=notifier,  # type: ignore[arg-type]
            runtime_status=RuntimeStatus(),
            trade_date=date(2026, 2, 23),
            wait_until_start=False,
            preset_codes={"000001"},
        )
    )
    assert result["rounds"] == 1
