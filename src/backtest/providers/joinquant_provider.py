from __future__ import annotations

"""JoinQuant minute-bar provider for backtest replay."""

from datetime import date, datetime, time
from typing import Any, Protocol

import pandas as pd
from loguru import logger

from ..mapper import normalize_code_to_jq
from .base import IntradayMinuteProvider


class JoinQuantAdapter(Protocol):
    """Minimal adapter protocol for easier testing and mocking."""

    def auth(self, username: str, password: str) -> Any: ...

    def get_price(self, security: str, **kwargs: Any) -> pd.DataFrame: ...

    def get_query_count(self) -> Any: ...


def _is_missing(value: Any) -> bool:
    """Treat NaN and platform sentinel values as missing."""
    if value in (None, "", "-"):
        return True
    return bool(pd.isna(value))


def _is_permission_or_quota_error(exc: Exception) -> bool:
    """Return true when provider error likely indicates auth/quota restrictions."""
    text = str(exc).lower()
    return any(
        token in text
        for token in ("permission", "denied", "no right", "quota", "limit", "付费", "机构使用", "购买需求")
    )


def _dedupe(items: list[str]) -> list[str]:
    """Keep order while removing duplicates from requested field list."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class JoinQuantMinuteProvider(IntradayMinuteProvider):
    """Fetch minute bars from JoinQuant and normalize for the backtest runner."""

    def __init__(
        self,
        username: str | None,
        password: str | None,
        ask_v1_field: str = "volume",
        allow_proxy_fallback: bool = True,
        jq_adapter: JoinQuantAdapter | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.ask_v1_field = ask_v1_field
        self.allow_proxy_fallback = allow_proxy_fallback
        self.jq = jq_adapter or self._import_jq()
        self._authenticated = False

    @staticmethod
    def _import_jq() -> JoinQuantAdapter:
        """Import SDK lazily so unit tests can run without JoinQuant runtime."""
        try:
            import jqdatasdk as jq  # type: ignore[import-not-found]

            return jq
        except Exception as exc:  # pragma: no cover - depends on runtime env
            raise RuntimeError("jqdatasdk is required for JoinQuant backtest") from exc

    def _ensure_auth(self) -> None:
        """Authenticate once and fail fast when credentials/quota are invalid."""
        if self._authenticated:
            return
        if not self.username or not self.password:
            raise ValueError("JoinQuant credential missing: set JQ_USERNAME and JQ_PASSWORD")
        try:
            self.jq.auth(self.username, self.password)
        except Exception as exc:
            raise RuntimeError(f"JoinQuant auth failed: {exc}") from exc

        get_query_count = getattr(self.jq, "get_query_count", None)
        if callable(get_query_count):
            try:
                # Query call verifies account state after successful auth.
                get_query_count()
            except Exception as exc:
                raise RuntimeError(f"JoinQuant auth failed: {exc}") from exc

        self._authenticated = True

    @staticmethod
    def _resolve_ts(df: pd.DataFrame) -> pd.Series:
        """Resolve bar timestamps from either explicit column or datetime index."""
        if "time" in df.columns:
            return pd.to_datetime(df["time"])
        if isinstance(df.index, pd.DatetimeIndex):
            return pd.Series(df.index, index=df.index)
        raise ValueError("JoinQuant minute data missing datetime index")

    def fetch_intraday_minutes(self, code: str, trade_date: date) -> list[dict[str, Any]]:
        """Fetch one-day minute data and map to runner-compatible dict records."""
        self._ensure_auth()

        jq_code = normalize_code_to_jq(code)
        start_dt = datetime.combine(trade_date, time(9, 30))
        end_dt = datetime.combine(trade_date, time(15, 0))
        fields = _dedupe(["close", "high", "low_limit", "pre_close", "volume", self.ask_v1_field])

        try:
            df = self.jq.get_price(
                jq_code,
                start_date=start_dt,
                end_date=end_dt,
                frequency="1m",
                fields=fields,
                skip_paused=True,
                fq=None,
                panel=False,
            )
        except Exception as exc:
            if _is_permission_or_quota_error(exc):
                raise RuntimeError(f"JoinQuant permission/quota error: {exc}") from exc
            raise RuntimeError(f"JoinQuant get_price failed: {exc}") from exc

        if df is None or len(df) == 0:
            return []

        logger.debug(
            "joinquant proxy minute columns code={} date={} columns={}",
            jq_code,
            trade_date,
            list(df.columns),
        )
        # data_quality is attached to every row so downstream reports can expose confidence.
        ask_v1_source = self.ask_v1_field
        data_quality = "tick_a1v" if self.ask_v1_field.lower() in {"a1_v", "ask_v1"} else "minute_proxy"
        if self.ask_v1_field not in df.columns:
            if self.allow_proxy_fallback and "volume" in df.columns:
                # Graceful degrade: keep replay runnable but mark as low-confidence proxy.
                ask_v1_source = "volume"
                data_quality = "minute_proxy"
                logger.warning(
                    "joinquant ask_v1 field {} missing for {} on {}, fallback to volume proxy",
                    self.ask_v1_field,
                    jq_code,
                    trade_date,
                )
            else:
                raise ValueError(
                    f"JoinQuant minute data missing field '{self.ask_v1_field}', "
                    f"available columns: {list(df.columns)}"
                )
        if "volume" not in df.columns:
            raise ValueError(
                "JoinQuant minute data missing field 'volume', "
                f"available columns: {list(df.columns)}"
            )

        ts_series = self._resolve_ts(df)
        records: list[dict[str, Any]] = []
        for idx, (_, row) in enumerate(df.iterrows()):
            limit_down_price = row.get("low_limit")
            if _is_missing(limit_down_price):
                # Some rows may miss low_limit; fallback to exchange rule pre_close * 0.9.
                pre_close = row.get("pre_close")
                if _is_missing(pre_close):
                    limit_down_price = None
                else:
                    limit_down_price = round(float(pre_close) * 0.9, 2)

            records.append(
                {
                    "ts": ts_series.iloc[idx],
                    "code": code,
                    "name": jq_code,
                    "close": row.get("close"),
                    "high": row.get("high"),
                    "limit_down_price": limit_down_price,
                    "ask_v1": row.get(ask_v1_source),
                    "volume": row.get("volume"),
                    "ask_v1_source": ask_v1_source,
                    "data_quality": data_quality,
                }
            )
        return records
