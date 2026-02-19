"""Model parsing and normalization tests."""

from src.models import StockSnapshot


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
