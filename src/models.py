from __future__ import annotations

"""Domain models shared by live engine and backtest pipeline."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PoolType = Literal["all"]
SignalCombination = Literal["and", "or"]
DataQuality = Literal["tick_a1v", "minute_proxy"]
ConfidenceLevel = Literal["high", "low"]


class PoolStock(BaseModel):
    """Stock metadata kept in the daily monitoring pool."""

    code: str
    name: str
    is_st: bool
    pool_type: PoolType

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize external symbol formats to 6-digit local code."""
        value = value.strip()
        if "." in value:
            value = value.split(".")[0]
        return value


class StockSnapshot(BaseModel):
    """Normalized intraday snapshot consumed by strategy evaluation."""

    code: str
    name: str
    current_price: float
    limit_down_price: float
    high_price: float
    ask_v1: int = Field(default=0)
    volume: int = Field(default=0)
    data_quality: DataQuality = "tick_a1v"
    ts: datetime = Field(default_factory=datetime.now)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Normalize snapshot symbol to keep key lookup stable."""
        value = value.strip()
        if "." in value:
            value = value.split(".")[0]
        return value

    @field_validator("current_price", "limit_down_price", "high_price", mode="before")
    @classmethod
    def parse_price(cls, value: object) -> float:
        """Accept raw API values and coerce missing markers to zero."""
        if value in (None, "", "-"):
            return 0.0
        if isinstance(value, str):
            return float(value.replace(",", ""))
        return float(value)

    @field_validator("ask_v1", mode="before")
    @classmethod
    def parse_ask_v1(cls, value: object) -> int:
        """Accept raw order-book values and coerce missing markers to zero."""
        if value in (None, "", "-"):
            return 0
        if isinstance(value, str):
            return int(float(value.replace(",", "")))
        return int(value)

    @field_validator("volume", mode="before")
    @classmethod
    def parse_volume(cls, value: object) -> int:
        """Accept raw volume values and coerce missing markers to zero."""
        if value in (None, "", "-"):
            return 0
        if isinstance(value, str):
            return int(float(value.replace(",", "")))
        return int(value)

    @property
    def is_one_word_limit_down(self) -> bool:
        """Return true when the symbol never traded above limit-down intraday."""
        return self.current_price == self.limit_down_price and self.high_price == self.limit_down_price


class AlertEvent(BaseModel):
    """Immutable alert payload used by notification gateways."""

    code: str
    name: str
    pool_type: PoolType
    initial_ask_v1: int
    current_ask_v1: int
    drop_ratio: float
    initial_volume: int = 0
    current_volume: int = 0
    volume_change_ratio: float = 0.0
    signal_ask_drop: bool = False
    signal_volume_spike: bool = False
    prev_window_ts: datetime | None = None
    curr_window_ts: datetime | None = None
    data_quality: DataQuality = "tick_a1v"
    confidence: ConfidenceLevel = "high"
    trigger_ts: datetime = Field(default_factory=datetime.now)
    reason: str = "window_delta"

    def format_message(self) -> str:
        """Format a human-readable alert body."""
        return (
            f"[{self.pool_type}] {self.code} {self.name} 封单异动\n"
            f"上一窗卖一: {self.initial_ask_v1}\n"
            f"当前窗卖一: {self.current_ask_v1}\n"
            f"卖一降幅: {self.drop_ratio:.2%}\n"
            f"上一窗成交量: {self.initial_volume}\n"
            f"当前窗成交量: {self.current_volume}\n"
            f"成交量增幅: {self.volume_change_ratio:.2%}\n"
            f"信号: ask_drop={self.signal_ask_drop} volume_spike={self.signal_volume_spike}\n"
            f"数据质量: {self.data_quality}/{self.confidence}\n"
            f"触发时间: {self.trigger_ts:%Y-%m-%d %H:%M:%S}"
        )
