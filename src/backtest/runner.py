from __future__ import annotations

"""Single-day replay runner that reuses the live strategy engine."""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from ..engine import StrategyEngine
from ..models import ConfidenceLevel, DataQuality
from ..models import PoolStock
from .mapper import minute_bar_to_snapshot
from .providers.base import IntradayMinuteProvider


@dataclass(frozen=True)
class BacktestRequest:
    """Input payload for one stock/day replay task."""

    code: str
    trade_date: date
    ask_drop_threshold: float
    volume_spike_threshold: float = 0.8
    confirm_minutes: int = 1
    signal_combination: str = "and"
    min_abs_delta_ask: int = 0
    min_abs_delta_volume: int = 0
    window_start: time = field(default_factory=lambda: time(13, 0))
    window_end: time = field(default_factory=lambda: time(15, 0))

    @property
    def threshold(self) -> float:
        """Backward-compatible alias for historical field naming."""
        return self.ask_drop_threshold


@dataclass(frozen=True)
class BacktestResult:
    """Execution result payload returned by the replay runner."""

    triggered: bool
    trigger_time: datetime | None
    reason: str
    prev_window_ts: datetime | None
    curr_window_ts: datetime | None
    prev_ask_v1: int | None
    curr_ask_v1: int | None
    ask_change_ratio: float | None
    prev_volume: int | None
    curr_volume: int | None
    volume_change_ratio: float | None
    signal_ask_drop: bool
    signal_volume_spike: bool
    data_quality: DataQuality
    confidence: ConfidenceLevel
    samples: int
    samples_in_window: int


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


def _default_quality() -> tuple[DataQuality, ConfidenceLevel]:
    """Return conservative defaults for non-triggered/empty states."""
    return ("minute_proxy", "low")


def _quality_to_confidence(data_quality: DataQuality) -> ConfidenceLevel:
    """Map data quality level to confidence label."""
    return "high" if data_quality == "tick_a1v" else "low"


def run_single_day_backtest(
    request: BacktestRequest,
    provider: IntradayMinuteProvider,
    engine: StrategyEngine | None = None,
) -> BacktestResult:
    """Replay intraday bars and return whether the strategy would trigger."""
    # Provider can be tick-based or minute-proxy; runner remains agnostic.
    raw_bars = provider.fetch_intraday_minutes(request.code, request.trade_date)
    if not raw_bars:
        data_quality, confidence = _default_quality()
        return BacktestResult(
            triggered=False,
            trigger_time=None,
            reason="no_data",
            prev_window_ts=None,
            curr_window_ts=None,
            prev_ask_v1=None,
            curr_ask_v1=None,
            ask_change_ratio=None,
            prev_volume=None,
            curr_volume=None,
            volume_change_ratio=None,
            signal_ask_drop=False,
            signal_volume_spike=False,
            data_quality=data_quality,
            confidence=confidence,
            samples=0,
            samples_in_window=0,
        )

    # Stable chronological replay guarantees deterministic state transitions.
    ordered_bars = sorted(raw_bars, key=_sort_key)
    windowed_bars: list[dict[str, Any]] = []
    for bar in ordered_bars:
        try:
            bar_ts = _coerce_ts(bar.get("ts"))
        except ValueError:
            data_quality, confidence = _default_quality()
            return BacktestResult(
                triggered=False,
                trigger_time=None,
                reason="insufficient_data",
                prev_window_ts=None,
                curr_window_ts=None,
                prev_ask_v1=None,
                curr_ask_v1=None,
                ask_change_ratio=None,
                prev_volume=None,
                curr_volume=None,
                volume_change_ratio=None,
                signal_ask_drop=False,
                signal_volume_spike=False,
                data_quality=data_quality,
                confidence=confidence,
                samples=len(raw_bars),
                samples_in_window=0,
            )
        # Backtest only evaluates bars inside configured monitoring window.
        if request.window_start <= bar_ts.time() <= request.window_end:
            windowed_bars.append(bar)

    if not windowed_bars:
        data_quality, confidence = _default_quality()
        return BacktestResult(
            triggered=False,
            trigger_time=None,
            reason="no_data_in_window",
            prev_window_ts=None,
            curr_window_ts=None,
            prev_ask_v1=None,
            curr_ask_v1=None,
            ask_change_ratio=None,
            prev_volume=None,
            curr_volume=None,
            volume_change_ratio=None,
            signal_ask_drop=False,
            signal_volume_spike=False,
            data_quality=data_quality,
            confidence=confidence,
            samples=len(raw_bars),
            samples_in_window=0,
        )

    # StrategyEngine is shared with live path to avoid rule drift.
    strategy = engine or StrategyEngine(
        ask_drop_threshold=request.ask_drop_threshold,
        volume_spike_threshold=request.volume_spike_threshold,
        confirm_minutes=request.confirm_minutes,
        signal_combination=request.signal_combination,  # type: ignore[arg-type]
        min_abs_delta_ask=request.min_abs_delta_ask,
        min_abs_delta_volume=request.min_abs_delta_volume,
    )
    strategy.register_pool(
        [
            PoolStock(
                code=request.code,
                name=request.code,
                is_st=False,
                pool_type="all",
            )
        ]
    )

    has_one_word_snapshot = False
    for bar in windowed_bars:
        try:
            # Normalize raw bar into strict strategy contract.
            snapshot = minute_bar_to_snapshot(bar=bar, code=request.code, name=str(bar.get("name") or request.code))
        except ValueError:
            last_point = strategy.prev_window_map.get(request.code)
            data_quality = last_point.data_quality if last_point is not None else "minute_proxy"
            return BacktestResult(
                triggered=False,
                trigger_time=None,
                reason="insufficient_data",
                prev_window_ts=last_point.ts if last_point is not None else None,
                curr_window_ts=None,
                prev_ask_v1=last_point.ask_v1 if last_point is not None else None,
                curr_ask_v1=None,
                ask_change_ratio=None,
                prev_volume=last_point.volume if last_point is not None else None,
                curr_volume=None,
                volume_change_ratio=None,
                signal_ask_drop=False,
                signal_volume_spike=False,
                data_quality=data_quality,
                confidence=_quality_to_confidence(data_quality),
                samples=len(raw_bars),
                samples_in_window=len(windowed_bars),
            )

        if snapshot.is_one_word_limit_down:
            has_one_word_snapshot = True

        # Evaluate one bar at a time; state machine decides whether to alert.
        event = strategy.evaluate(snapshot)
        if event is None:
            continue

        return BacktestResult(
            triggered=True,
            trigger_time=snapshot.ts,
            reason=event.reason,
            prev_window_ts=event.prev_window_ts,
            curr_window_ts=event.curr_window_ts,
            prev_ask_v1=event.initial_ask_v1,
            curr_ask_v1=event.current_ask_v1,
            ask_change_ratio=event.drop_ratio,
            prev_volume=event.initial_volume,
            curr_volume=event.current_volume,
            volume_change_ratio=event.volume_change_ratio,
            signal_ask_drop=event.signal_ask_drop,
            signal_volume_spike=event.signal_volume_spike,
            data_quality=event.data_quality,
            confidence=event.confidence,
            samples=len(raw_bars),
            samples_in_window=len(windowed_bars),
        )

    last_point = strategy.prev_window_map.get(request.code)
    data_quality = last_point.data_quality if last_point is not None else "minute_proxy"
    return BacktestResult(
        triggered=False,
        trigger_time=None,
        reason="no_one_word_limit_down" if not has_one_word_snapshot else "threshold_not_met",
        prev_window_ts=last_point.ts if last_point is not None else None,
        curr_window_ts=None,
        prev_ask_v1=last_point.ask_v1 if last_point is not None else None,
        curr_ask_v1=None,
        ask_change_ratio=None,
        prev_volume=last_point.volume if last_point is not None else None,
        curr_volume=None,
        volume_change_ratio=None,
        signal_ask_drop=False,
        signal_volume_spike=False,
        data_quality=data_quality,
        confidence=_quality_to_confidence(data_quality),
        samples=len(raw_bars),
        samples_in_window=len(windowed_bars),
    )
