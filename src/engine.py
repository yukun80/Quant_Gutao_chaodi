from __future__ import annotations

"""Strategy state machine for one-word limit-down anomaly detection."""

from dataclasses import dataclass
from collections.abc import Iterable
from datetime import datetime

from .models import AlertEvent, DataQuality, PoolStock, SignalCombination, StockSnapshot

RULE_BUY_FLOW = "buy_flow_breakout"
RULE_SELL1_DROP = "sell1_drop"
RULE_COMBINED = "buy_flow_breakout_and_sell1_drop"
ALL_RULES = {RULE_BUY_FLOW, RULE_SELL1_DROP}


@dataclass(frozen=True)
class _MinuteBucket:
    """Per-symbol one-minute aggregation snapshot based on last quote in that minute."""

    minute_key: datetime
    end_ts: datetime
    end_volume_total: int
    last_ask_v1: int
    data_quality: DataQuality


class StrategyEngine:
    """Evaluate one-word minute signals and emit per-rule alerts with OR semantics."""

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
        self.ask_drop_threshold = resolved_ask_threshold if resolved_ask_threshold is not None else 0.5

        # Deprecated compatibility fields kept for existing callers/config.
        self.volume_spike_threshold = volume_spike_threshold
        self.signal_combination = signal_combination
        self.min_abs_delta_volume = max(min_abs_delta_volume, 0)
        self.vol_drop_threshold = self.ask_drop_threshold

        # Sell1-drop confirmation counter (applies to RULE_SELL1_DROP only).
        self.confirm_minutes = max(confirm_minutes, 1)
        self.min_abs_delta_ask = max(min_abs_delta_ask, 0)

        self.active_pool: dict[str, PoolStock] = {}
        self.removed_pool: set[str] = set()

        # Fully silenced symbols: both rules have already fired.
        self.processed_set: set[str] = set()

        # Per-rule fired marks to support "each rule once".
        self.fired_rules_map: dict[str, set[str]] = {}

        # One-word minute state.
        self.prev_bucket_map: dict[str, _MinuteBucket] = {}
        self.current_bucket_map: dict[str, _MinuteBucket] = {}

        # Sell1-drop consecutive confirmation state.
        self.sell1_confirm_count_map: dict[str, int] = {}

        # Backward-compatible aliases for historical field names.
        self.prev_window_map = self.prev_bucket_map
        self.confirm_count_map = self.sell1_confirm_count_map

    def register_pool(self, stocks: Iterable[PoolStock]) -> None:
        """Reset engine state and register today's candidate symbols."""
        self.active_pool = {stock.code: stock for stock in stocks}
        self.removed_pool.clear()
        self.processed_set.clear()
        self.fired_rules_map.clear()
        self.prev_bucket_map.clear()
        self.current_bucket_map.clear()
        self.sell1_confirm_count_map.clear()

    def monitorable_codes(self) -> list[str]:
        """Return symbols that are still active and not fully silenced."""
        return [code for code in self.active_pool if code not in self.processed_set]

    @staticmethod
    def _minute_key(ts: datetime) -> datetime:
        """Round timestamp down to minute precision for minute-bucket grouping."""
        return ts.replace(second=0, microsecond=0)

    def _build_bucket(self, snapshot: StockSnapshot) -> _MinuteBucket:
        """Convert one snapshot to an in-progress minute bucket."""
        return _MinuteBucket(
            minute_key=self._minute_key(snapshot.ts),
            end_ts=snapshot.ts,
            end_volume_total=max(snapshot.volume, 0),
            last_ask_v1=max(snapshot.ask_v1, 0),
            data_quality=snapshot.data_quality,
        )

    def _clear_symbol_runtime_state(self, code: str) -> None:
        """Drop minute-comparison runtime state for one symbol."""
        self.prev_bucket_map.pop(code, None)
        self.current_bucket_map.pop(code, None)
        self.sell1_confirm_count_map.pop(code, None)

    def _emit_alert_if_hit(
        self,
        code: str,
        pool_stock: PoolStock,
        previous: _MinuteBucket,
        current: _MinuteBucket,
    ) -> AlertEvent | None:
        """Evaluate both rules on a completed one-word minute and build alert if any hit."""
        fired_rules = self.fired_rules_map.setdefault(code, set())

        cumulative_before = max(previous.end_volume_total, 0)
        current_buy_volume = max(current.end_volume_total - previous.end_volume_total, 0)
        signal_buy_flow = (
            RULE_BUY_FLOW not in fired_rules
            and cumulative_before > 0
            and current_buy_volume > cumulative_before
        )

        ask_base = max(previous.last_ask_v1, 1)
        ask_delta = previous.last_ask_v1 - current.last_ask_v1
        ask_change_ratio = ask_delta / ask_base
        ask_drop_hit = ask_change_ratio >= self.ask_drop_threshold and ask_delta >= self.min_abs_delta_ask

        if ask_drop_hit:
            hit_count = self.sell1_confirm_count_map.get(code, 0) + 1
        else:
            hit_count = 0
        self.sell1_confirm_count_map[code] = hit_count

        signal_sell1_drop = (
            RULE_SELL1_DROP not in fired_rules
            and ask_drop_hit
            and hit_count >= self.confirm_minutes
        )

        if not signal_buy_flow and not signal_sell1_drop:
            return None

        if signal_buy_flow and signal_sell1_drop:
            reason = RULE_COMBINED
        elif signal_buy_flow:
            reason = RULE_BUY_FLOW
        else:
            reason = RULE_SELL1_DROP

        if signal_buy_flow:
            fired_rules.add(RULE_BUY_FLOW)
        if signal_sell1_drop:
            fired_rules.add(RULE_SELL1_DROP)

        if fired_rules >= ALL_RULES:
            self.processed_set.add(code)

        confidence = "high" if current.data_quality == "tick_a1v" else "low"
        volume_change_ratio = (current.end_volume_total - previous.end_volume_total) / max(previous.end_volume_total, 1)

        return AlertEvent(
            code=code,
            name=pool_stock.name,
            pool_type=pool_stock.pool_type,
            initial_ask_v1=previous.last_ask_v1,
            current_ask_v1=current.last_ask_v1,
            drop_ratio=ask_change_ratio,
            initial_volume=previous.end_volume_total,
            current_volume=current.end_volume_total,
            volume_change_ratio=volume_change_ratio,
            signal_ask_drop=signal_sell1_drop,
            signal_volume_spike=False,
            signal_buy_flow=signal_buy_flow,
            prev_window_ts=previous.end_ts,
            curr_window_ts=current.end_ts,
            data_quality=current.data_quality,
            confidence=confidence,
            trigger_ts=current.end_ts,
            reason=reason,
            trigger_rule=reason,
            current_buy_volume=current_buy_volume if signal_buy_flow else None,
            cumulative_buy_volume_before=cumulative_before if signal_buy_flow else None,
        )

    def _finalize_completed_bucket(self, code: str, pool_stock: PoolStock, completed: _MinuteBucket) -> AlertEvent | None:
        """Finalize one completed minute and evaluate OR rules against previous one-word minute."""
        previous = self.prev_bucket_map.get(code)
        if previous is None:
            self.sell1_confirm_count_map[code] = 0
            return None
        return self._emit_alert_if_hit(code, pool_stock, previous=previous, current=completed)

    def evaluate(self, snapshot: StockSnapshot) -> AlertEvent | None:
        """Consume one snapshot and return an alert when any eligible rule is triggered."""
        code = snapshot.code
        pool_stock = self.active_pool.get(code)
        if pool_stock is None or code in self.processed_set:
            return None

        if snapshot.high_price > snapshot.limit_down_price:
            self.removed_pool.add(code)
            self.active_pool.pop(code, None)
            self._clear_symbol_runtime_state(code)
            self.fired_rules_map.pop(code, None)
            return None

        # Global gate: both Rule A and Rule B must run under one-word condition.
        if not snapshot.is_one_word_limit_down:
            self._clear_symbol_runtime_state(code)
            return None

        current = self.current_bucket_map.get(code)
        incoming = self._build_bucket(snapshot)

        if current is None:
            self.current_bucket_map[code] = incoming
            return None

        if incoming.minute_key == current.minute_key:
            # Same minute: keep latest quote as minute-end approximation.
            self.current_bucket_map[code] = incoming
            return None

        # Minute changed: finalize previous minute then roll forward.
        event = self._finalize_completed_bucket(code, pool_stock, completed=current)
        self.prev_bucket_map[code] = current
        self.current_bucket_map[code] = incoming
        return event

    def flush_pending(self) -> list[AlertEvent]:
        """Finalize pending minute buckets (typically called once at session end)."""
        events: list[AlertEvent] = []
        for code, current in list(self.current_bucket_map.items()):
            pool_stock = self.active_pool.get(code)
            if pool_stock is None or code in self.processed_set:
                continue

            event = self._finalize_completed_bucket(code, pool_stock, completed=current)
            self.prev_bucket_map[code] = current
            if event is not None:
                events.append(event)

        # Prevent duplicate alerts if flush is called multiple times.
        self.current_bucket_map.clear()
        return events

    def summary(self) -> dict[str, int]:
        """Return compact runtime counters for logging and diagnostics."""
        triggered_buy_flow = sum(1 for rules in self.fired_rules_map.values() if RULE_BUY_FLOW in rules)
        triggered_sell1_drop = sum(1 for rules in self.fired_rules_map.values() if RULE_SELL1_DROP in rules)
        return {
            "active": len(self.active_pool),
            "processed": len(self.processed_set),
            "removed": len(self.removed_pool),
            "current_minutes": len(self.current_bucket_map),
            "previous_minutes": len(self.prev_bucket_map),
            "triggered_buy_flow": triggered_buy_flow,
            "triggered_sell1_drop": triggered_sell1_drop,
            "fully_silenced": len(self.processed_set),
        }
