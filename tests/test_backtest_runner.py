from __future__ import annotations

"""Runner replay behavior tests."""

from datetime import date, datetime
from typing import Any

from src.backtest.runner import BacktestRequest, run_single_day_backtest


class FakeProvider:
    def __init__(self, bars: list[dict[str, Any]]) -> None:
        self.bars = bars

    def fetch_intraday_minutes(self, code: str, trade_date: date) -> list[dict[str, Any]]:
        return self.bars


def test_run_single_day_backtest_triggered_by_buy_flow_breakout() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 9, 31),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 100,
        },
        {
            "ts": datetime(2025, 1, 10, 9, 32),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 200,
        },
        {
            "ts": datetime(2025, 1, 10, 13, 1),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 50,
        },
        {
            "ts": datetime(2025, 1, 10, 13, 2),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 400,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(
            code="600000",
            trade_date=date(2025, 1, 10),
        ),
        provider=FakeProvider(bars),
    )
    assert result.triggered is True
    assert result.reason == "buy_flow_breakout"
    assert result.trigger_time == datetime(2025, 1, 10, 13, 2)
    assert result.current_buy_volume == 400
    assert result.cumulative_buy_volume_before == 350
    assert result.data_quality == "minute_proxy"
    assert result.confidence == "low"
    assert result.samples == 4
    assert result.samples_in_window == 2
    assert result.samples_one_word_in_window == 2


def test_run_single_day_backtest_not_triggered_at_1302_for_002122_like_pattern() -> None:
    bars = [
        {
            "ts": datetime(2025, 11, 5, 9, 31),
            "close": 3.07,
            "high": 3.07,
            "limit_down_price": 3.07,
            "volume": 1_000_000,
        },
        {
            "ts": datetime(2025, 11, 5, 13, 1),
            "close": 3.07,
            "high": 3.07,
            "limit_down_price": 3.07,
            "volume": 498_300,
        },
        {
            "ts": datetime(2025, 11, 5, 13, 2),
            "close": 3.07,
            "high": 3.07,
            "limit_down_price": 3.07,
            "volume": 500,
        },
        {
            "ts": datetime(2025, 11, 5, 15, 0),
            "close": 3.07,
            "high": 3.07,
            "limit_down_price": 3.07,
            "volume": 2_000_000,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(code="002122", trade_date=date(2025, 11, 5)),
        provider=FakeProvider(bars),
    )
    assert result.triggered is True
    # 13:02 should not trigger because volume is much smaller than accumulated history.
    assert result.trigger_time == datetime(2025, 11, 5, 15, 0)


def test_run_single_day_backtest_no_one_word_limit() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 14, 0),
            "close": 10.1,
            "high": 10.2,
            "limit_down_price": 10.0,
            "volume": 1000,
        }
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(code="600000", trade_date=date(2025, 1, 10)),
        provider=FakeProvider(bars),
    )
    assert result.triggered is False
    assert result.reason == "no_one_word_limit_down"
    assert result.samples_in_window == 1
    assert result.samples_one_word_in_window == 0


def test_run_single_day_backtest_threshold_not_met() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 9, 31),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 500,
        },
        {
            "ts": datetime(2025, 1, 10, 13, 1),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 100,
        },
        {
            "ts": datetime(2025, 1, 10, 13, 2),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 200,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(code="600000", trade_date=date(2025, 1, 10)),
        provider=FakeProvider(bars),
    )
    assert result.triggered is False
    assert result.reason == "threshold_not_met"


def test_run_single_day_backtest_insufficient_data() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 14, 0),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 100,
        },
        {
            "ts": datetime(2025, 1, 10, 14, 1),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": None,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(code="600000", trade_date=date(2025, 1, 10)),
        provider=FakeProvider(bars),
    )
    assert result.triggered is False
    assert result.reason == "insufficient_data"


def test_run_single_day_backtest_no_data_in_window() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 9, 31),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 100,
        },
        {
            "ts": datetime(2025, 1, 10, 9, 32),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "volume": 120,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(code="600000", trade_date=date(2025, 1, 10)),
        provider=FakeProvider(bars),
    )
    assert result.triggered is False
    assert result.reason == "no_data_in_window"
    assert result.samples == 2
    assert result.samples_in_window == 0
