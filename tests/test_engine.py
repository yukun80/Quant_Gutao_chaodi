"""Regression tests for live strategy OR-rules and one-word gate behavior."""

from datetime import datetime

from src.engine import StrategyEngine
from src.models import PoolStock, StockSnapshot


def _snap(
    *,
    code: str = "600000",
    name: str = "A",
    ts: datetime,
    current_price: float = 10.0,
    high_price: float = 10.0,
    limit_down_price: float = 10.0,
    ask_v1: int = 1000,
    volume: int = 100,
) -> StockSnapshot:
    return StockSnapshot(
        code=code,
        name=name,
        current_price=current_price,
        high_price=high_price,
        limit_down_price=limit_down_price,
        ask_v1=ask_v1,
        volume=volume,
        ts=ts,
    )


def test_buy_flow_breakout_triggered_under_one_word_gate() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.95, confirm_minutes=1)
    engine.register_pool([PoolStock(code="600000", name="A", is_st=False, pool_type="all")])

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 0), ask_v1=1000, volume=100)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 1), ask_v1=980, volume=150)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 2), ask_v1=960, volume=400)) is None

    event = engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 3), ask_v1=950, volume=420))
    assert event is not None
    assert event.reason == "buy_flow_breakout"
    assert event.signal_buy_flow is True
    assert event.signal_ask_drop is False
    assert event.current_buy_volume == 250
    assert event.cumulative_buy_volume_before == 150
    assert "600000" not in engine.processed_set


def test_sell1_drop_triggered_under_one_word_gate() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.3, confirm_minutes=1)
    engine.register_pool([PoolStock(code="600000", name="A", is_st=False, pool_type="all")])

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 0), ask_v1=1000, volume=100)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 1), ask_v1=900, volume=160)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 2), ask_v1=400, volume=220)) is None

    event = engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 3), ask_v1=390, volume=240))
    assert event is not None
    assert event.reason == "sell1_drop"
    assert event.signal_buy_flow is False
    assert event.signal_ask_drop is True
    assert event.current_buy_volume is None
    assert event.cumulative_buy_volume_before is None
    assert "600000" not in engine.processed_set


def test_non_one_word_snapshot_resets_runtime_context() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.3, confirm_minutes=1)
    engine.register_pool([PoolStock(code="600000", name="A", is_st=False, pool_type="all")])

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 0), ask_v1=1000, volume=100)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 1), ask_v1=500, volume=160)) is None

    # Non one-word minute breaks state continuity for both Rule A and Rule B.
    assert (
        engine.evaluate(
            _snap(
                ts=datetime(2025, 1, 10, 13, 2),
                current_price=9.99,
                high_price=10.0,
                limit_down_price=10.0,
                ask_v1=450,
                volume=220,
            )
        )
        is None
    )

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 3), ask_v1=300, volume=260)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 4), ask_v1=280, volume=300)) is None


def test_combined_alert_marks_symbol_fully_silenced() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.3, confirm_minutes=1)
    engine.register_pool([PoolStock(code="600000", name="A", is_st=False, pool_type="all")])

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 0), ask_v1=1000, volume=100)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 1), ask_v1=800, volume=150)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 2), ask_v1=200, volume=500)) is None

    event = engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 3), ask_v1=190, volume=520))
    assert event is not None
    assert event.reason == "buy_flow_breakout_and_sell1_drop"
    assert event.signal_buy_flow is True
    assert event.signal_ask_drop is True
    assert "600000" in engine.processed_set
    assert "600000" not in engine.monitorable_codes()


def test_each_rule_triggers_once_and_total_alerts_capped_at_two() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.3, confirm_minutes=1)
    engine.register_pool([PoolStock(code="600000", name="A", is_st=False, pool_type="all")])

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 0), ask_v1=1000, volume=100)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 1), ask_v1=900, volume=150)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 2), ask_v1=500, volume=210)) is None

    event_1 = engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 3), ask_v1=480, volume=300))
    assert event_1 is not None
    assert event_1.reason == "sell1_drop"

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 4), ask_v1=470, volume=700)) is None

    event_2 = engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 5), ask_v1=460, volume=760))
    assert event_2 is not None
    assert event_2.reason == "buy_flow_breakout"

    # After both rules fired once, symbol is fully silenced.
    assert "600000" in engine.processed_set
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 6), ask_v1=100, volume=1200)) is None


def test_sell1_drop_respects_confirm_minutes() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.3, confirm_minutes=2)
    engine.register_pool([PoolStock(code="600000", name="A", is_st=False, pool_type="all")])

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 0), ask_v1=1000, volume=100)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 1), ask_v1=700, volume=150)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 2), ask_v1=400, volume=200)) is None

    event = engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 3), ask_v1=390, volume=220))
    assert event is not None
    assert event.reason == "sell1_drop"


def test_open_board_removal() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.3, confirm_minutes=1)
    engine.register_pool([PoolStock(code="000001", name="B", is_st=True, pool_type="all")])

    assert (
        engine.evaluate(
            _snap(
                code="000001",
                name="B",
                ts=datetime(2025, 1, 10, 13, 0),
                current_price=10.0,
                high_price=10.1,
                limit_down_price=10.0,
                ask_v1=1000,
                volume=100,
            )
        )
        is None
    )
    assert "000001" in engine.removed_pool


def test_flush_pending_emits_last_minute_signal_once() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.95, confirm_minutes=1)
    engine.register_pool([PoolStock(code="600000", name="A", is_st=False, pool_type="all")])

    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 0), ask_v1=1000, volume=100)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 1), ask_v1=900, volume=150)) is None
    assert engine.evaluate(_snap(ts=datetime(2025, 1, 10, 13, 2), ask_v1=850, volume=500)) is None

    events = engine.flush_pending()
    assert len(events) == 1
    assert events[0].reason == "buy_flow_breakout"

    # flush is idempotent: pending state has been cleared.
    assert engine.flush_pending() == []
