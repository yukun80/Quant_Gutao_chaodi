"""Pool manager tests using fake provider data."""

from datetime import date

import pandas as pd

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
                {"symbol": "000001", "name": "平安银行", "list_date": "19910403", "ts_code": "000001.SZ"},
                {"symbol": "000002", "name": "ST新例", "list_date": "20000101", "ts_code": "000002.SZ"},
                {"symbol": "000003", "name": "*ST退市风险", "list_date": "20000101", "ts_code": "000003.SZ"},
            ]
        )

def test_daily_pool_contains_all_symbols() -> None:
    settings = Settings(
        TUSHARE_TOKEN="token",
        DINGTALK_URL="https://oapi.dingtalk.com/robot/send?access_token=dummy",
    )
    manager = PoolManager(settings=settings, provider=FakeProvider())
    pool = manager.build_daily_pool(trade_date=date(2025, 2, 15))

    by_code = {stock.code: stock for stock in pool}
    assert by_code["000001"].pool_type == "all"
    assert by_code["000001"].is_st is False
    assert by_code["000002"].is_st is True
    assert by_code["000003"].is_st is True
