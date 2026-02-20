from __future__ import annotations

"""Single-day replay runner for buy-flow breakout backtest strategy."""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from ..models import ConfidenceLevel, DataQuality
from .providers.base import IntradayMinuteProvider


@dataclass(frozen=True)
class BacktestRequest:
    """Input payload for one stock/day replay task."""

    code: str
    trade_date: date
    window_start: time = field(default_factory=lambda: time(13, 0))
    window_end: time = field(default_factory=lambda: time(15, 0))


@dataclass(frozen=True)
class BacktestResult:
    """Execution result payload returned by the replay runner."""

    triggered: bool
    trigger_time: datetime | None
    reason: str
    current_buy_volume: int | None
    cumulative_buy_volume_before: int | None
    data_quality: DataQuality
    confidence: ConfidenceLevel
    samples: int
    samples_in_window: int
    samples_one_word_in_window: int


def _sort_key(bar: dict[str, Any]) -> str:
    """Sort helper to preserve chronological replay order."""
    return str(bar.get("ts", ""))


def _coerce_ts(value: Any) -> datetime:
    """Parse provider ts field into datetime for window filtering."""
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError(f"invalid ts value: {value!r}")


def _coerce_float(value: Any, field_name: str) -> float:
    """Coerce numeric-like provider values to float with strict validation."""
    if value in (None, "", "-"):
        raise ValueError(f"missing field '{field_name}'")
    return float(value)


def _default_quality() -> tuple[DataQuality, ConfidenceLevel]:
    """Return conservative defaults for backtest output."""
    return ("minute_proxy", "low")


def _is_one_word_limit_down(close: float, high: float, limit_down: float) -> bool:
    """Identify one-word limit-down minute bars with tolerance for float noise."""
    eps = 1e-6
    return abs(close - limit_down) <= eps and abs(high - limit_down) <= eps


def run_single_day_backtest(
    request: BacktestRequest,
    provider: IntradayMinuteProvider,
) -> BacktestResult:
    """Replay intraday bars and trigger when one-minute buy flow exceeds prior day accumulation."""
    raw_bars = provider.fetch_intraday_minutes(request.code, request.trade_date)
    data_quality, confidence = _default_quality()

    if not raw_bars:
        return BacktestResult(
            triggered=False,
            trigger_time=None,
            reason="no_data",
            current_buy_volume=None,
            cumulative_buy_volume_before=None,
            data_quality=data_quality,
            confidence=confidence,
            samples=0,
            samples_in_window=0,
            samples_one_word_in_window=0,
        )

    ordered_bars = sorted(raw_bars, key=_sort_key)
    samples_in_window = 0
    samples_one_word_in_window = 0
    cumulative_buy_volume_day = 0

    for bar in ordered_bars:
        try:
            bar_ts = _coerce_ts(bar.get("ts"))
        except ValueError:
            return BacktestResult(
                triggered=False,
                trigger_time=None,
                reason="insufficient_data",
                current_buy_volume=None,
                cumulative_buy_volume_before=None,
                data_quality=data_quality,
                confidence=confidence,
                samples=len(raw_bars),
                samples_in_window=samples_in_window,
                samples_one_word_in_window=samples_one_word_in_window,
            )

        try:
            close = _coerce_float(bar.get("close"), "close")
            high = _coerce_float(bar.get("high"), "high")
            limit_down_price = _coerce_float(bar.get("limit_down_price"), "limit_down_price")
            volume = _coerce_float(bar.get("volume"), "volume")
        except ValueError:
            return BacktestResult(
                triggered=False,
                trigger_time=None,
                reason="insufficient_data",
                current_buy_volume=None,
                cumulative_buy_volume_before=None,
                data_quality=data_quality,
                confidence=confidence,
                samples=len(raw_bars),
                samples_in_window=samples_in_window,
                samples_one_word_in_window=samples_one_word_in_window,
            )

        is_one_word = _is_one_word_limit_down(close, high, limit_down_price)
        current_buy_volume = int(max(volume, 0.0)) if is_one_word else 0
        cumulative_before = cumulative_buy_volume_day

        in_window = request.window_start <= bar_ts.time() <= request.window_end
        if in_window:
            samples_in_window += 1
            if is_one_word:
                samples_one_word_in_window += 1

            if is_one_word and cumulative_before > 0 and current_buy_volume > cumulative_before:
                return BacktestResult(
                    triggered=True,
                    trigger_time=bar_ts,
                    reason="buy_flow_breakout",
                    current_buy_volume=current_buy_volume,
                    cumulative_buy_volume_before=cumulative_before,
                    data_quality=data_quality,
                    confidence=confidence,
                    samples=len(raw_bars),
                    samples_in_window=samples_in_window,
                    samples_one_word_in_window=samples_one_word_in_window,
                )

        # Full-day accumulation: update after evaluation so trigger compares against history only.
        cumulative_buy_volume_day += current_buy_volume

    if samples_in_window == 0:
        reason = "no_data_in_window"
    elif samples_one_word_in_window == 0:
        reason = "no_one_word_limit_down"
    else:
        reason = "threshold_not_met"

    return BacktestResult(
        triggered=False,
        trigger_time=None,
        reason=reason,
        current_buy_volume=None,
        cumulative_buy_volume_before=None,
        data_quality=data_quality,
        confidence=confidence,
        samples=len(raw_bars),
        samples_in_window=samples_in_window,
        samples_one_word_in_window=samples_one_word_in_window,
    )
