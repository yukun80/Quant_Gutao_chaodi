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


def test_run_single_day_backtest_triggered_after_confirm() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 14, 0),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 1000,
            "volume": 100,
            "data_quality": "minute_proxy",
        },
        {
            "ts": datetime(2025, 1, 10, 14, 1),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 600,
            "volume": 200,
            "data_quality": "minute_proxy",
        },
        {
            "ts": datetime(2025, 1, 10, 14, 2),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 300,
            "volume": 500,
            "data_quality": "minute_proxy",
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(
            code="600000",
            trade_date=date(2025, 1, 10),
            ask_drop_threshold=0.3,
            volume_spike_threshold=0.5,
            confirm_minutes=2,
            signal_combination="and",
        ),
        provider=FakeProvider(bars),
    )
    assert result.triggered is True
    assert result.reason == "volume_spike_and_sell1_drop"
    assert result.prev_window_ts == datetime(2025, 1, 10, 14, 1)
    assert result.curr_window_ts == datetime(2025, 1, 10, 14, 2)
    assert result.prev_ask_v1 == 600
    assert result.curr_ask_v1 == 300
    assert result.prev_volume == 200
    assert result.curr_volume == 500
    assert result.signal_ask_drop is True
    assert result.signal_volume_spike is True
    assert result.data_quality == "minute_proxy"
    assert result.confidence == "low"
    assert result.trigger_time == datetime(2025, 1, 10, 14, 2)
    assert result.samples == 3
    assert result.samples_in_window == 3


def test_run_single_day_backtest_no_one_word_limit() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 14, 0),
            "close": 10.1,
            "high": 10.2,
            "limit_down_price": 10.0,
            "ask_v1": 1000,
            "volume": 1000,
        }
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(code="600000", trade_date=date(2025, 1, 10), ask_drop_threshold=0.3),
        provider=FakeProvider(bars),
    )
    assert result.triggered is False
    assert result.reason == "no_one_word_limit_down"
    assert result.samples_in_window == 1


def test_run_single_day_backtest_threshold_not_met_when_not_consecutive() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 14, 0),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 1000,
            "volume": 100,
        },
        {
            "ts": datetime(2025, 1, 10, 14, 1),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 600,
            "volume": 200,
        },
        {
            "ts": datetime(2025, 1, 10, 14, 2),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 500,
            "volume": 220,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(
            code="600000",
            trade_date=date(2025, 1, 10),
            ask_drop_threshold=0.3,
            volume_spike_threshold=0.5,
            confirm_minutes=2,
            signal_combination="and",
        ),
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
            "ask_v1": 1000,
            "volume": 100,
        },
        {
            "ts": datetime(2025, 1, 10, 14, 1),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 900,
            "volume": None,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(code="600000", trade_date=date(2025, 1, 10), ask_drop_threshold=0.3),
        provider=FakeProvider(bars),
    )
    assert result.triggered is False
    assert result.reason == "insufficient_data"
    assert result.samples_in_window == 2


def test_run_single_day_backtest_no_data_in_window() -> None:
    bars = [
        {
            "ts": datetime(2025, 1, 10, 9, 31),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 1000,
            "volume": 100,
        },
        {
            "ts": datetime(2025, 1, 10, 9, 32),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 600,
            "volume": 120,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(code="600000", trade_date=date(2025, 1, 10), ask_drop_threshold=0.3),
        provider=FakeProvider(bars),
    )
    assert result.triggered is False
    assert result.reason == "no_data_in_window"
    assert result.samples == 2
    assert result.samples_in_window == 0


def test_run_single_day_backtest_ignores_early_drop_without_volume_spike() -> None:
    bars = [
        {
            "ts": datetime(2025, 11, 5, 13, 1),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 498300,
            "volume": 498300,
        },
        {
            "ts": datetime(2025, 11, 5, 13, 2),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 10300,
            "volume": 10300,
        },
        {
            "ts": datetime(2025, 11, 5, 13, 3),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 12000,
            "volume": 12000,
        },
        {
            "ts": datetime(2025, 11, 5, 14, 54),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 50000,
            "volume": 10000,
        },
        {
            "ts": datetime(2025, 11, 5, 14, 55),
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 10000,
            "volume": 26000,
        },
    ]
    result = run_single_day_backtest(
        request=BacktestRequest(
            code="002122",
            trade_date=date(2025, 11, 5),
            ask_drop_threshold=0.3,
            volume_spike_threshold=0.8,
            confirm_minutes=1,
            signal_combination="and",
        ),
        provider=FakeProvider(bars),
    )
    assert result.triggered is True
    assert result.trigger_time == datetime(2025, 11, 5, 14, 55)
    assert result.prev_window_ts == datetime(2025, 11, 5, 14, 54)
