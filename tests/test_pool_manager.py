"""Pool manager tests using fake provider data."""

from datetime import date

import pandas as pd
import pytest

from src.config import Settings
from src.pool_manager import PoolManager


class FakeProvider:
    def fetch_realtime_st_list(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"symbol": "000002", "name": "ST新例"},
                {"symbol": "000003", "name": "*ST退市风险"},
            ]
        )

    def fetch_stock_basic(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"symbol": "000001", "name": "平安银行"},
                {"symbol": "000002", "name": "ST新例"},
                {"symbol": "000003", "name": "*ST退市风险"},
            ]
        )


class DirtySymbolProvider(FakeProvider):
    def fetch_stock_basic(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"symbol": "1", "name": "平安银行"},
                {"symbol": "000001", "name": "平安银行重复"},
                {"symbol": "invalid", "name": "无效"},
                {"symbol": "600000.SH", "name": "浦发银行"},
                {"symbol": "300750", "name": ""},
            ]
        )

    def fetch_realtime_st_list(self) -> pd.DataFrame:
        return pd.DataFrame([{"symbol": "300750", "name": "ST示例"}])


class FailingProvider(FakeProvider):
    def fetch_stock_basic(self) -> pd.DataFrame:
        raise RuntimeError("network down")


def test_daily_pool_contains_all_symbols(tmp_path) -> None:
    settings = Settings(
        DINGTALK_URL="https://oapi.dingtalk.com/robot/send?access_token=dummy",
        POOL_CACHE_PATH=str(tmp_path / "pool.csv"),
    )
    manager = PoolManager(settings=settings, provider=FakeProvider())
    pool = manager.build_daily_pool(trade_date=date(2025, 2, 15))

    by_code = {stock.code: stock for stock in pool}
    assert by_code["000001"].pool_type == "all"
    assert by_code["000001"].is_st is False
    assert by_code["000002"].is_st is True
    assert by_code["000003"].is_st is True


def test_pool_normalizes_symbols_and_names(tmp_path) -> None:
    settings = Settings(
        DINGTALK_URL="https://oapi.dingtalk.com/robot/send?access_token=dummy",
        POOL_CACHE_PATH=str(tmp_path / "pool.csv"),
    )
    manager = PoolManager(settings=settings, provider=DirtySymbolProvider())
    pool = manager.build_daily_pool()

    by_code = {stock.code: stock for stock in pool}
    assert set(by_code) == {"000001", "300750", "600000"}
    assert by_code["300750"].name == "300750"
    assert by_code["300750"].is_st is True


def test_pool_falls_back_to_cache_when_online_build_fails(tmp_path) -> None:
    cache_path = tmp_path / "pool_cache.csv"
    settings = Settings(
        DINGTALK_URL="https://oapi.dingtalk.com/robot/send?access_token=dummy",
        POOL_CACHE_PATH=str(cache_path),
    )
    online_manager = PoolManager(settings=settings, provider=FakeProvider())
    online_pool = online_manager.build_daily_pool()
    assert cache_path.exists()

    fallback_manager = PoolManager(settings=settings, provider=FailingProvider())
    fallback_pool = fallback_manager.build_daily_pool()
    assert [item.code for item in fallback_pool] == [item.code for item in online_pool]


def test_pool_fail_fast_mode_raises_when_online_build_fails(tmp_path) -> None:
    settings = Settings(
        DINGTALK_URL="https://oapi.dingtalk.com/robot/send?access_token=dummy",
        POOL_CACHE_PATH=str(tmp_path / "pool.csv"),
        POOL_FAILOVER_MODE="fail_fast",
    )
    manager = PoolManager(settings=settings, provider=FailingProvider())
    with pytest.raises(RuntimeError, match="failover disabled"):
        manager.build_daily_pool()
