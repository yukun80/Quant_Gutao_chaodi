from __future__ import annotations

"""Daily stock-pool construction using Tushare and AkShare."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd
import tushare as ts

from .config import Settings
from .models import PoolStock


class DataProvider(Protocol):
    """Provider abstraction to support test doubles and real APIs."""

    def fetch_realtime_st_list(self) -> pd.DataFrame: ...

    def fetch_stock_basic(self) -> pd.DataFrame: ...


@dataclass
class TushareAkshareProvider:
    """Concrete provider that fetches stock universe and realtime ST labels."""

    settings: Settings

    def __post_init__(self) -> None:
        """Initialize Tushare client once per provider instance."""
        ts.set_token(self.settings.TUSHARE_TOKEN)
        self.pro = ts.pro_api()

    def fetch_realtime_st_list(self) -> pd.DataFrame:
        """Fetch realtime ST tags and normalize expected columns."""
        import akshare as ak

        df = ak.stock_zh_a_st_em()
        renamed = df.rename(columns={"代码": "symbol", "名称": "name"})
        if "symbol" not in renamed.columns or "name" not in renamed.columns:
            raise ValueError("akshare stock_zh_a_st_em response missing required columns")
        renamed["symbol"] = renamed["symbol"].astype(str).str.zfill(6)
        return renamed[["symbol", "name"]].copy()

    def fetch_stock_basic(self) -> pd.DataFrame:
        """Fetch full listed universe used as the baseline daily pool."""
        df = self.pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,list_date",
        )
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        return df


class PoolManager:
    """Build strategy pool objects from provider dataframes."""

    def __init__(self, settings: Settings, provider: DataProvider | None = None) -> None:
        self.settings = settings
        self.provider = provider or TushareAkshareProvider(settings)

    def build_daily_pool(self, trade_date: date | None = None) -> list[PoolStock]:
        """Construct today's pool with ST label attached to each symbol."""
        _ = trade_date or date.today()
        stock_basic = self.provider.fetch_stock_basic()
        st_realtime = self.provider.fetch_realtime_st_list()
        st_set = set(st_realtime["symbol"].astype(str).tolist())
        pool: list[PoolStock] = []
        for _, row in stock_basic.iterrows():
            symbol = str(row["symbol"]).zfill(6)
            pool.append(
                PoolStock(
                    code=symbol,
                    name=str(row["name"]),
                    is_st=symbol in st_set,
                    pool_type="all",
                )
            )
        return pool


def parse_hhmm(value: str) -> datetime.time:
    """Parse HH:MM string from settings into a `time` object."""
    return datetime.strptime(value, "%H:%M").time()
