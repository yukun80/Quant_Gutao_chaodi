from __future__ import annotations

"""Daily stock-pool construction using AkShare with cache failover."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

import pandas as pd
from loguru import logger

from .config import Settings
from .models import PoolStock

_CACHE_COLUMNS = ["code", "name", "is_st", "pool_type", "built_at"]


class DataProvider(Protocol):
    """Provider abstraction to support test doubles and real APIs."""

    def fetch_realtime_st_list(self) -> pd.DataFrame: ...

    def fetch_stock_basic(self) -> pd.DataFrame: ...


@dataclass
class AkshareOnlyProvider:
    """Concrete provider that fetches stock universe and realtime ST labels via AkShare."""

    settings: Settings

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
        """Fetch full listed universe used as baseline daily pool."""
        import akshare as ak

        df = ak.stock_zh_a_spot_em()
        renamed = df.rename(columns={"代码": "symbol", "名称": "name"})
        if "symbol" not in renamed.columns or "name" not in renamed.columns:
            raise ValueError("akshare stock_zh_a_spot_em response missing required columns")
        renamed["symbol"] = renamed["symbol"].astype(str).str.zfill(6)
        return renamed[["symbol", "name"]].copy()


class PoolManager:
    """Build strategy pool objects from provider dataframes."""

    def __init__(self, settings: Settings, provider: DataProvider | None = None) -> None:
        self.settings = settings
        self.provider = provider or AkshareOnlyProvider(settings)

    def build_daily_pool(self, trade_date: date | None = None) -> list[PoolStock]:
        """Construct today's pool with ST label attached to each symbol."""
        _ = trade_date or date.today()
        try:
            stock_basic = self.provider.fetch_stock_basic()
            st_realtime = self.provider.fetch_realtime_st_list()
            pool = self._build_pool_from_frames(stock_basic=stock_basic, st_realtime=st_realtime)
            self._save_pool_cache(pool)
            logger.info("pool build source=akshare_online symbols={}", len(pool))
            return pool
        except Exception as exc:
            if self.settings.POOL_FAILOVER_MODE != "cache":
                raise RuntimeError(f"online pool build failed and failover disabled: {exc}") from exc
            pool = self._load_pool_cache()
            logger.warning("pool build source=cache_fallback symbols={} reason={}", len(pool), exc)
            return pool

    @staticmethod
    def _normalize_symbol(value: object) -> str | None:
        """Normalize external symbol formats to local 6-digit code."""
        raw = str(value).strip()
        if not raw:
            return None
        if "." in raw:
            maybe_symbol = raw.split(".", maxsplit=1)[0].strip()
            if maybe_symbol.isdigit():
                raw = maybe_symbol
        if not raw.isdigit():
            return None
        normalized = raw.zfill(6)
        if len(normalized) != 6:
            return None
        return normalized

    def _normalize_basic_frame(self, stock_basic: pd.DataFrame) -> pd.DataFrame:
        """Normalize stock basic frame into unique symbol/name rows."""
        if "symbol" not in stock_basic.columns or "name" not in stock_basic.columns:
            raise ValueError("stock_basic response missing required columns: symbol/name")
        normalized = stock_basic.copy()
        normalized["symbol"] = normalized["symbol"].apply(self._normalize_symbol)
        normalized = normalized.dropna(subset=["symbol"])
        normalized = normalized.drop_duplicates(subset=["symbol"], keep="first")
        normalized["name"] = normalized["name"].astype(str).str.strip()
        normalized.loc[normalized["name"] == "", "name"] = normalized["symbol"]
        return normalized[["symbol", "name"]].copy()

    def _normalize_st_frame(self, st_realtime: pd.DataFrame) -> pd.DataFrame:
        """Normalize realtime ST frame into unique symbol rows."""
        if "symbol" not in st_realtime.columns:
            raise ValueError("st_realtime response missing required column: symbol")
        normalized = st_realtime.copy()
        normalized["symbol"] = normalized["symbol"].apply(self._normalize_symbol)
        normalized = normalized.dropna(subset=["symbol"])
        normalized = normalized.drop_duplicates(subset=["symbol"], keep="first")
        return normalized[["symbol"]].copy()

    def _build_pool_from_frames(self, stock_basic: pd.DataFrame, st_realtime: pd.DataFrame) -> list[PoolStock]:
        """Build pool list from provider dataframes after normalization."""
        basic = self._normalize_basic_frame(stock_basic)
        st = self._normalize_st_frame(st_realtime)
        st_set = set(st["symbol"].astype(str).tolist())
        pool: list[PoolStock] = []
        for _, row in basic.sort_values("symbol").iterrows():
            symbol = str(row["symbol"])
            pool.append(
                PoolStock(
                    code=symbol,
                    name=str(row["name"]),
                    is_st=symbol in st_set,
                    pool_type="all",
                )
            )
        return pool

    def _cache_path(self) -> Path:
        return Path(self.settings.POOL_CACHE_PATH)

    def _save_pool_cache(self, pool: list[PoolStock]) -> None:
        """Persist latest successful pool build for failover use."""
        if not pool:
            return
        cache_path = self._cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        built_at = datetime.now().replace(microsecond=0).isoformat()
        records = [
            {
                "code": item.code,
                "name": item.name,
                "is_st": item.is_st,
                "pool_type": item.pool_type,
                "built_at": built_at,
            }
            for item in pool
        ]
        pd.DataFrame.from_records(records, columns=_CACHE_COLUMNS).to_csv(cache_path, index=False)

    def _load_pool_cache(self) -> list[PoolStock]:
        """Load previous pool snapshot when online provider is unavailable."""
        cache_path = self._cache_path()
        if not cache_path.exists():
            raise RuntimeError(f"pool cache not found: {cache_path}")

        frame = pd.read_csv(cache_path)
        if frame.empty:
            raise RuntimeError(f"pool cache is empty: {cache_path}")
        missing = [column for column in _CACHE_COLUMNS if column not in frame.columns]
        if missing:
            raise RuntimeError(f"pool cache missing columns: {missing}")

        built_at_text = str(frame["built_at"].iloc[0]).strip()
        built_at = datetime.fromisoformat(built_at_text)
        if datetime.now() - built_at > timedelta(hours=self.settings.POOL_CACHE_TTL_HOURS):
            raise RuntimeError(
                f"pool cache expired: built_at={built_at.isoformat()} ttl_hours={self.settings.POOL_CACHE_TTL_HOURS}"
            )

        pool: list[PoolStock] = []
        for _, row in frame.iterrows():
            code = self._normalize_symbol(row["code"])
            if code is None:
                continue
            name = str(row["name"]).strip() or code
            is_st = str(row["is_st"]).strip().lower() in {"1", "true", "t", "yes", "y"}
            pool.append(
                PoolStock(
                    code=code,
                    name=name,
                    is_st=is_st,
                    pool_type="all",
                )
            )
        if not pool:
            raise RuntimeError(f"pool cache is empty: {cache_path}")
        return pool


def parse_hhmm(value: str) -> datetime.time:
    """Parse HH:MM string from settings into a `time` object."""
    return datetime.strptime(value, "%H:%M").time()
