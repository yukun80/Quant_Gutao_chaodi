"""Model parsing and normalization tests."""

from src.models import AlertEvent, StockSnapshot


def test_snapshot_cleaning_dash_and_empty() -> None:
    snap = StockSnapshot(
        code="000001.SZ",
        name="Demo",
        current_price="-",
        high_price="",
        limit_down_price="10.0",
        ask_v1="-",
    )
    assert snap.code == "000001"
    assert snap.current_price == 0.0
    assert snap.high_price == 0.0
    assert snap.ask_v1 == 0
    assert snap.volume == 0


def test_snapshot_cleaning_numeric_string() -> None:
    snap = StockSnapshot(
        code="600000",
        name="Demo",
        current_price="12.34",
        high_price="12.34",
        limit_down_price="12.34",
        ask_v1="12345",
        volume="6789",
    )
    assert snap.ask_v1 == 12345
    assert snap.volume == 6789
    assert snap.is_one_word_limit_down


def test_alert_event_message_contains_rule_and_buy_flow_fields() -> None:
    event = AlertEvent(
        code="600000",
        name="Demo",
        pool_type="all",
        initial_ask_v1=1000,
        current_ask_v1=500,
        drop_ratio=0.5,
        reason="buy_flow_breakout",
        trigger_rule="buy_flow_breakout",
        signal_buy_flow=True,
        current_buy_volume=300,
        cumulative_buy_volume_before=200,
    )
    body = event.format_message()
    assert "触发规则: buy_flow_breakout" in body
    assert "当前分钟成交量(代理): 300" in body
    assert "当日前序累计成交量: 200" in body
