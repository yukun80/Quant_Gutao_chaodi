from __future__ import annotations

from datetime import date

import pandas as pd

from src import trading_calendar


def test_is_trading_day_true(monkeypatch) -> None:
    trading_calendar._load_trade_dates.cache_clear()

    def fake_fetch() -> pd.DataFrame:
        return pd.DataFrame({"trade_date": ["2026-02-20", "2026-02-23"]})

    monkeypatch.setattr(trading_calendar, "_fetch_trade_dates_frame", fake_fetch)
    assert trading_calendar.is_trading_day(date(2026, 2, 23)) is True


def test_is_trading_day_false(monkeypatch) -> None:
    trading_calendar._load_trade_dates.cache_clear()

    def fake_fetch() -> pd.DataFrame:
        return pd.DataFrame({"trade_date": ["2026-02-20"]})

    monkeypatch.setattr(trading_calendar, "_fetch_trade_dates_frame", fake_fetch)
    assert trading_calendar.is_trading_day(date(2026, 2, 22)) is False
