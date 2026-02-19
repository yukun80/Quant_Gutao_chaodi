from __future__ import annotations

"""Field mapping helpers between provider bars and strategy snapshots."""

from datetime import datetime
from typing import Any, Mapping

from ..models import StockSnapshot


def normalize_code_to_jq(code: str) -> str:
    """Convert local stock code into JoinQuant market-suffixed format."""
    value = code.strip()
    if "." in value:
        value = value.split(".")[0]

    if value.startswith(("5", "6", "9")):
        return f"{value}.XSHG"
    return f"{value}.XSHE"


def _parse_ts(value: Any) -> datetime:
    """Parse timestamp values from provider bars into datetime."""
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError(f"invalid ts value: {value!r}")


def minute_bar_to_snapshot(bar: Mapping[str, Any], code: str, name: str | None = None) -> StockSnapshot:
    """Build StockSnapshot from a normalized minute bar dictionary."""
    # Backtest runner uses explicit errors to classify data quality failures.
    if bar.get("limit_down_price") in (None, "", "-"):
        raise ValueError("minute bar missing limit_down_price")
    if bar.get("ask_v1") in (None, "", "-"):
        raise ValueError("minute bar missing ask_v1")
    if bar.get("volume") in (None, "", "-"):
        raise ValueError("minute bar missing volume")
    if bar.get("ts") in (None, ""):
        raise ValueError("minute bar missing ts")

    return StockSnapshot(
        code=code,
        name=name or str(bar.get("name") or code),
        current_price=bar.get("close", 0),
        high_price=bar.get("high", 0),
        limit_down_price=bar["limit_down_price"],
        ask_v1=bar["ask_v1"],
        volume=bar["volume"],
        data_quality=str(bar.get("data_quality") or "minute_proxy"),
        ts=_parse_ts(bar["ts"]),
    )
