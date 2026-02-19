"""Regression tests for strategy one-shot and removal behavior."""

from datetime import datetime

from src.engine import StrategyEngine
from src.models import PoolStock, StockSnapshot


def test_one_shot_trigger_after_consecutive_confirm() -> None:
    engine = StrategyEngine(
        ask_drop_threshold=0.3,
        volume_spike_threshold=0.5,
        confirm_minutes=2,
        signal_combination="and",
    )
    engine.register_pool([PoolStock(code="600000", name="A", is_st=False, pool_type="all")])

    # first window only initializes the rolling previous point
    assert engine.evaluate(
        StockSnapshot(
            code="600000",
            name="A",
            current_price=10,
            high_price=10,
            limit_down_price=10,
            ask_v1=1000,
            volume=100,
            ts=datetime(2025, 1, 10, 14, 0),
        )
    ) is None

    # hit #1: ask down + volume up
    assert engine.evaluate(
        StockSnapshot(
            code="600000",
            name="A",
            current_price=10,
            high_price=10,
            limit_down_price=10,
            ask_v1=600,
            volume=220,
            ts=datetime(2025, 1, 10, 14, 1),
        )
    ) is None

    # hit #2: still ask down + volume up, reaches confirm count
    event = engine.evaluate(
        StockSnapshot(
            code="600000",
            name="A",
            current_price=10,
            high_price=10,
            limit_down_price=10,
            ask_v1=300,
            volume=500,
            ts=datetime(2025, 1, 10, 14, 2),
        )
    )
    assert event is not None
    assert event.reason == "volume_spike_and_sell1_drop"
    assert event.signal_ask_drop is True
    assert event.signal_volume_spike is True

    # second trigger blocked
    assert (
        engine.evaluate(
            StockSnapshot(
                code="600000",
                name="A",
                current_price=10,
                high_price=10,
                limit_down_price=10,
                ask_v1=200,
                volume=800,
                ts=datetime(2025, 1, 10, 14, 3),
            )
        )
        is None
    )


def test_confirm_reset_on_rebound() -> None:
    engine = StrategyEngine(
        ask_drop_threshold=0.3,
        volume_spike_threshold=0.5,
        confirm_minutes=2,
        signal_combination="and",
    )
    engine.register_pool([PoolStock(code="600001", name="B", is_st=False, pool_type="all")])

    assert engine.evaluate(
        StockSnapshot(
            code="600001",
            name="B",
            current_price=10,
            high_price=10,
            limit_down_price=10,
            ask_v1=1000,
            volume=100,
            ts=datetime(2025, 1, 10, 14, 0),
        )
    ) is None

    # hit #1
    assert engine.evaluate(
        StockSnapshot(
            code="600001",
            name="B",
            current_price=10,
            high_price=10,
            limit_down_price=10,
            ask_v1=600,
            volume=220,
            ts=datetime(2025, 1, 10, 14, 1),
        )
    ) is None

    # volume spike missing, resets confirm counter in AND mode
    assert engine.evaluate(
        StockSnapshot(
            code="600001",
            name="B",
            current_price=10,
            high_price=10,
            limit_down_price=10,
            ask_v1=500,
            volume=230,
            ts=datetime(2025, 1, 10, 14, 2),
        )
    ) is None

    # only first hit again, should not trigger
    assert engine.evaluate(
        StockSnapshot(
            code="600001",
            name="B",
            current_price=10,
            high_price=10,
            limit_down_price=10,
            ask_v1=200,
            volume=500,
            ts=datetime(2025, 1, 10, 14, 3),
        )
    ) is None


def test_open_board_removal() -> None:
    engine = StrategyEngine(ask_drop_threshold=0.3, volume_spike_threshold=0.5, confirm_minutes=2)
    engine.register_pool([PoolStock(code="000001", name="B", is_st=True, pool_type="all")])

    assert (
        engine.evaluate(
            StockSnapshot(
                code="000001",
                name="B",
                current_price=10,
                high_price=10.1,
                limit_down_price=10,
                ask_v1=1000,
                volume=100,
            )
        )
        is None
    )
    assert "000001" in engine.removed_pool


def test_or_mode_triggers_with_single_signal() -> None:
    engine = StrategyEngine(
        ask_drop_threshold=0.3,
        volume_spike_threshold=10.0,
        confirm_minutes=1,
        signal_combination="or",
    )
    engine.register_pool([PoolStock(code="600010", name="C", is_st=False, pool_type="all")])

    assert (
        engine.evaluate(
            StockSnapshot(
                code="600010",
                name="C",
                current_price=10,
                high_price=10,
                limit_down_price=10,
                ask_v1=1000,
                volume=100,
            )
        )
        is None
    )

    event = engine.evaluate(
        StockSnapshot(
            code="600010",
            name="C",
            current_price=10,
            high_price=10,
            limit_down_price=10,
            ask_v1=500,
            volume=110,
        )
    )
    assert event is not None
    assert event.signal_ask_drop is True
    assert event.signal_volume_spike is False
