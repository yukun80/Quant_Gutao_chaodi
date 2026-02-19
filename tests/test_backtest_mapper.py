"""Tests for backtest mapper helpers."""

from datetime import datetime

import pytest

from src.backtest.mapper import minute_bar_to_snapshot, normalize_code_to_jq


def test_normalize_code_to_jq_market() -> None:
    assert normalize_code_to_jq("600000") == "600000.XSHG"
    assert normalize_code_to_jq("000001.SZ") == "000001.XSHE"


def test_minute_bar_to_snapshot_success() -> None:
    snapshot = minute_bar_to_snapshot(
        {
            "ts": datetime(2025, 1, 10, 14, 30),
            "name": "Demo",
            "close": 10.0,
            "high": 10.0,
            "limit_down_price": 10.0,
            "ask_v1": 1200,
            "volume": 3000,
        },
        code="000001",
    )
    assert snapshot.code == "000001"
    assert snapshot.name == "Demo"
    assert snapshot.is_one_word_limit_down


def test_minute_bar_to_snapshot_missing_ask_v1() -> None:
    with pytest.raises(ValueError):
        minute_bar_to_snapshot(
            {
                "ts": datetime(2025, 1, 10, 14, 30),
                "close": 10.0,
                "high": 10.0,
                "limit_down_price": 10.0,
                "volume": 3000,
            },
            code="000001",
        )
