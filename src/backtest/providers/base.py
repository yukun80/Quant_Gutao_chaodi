from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class IntradayMinuteProvider(Protocol):
    """Abstract minute-bar provider used by the backtest runner."""

    def fetch_intraday_minutes(self, code: str, trade_date: date) -> list[dict[str, Any]]:
        """Fetch minute-level bars for a single stock on a single trade date."""
