from __future__ import annotations

"""Configuration model for both live monitoring and backtest workflows."""

from datetime import datetime
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TUSHARE_TOKEN: str
    DINGTALK_URL: str
    DINGTALK_KEYWORD: str = "【翘板提醒】"

    VOL_DROP_THRESHOLD: float = Field(default=0.50)
    ASK_DROP_THRESHOLD: float | None = None
    VOLUME_SPIKE_THRESHOLD: float = Field(default=0.8)
    SIGNAL_WINDOW_MINUTES: int = Field(default=1)
    SIGNAL_COMBINATION: str = "and"
    MIN_ABS_DELTA_ASK: int = 0
    MIN_ABS_DELTA_VOLUME: int = 0
    MAX_CONCURRENCY: int = Field(default=50)
    REQUEST_TIMEOUT_SEC: float = Field(default=2.0)
    RETRY_ATTEMPTS: int = Field(default=3)
    RETRY_WAIT_SEC: float = Field(default=0.5)
    POLL_INTERVAL_SEC: float = Field(default=1.0)
    JITTER_MIN_SEC: float = Field(default=0.1)
    JITTER_MAX_SEC: float = Field(default=0.5)

    MONITOR_START_TIME: str = "13:00"
    MONITOR_END_TIME: str = "15:00"

    EM_API_BASE: str = "https://push2.eastmoney.com/api/qt/stock/get"
    EM_FIELDS: str = "f57,f58,f2,f15,f51,f31,f47"
    EM_HEADERS_JSON: str | None = None
    EM_COOKIE: str | None = None

    BACKTEST_SOURCE: str = "joinquant"
    BACKTEST_USE_NOTIFIER: bool = False
    BACKTEST_MINUTE_ASKV1_FIELD: str = "volume"
    BACKTEST_PROXY_MODE: str = "allow_proxy"
    BACKTEST_WINDOW_START: str | None = None
    BACKTEST_WINDOW_END: str | None = None
    BACKTEST_CONFIRM_MINUTES: int = Field(default=1)
    BACKTEST_VOLUME_SPIKE_THRESHOLD: float | None = None
    BACKTEST_SIGNAL_COMBINATION: str | None = "or"
    BACKTEST_MIN_ABS_DELTA_ASK: int | None = None
    BACKTEST_MIN_ABS_DELTA_VOLUME: int | None = None
    JQ_USERNAME: str | None = None
    JQ_PASSWORD: str | None = None

    @field_validator("VOL_DROP_THRESHOLD")
    @classmethod
    def validate_threshold(cls, value: float) -> float:
        """Ensure strategy threshold remains in a meaningful ratio range."""
        if not 0 < value < 1:
            raise ValueError("VOL_DROP_THRESHOLD must be in (0, 1)")
        return value

    @field_validator("ASK_DROP_THRESHOLD")
    @classmethod
    def validate_ask_drop_threshold(cls, value: float | None) -> float | None:
        """Validate optional ask-drop threshold override."""
        if value is None:
            return None
        if not 0 < value < 1:
            raise ValueError("ASK_DROP_THRESHOLD must be in (0, 1)")
        return value

    @field_validator("VOLUME_SPIKE_THRESHOLD")
    @classmethod
    def validate_volume_spike_threshold(cls, value: float) -> float:
        """Volume spike threshold should be non-negative ratio."""
        if value < 0:
            raise ValueError("VOLUME_SPIKE_THRESHOLD must be >= 0")
        return value

    @field_validator("MAX_CONCURRENCY")
    @classmethod
    def validate_concurrency(cls, value: int) -> int:
        """Cap concurrency to avoid invalid or extreme runtime settings."""
        if value <= 0 or value > 100:
            raise ValueError("MAX_CONCURRENCY must be in [1, 100]")
        return value

    @field_validator("SIGNAL_WINDOW_MINUTES")
    @classmethod
    def validate_window_minutes(cls, value: int) -> int:
        """Window size must stay within practical intraday bounds."""
        if value <= 0 or value > 30:
            raise ValueError("SIGNAL_WINDOW_MINUTES must be in [1, 30]")
        return value

    @field_validator("MIN_ABS_DELTA_ASK", "MIN_ABS_DELTA_VOLUME")
    @classmethod
    def validate_min_abs_delta(cls, value: int) -> int:
        """Absolute delta floors cannot be negative."""
        if value < 0:
            raise ValueError("MIN_ABS_DELTA values must be >= 0")
        return value

    @field_validator("BACKTEST_CONFIRM_MINUTES")
    @classmethod
    def validate_confirm_minutes(cls, value: int) -> int:
        """Require a positive consecutive confirmation count."""
        if value <= 0 or value > 20:
            raise ValueError("BACKTEST_CONFIRM_MINUTES must be in [1, 20]")
        return value

    @field_validator("SIGNAL_COMBINATION", "BACKTEST_SIGNAL_COMBINATION")
    @classmethod
    def validate_signal_combination(cls, value: str | None) -> str | None:
        """Support either and/or signal composition mode."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"and", "or"}:
            raise ValueError("SIGNAL_COMBINATION must be 'and' or 'or'")
        return normalized

    @field_validator("BACKTEST_PROXY_MODE")
    @classmethod
    def validate_backtest_proxy_mode(cls, value: str) -> str:
        """Backtest proxy mode controls whether ask_v1 fallback is allowed."""
        normalized = value.strip().lower()
        if normalized not in {"allow_proxy", "strict"}:
            raise ValueError("BACKTEST_PROXY_MODE must be 'allow_proxy' or 'strict'")
        return normalized

    @field_validator("BACKTEST_VOLUME_SPIKE_THRESHOLD")
    @classmethod
    def validate_backtest_volume_spike_threshold(cls, value: float | None) -> float | None:
        """Backtest volume threshold override must be non-negative."""
        if value is None:
            return None
        if value < 0:
            raise ValueError("BACKTEST_VOLUME_SPIKE_THRESHOLD must be >= 0")
        return value

    @field_validator("BACKTEST_MIN_ABS_DELTA_ASK", "BACKTEST_MIN_ABS_DELTA_VOLUME")
    @classmethod
    def validate_backtest_min_abs_delta(cls, value: int | None) -> int | None:
        """Backtest absolute delta overrides cannot be negative."""
        if value is None:
            return None
        if value < 0:
            raise ValueError("BACKTEST_MIN_ABS_DELTA values must be >= 0")
        return value

    @field_validator("BACKTEST_SOURCE")
    @classmethod
    def validate_backtest_source(cls, value: str) -> str:
        """Validate configured backtest provider name."""
        normalized = value.strip().lower()
        if normalized not in {"joinquant"}:
            raise ValueError("BACKTEST_SOURCE only supports 'joinquant' now")
        return normalized

    @field_validator("BACKTEST_WINDOW_START", "BACKTEST_WINDOW_END", "MONITOR_START_TIME", "MONITOR_END_TIME")
    @classmethod
    def validate_hhmm(cls, value: str | None) -> str | None:
        """Validate configured HH:MM time strings when present."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        datetime.strptime(normalized, "%H:%M")
        return normalized

    @field_validator("DINGTALK_KEYWORD")
    @classmethod
    def validate_dingtalk_keyword(cls, value: str) -> str:
        """Ensure keyword is non-empty because DingTalk may enforce keyword filters."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("DINGTALK_KEYWORD must not be empty")
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings to avoid repeated environment parsing."""
    return Settings()
