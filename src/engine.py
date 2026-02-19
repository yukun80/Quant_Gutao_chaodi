from __future__ import annotations

"""Strategy state machine for one-word limit-down anomaly detection."""

from dataclasses import dataclass
from collections.abc import Iterable
from datetime import datetime

from .models import AlertEvent, DataQuality, PoolStock, SignalCombination, StockSnapshot


@dataclass(frozen=True)
class _WindowPoint:
    """One window's normalized features for delta comparison."""

    ts: datetime
    ask_v1: int
    volume: int
    data_quality: DataQuality


class StrategyEngine:
    """Evaluate window deltas and emit at most one alert per symbol per day."""

    def __init__(
        self,
        vol_drop_threshold: float | None = None,
        confirm_minutes: int = 1,
        *,
        ask_drop_threshold: float | None = None,
        volume_spike_threshold: float = 0.8,
        signal_combination: SignalCombination = "and",
        min_abs_delta_ask: int = 0,
        min_abs_delta_volume: int = 0,
    ) -> None:
        # Keep backward compatibility: old callers may still pass vol_drop_threshold.
        resolved_ask_threshold = ask_drop_threshold if ask_drop_threshold is not None else vol_drop_threshold
        # ask_drop_threshold drives sell1-drop detection on adjacent windows.
        self.ask_drop_threshold = resolved_ask_threshold if resolved_ask_threshold is not None else 0.5
        # volume_spike_threshold drives volume surge detection on adjacent windows.
        self.volume_spike_threshold = volume_spike_threshold
        # "and"/"or" defines whether both sub-signals are required.
        self.signal_combination = signal_combination
        # Absolute gates prevent tiny changes from passing ratio checks.
        self.min_abs_delta_ask = max(min_abs_delta_ask, 0)
        self.min_abs_delta_volume = max(min_abs_delta_volume, 0)
        # confirm_minutes means how many consecutive windows must satisfy the rule.
        self.confirm_minutes = max(confirm_minutes, 1)
        # Backward-compatible alias for historical field name.
        self.vol_drop_threshold = self.ask_drop_threshold
        # Stores previous window metrics per symbol for rolling delta detection.
        self.prev_window_map: dict[str, _WindowPoint] = {}
        # Tracks consecutive threshold-hit count per symbol.
        self.confirm_count_map: dict[str, int] = {}
        # Once alerted, symbol is muted for the rest of the day.
        self.processed_set: set[str] = set()
        # Active symbols currently eligible for evaluation.
        self.active_pool: dict[str, PoolStock] = {}
        # Symbols explicitly removed after open-board behavior is observed.
        self.removed_pool: set[str] = set()

    def register_pool(self, stocks: Iterable[PoolStock]) -> None:
        """Reset engine state and register today's candidate symbols."""
        self.active_pool = {stock.code: stock for stock in stocks}
        self.prev_window_map.clear()
        self.confirm_count_map.clear()
        self.processed_set.clear()
        self.removed_pool.clear()

    def monitorable_codes(self) -> list[str]:
        """Return symbols that are still active and not yet alerted."""
        return [code for code in self.active_pool if code not in self.processed_set]

    def evaluate(self, snapshot: StockSnapshot) -> AlertEvent | None:
        """Consume one snapshot and return an alert when trigger condition is met."""
        code = snapshot.code
        pool_stock = self.active_pool.get(code)
        # Ignore symbols that are not active or already alerted (one-shot semantics).
        if pool_stock is None or code in self.processed_set:
            return None

        # Once high price breaks limit-down, the symbol is no longer one-word.
        if snapshot.high_price > snapshot.limit_down_price:
            self.removed_pool.add(code)
            self.active_pool.pop(code, None)
            self.prev_window_map.pop(code, None)
            self.confirm_count_map.pop(code, None)
            return None

        if not snapshot.is_one_word_limit_down:
            # Non one-word bars break consecutive confirmation.
            self.confirm_count_map[code] = 0
            return None

        # Each new bar is treated as the current rolling window point.
        current_ask = max(snapshot.ask_v1, 0)
        current_volume = max(snapshot.volume, 0)
        current_point = _WindowPoint(
            ts=snapshot.ts,
            ask_v1=current_ask,
            volume=current_volume,
            data_quality=snapshot.data_quality,
        )

        previous = self.prev_window_map.get(code)
        if previous is None:
            # First valid window only initializes baseline for adjacent-window deltas.
            self.prev_window_map[code] = current_point
            self.confirm_count_map[code] = 0
            return None

        # Adjacent-window deltas: never compare against a fixed intraday baseline.
        ask_base = max(previous.ask_v1, 1)
        volume_base = max(previous.volume, 1)
        ask_delta = previous.ask_v1 - current_ask
        volume_delta = current_volume - previous.volume
        ask_change_ratio = ask_delta / ask_base
        volume_change_ratio = volume_delta / volume_base

        # Sub-signal A: sell1 drops from previous window to current window.
        signal_ask_drop = ask_change_ratio >= self.ask_drop_threshold and ask_delta >= self.min_abs_delta_ask
        # Sub-signal B: traded volume rises from previous window to current window.
        signal_volume_spike = (
            volume_change_ratio >= self.volume_spike_threshold and volume_delta >= self.min_abs_delta_volume
        )

        if self.signal_combination == "or":
            hit = signal_ask_drop or signal_volume_spike
        else:
            hit = signal_ask_drop and signal_volume_spike

        if not hit:
            # Reset confirmation streak when this window does not satisfy rule.
            self.confirm_count_map[code] = 0
            # Always slide forward so next bar compares against the latest window.
            self.prev_window_map[code] = current_point
            return None

        # Count consecutive satisfied windows.
        hit_count = self.confirm_count_map.get(code, 0) + 1
        self.confirm_count_map[code] = hit_count
        self.prev_window_map[code] = current_point
        if hit_count < self.confirm_minutes:
            return None

        # One-shot trigger: emit once and silence the symbol immediately.
        if signal_ask_drop and signal_volume_spike:
            reason = "volume_spike_and_sell1_drop"
        elif signal_ask_drop:
            reason = "sell1_drop"
        else:
            reason = "volume_spike"

        confidence = "high" if current_point.data_quality == "tick_a1v" else "low"
        # One-shot silencing happens immediately after trigger.
        self.processed_set.add(code)

        return AlertEvent(
            code=code,
            name=pool_stock.name,
            pool_type=pool_stock.pool_type,
            initial_ask_v1=previous.ask_v1,
            current_ask_v1=current_ask,
            drop_ratio=ask_change_ratio,
            initial_volume=previous.volume,
            current_volume=current_volume,
            volume_change_ratio=volume_change_ratio,
            signal_ask_drop=signal_ask_drop,
            signal_volume_spike=signal_volume_spike,
            prev_window_ts=previous.ts,
            curr_window_ts=current_point.ts,
            data_quality=current_point.data_quality,
            confidence=confidence,
            trigger_ts=current_point.ts,
            reason=reason,
        )

    def summary(self) -> dict[str, int]:
        """Return compact runtime counters for logging and diagnostics."""
        return {
            "active": len(self.active_pool),
            "processed": len(self.processed_set),
            "removed": len(self.removed_pool),
            "window_state": len(self.prev_window_map),
            "confirming": sum(1 for value in self.confirm_count_map.values() if value > 0),
        }
