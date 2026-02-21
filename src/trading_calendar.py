from __future__ import annotations

"""Trading calendar helpers for A-share market open-day checks."""

from datetime import date
from functools import lru_cache

import pandas as pd


def _fetch_trade_dates_frame() -> pd.DataFrame:
    """Fetch historical trade dates from AkShare."""
    import akshare as ak

    return ak.tool_trade_date_hist_sina()


@lru_cache(maxsize=1)
def _load_trade_dates() -> set[date]:
    """Load trade-date set once and reuse for daily scheduler checks."""
    frame = _fetch_trade_dates_frame()
    if frame.empty:
        return set()

    column = "trade_date" if "trade_date" in frame.columns else frame.columns[0]
    values = pd.to_datetime(frame[column], errors="coerce").dropna()
    return set(values.dt.date.tolist())


def is_trading_day(trade_date: date) -> bool:
    """Return whether a given date is an A-share trading day."""
    return trade_date in _load_trade_dates()

