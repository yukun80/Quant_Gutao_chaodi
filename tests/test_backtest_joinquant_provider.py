from __future__ import annotations

"""JoinQuant provider behavior tests with SDK doubles."""

from datetime import date

import pandas as pd
import pytest

from src.backtest.providers.joinquant_provider import JoinQuantMinuteProvider


class FakeJQAdapter:
    def __init__(
        self,
        frame: pd.DataFrame,
        auth_error: Exception | None = None,
        price_error: Exception | None = None,
    ) -> None:
        self.frame = frame
        self.authed = False
        self.auth_error = auth_error
        self.price_error = price_error

    def auth(self, username: str, password: str):
        if self.auth_error is not None:
            raise self.auth_error
        self.authed = True
        return True

    def get_query_count(self):
        return {"spare": 1000, "total": 100000}

    def get_price(self, security: str, **kwargs):
        if self.price_error is not None:
            raise self.price_error
        return self.frame


def test_joinquant_provider_fetch_minutes() -> None:
    frame = pd.DataFrame(
        {
            "close": [10.0, 10.0],
            "high": [10.0, 10.0],
            "low_limit": [10.0, 10.0],
            "volume": [1000, 700],
        },
        index=pd.to_datetime(["2025-01-10 14:00:00", "2025-01-10 14:01:00"]),
    )
    provider = JoinQuantMinuteProvider(
        username="u",
        password="p",
        ask_v1_field="volume",
        jq_adapter=FakeJQAdapter(frame),
    )

    rows = provider.fetch_intraday_minutes(code="600000", trade_date=date(2025, 1, 10))
    assert len(rows) == 2
    assert rows[0]["ask_v1"] == 1000
    assert rows[0]["volume"] == 1000
    assert rows[0]["data_quality"] == "minute_proxy"
    assert rows[1]["limit_down_price"] == 10.0


def test_joinquant_provider_missing_ask_field() -> None:
    frame = pd.DataFrame(
        {
            "close": [10.0],
            "high": [10.0],
            "low_limit": [10.0],
        },
        index=pd.to_datetime(["2025-01-10 14:00:00"]),
    )
    provider = JoinQuantMinuteProvider(
        username="u",
        password="p",
        ask_v1_field="volume",
        jq_adapter=FakeJQAdapter(frame),
    )
    with pytest.raises(ValueError) as exc:
        provider.fetch_intraday_minutes(code="600000", trade_date=date(2025, 1, 10))
    assert "available columns" in str(exc.value)


def test_joinquant_provider_missing_ask_field_fallback_to_volume() -> None:
    frame = pd.DataFrame(
        {
            "close": [10.0],
            "high": [10.0],
            "low_limit": [10.0],
            "volume": [1000],
        },
        index=pd.to_datetime(["2025-01-10 14:00:00"]),
    )
    provider = JoinQuantMinuteProvider(
        username="u",
        password="p",
        ask_v1_field="a1_v",
        allow_proxy_fallback=True,
        jq_adapter=FakeJQAdapter(frame),
    )
    rows = provider.fetch_intraday_minutes(code="600000", trade_date=date(2025, 1, 10))
    assert rows[0]["ask_v1"] == 1000
    assert rows[0]["ask_v1_source"] == "volume"
    assert rows[0]["data_quality"] == "minute_proxy"


def test_joinquant_provider_auth_failed() -> None:
    frame = pd.DataFrame(
        {
            "close": [10.0],
            "high": [10.0],
            "low_limit": [10.0],
            "volume": [1000],
        },
        index=pd.to_datetime(["2025-01-10 14:00:00"]),
    )
    provider = JoinQuantMinuteProvider(
        username="u",
        password="p",
        ask_v1_field="volume",
        jq_adapter=FakeJQAdapter(frame, auth_error=RuntimeError("bad credential")),
    )
    with pytest.raises(RuntimeError) as exc:
        provider.fetch_intraday_minutes(code="600000", trade_date=date(2025, 1, 10))
    assert "JoinQuant auth failed" in str(exc.value)


def test_joinquant_provider_permission_error() -> None:
    frame = pd.DataFrame(
        {
            "close": [10.0],
            "high": [10.0],
            "low_limit": [10.0],
            "volume": [1000],
        },
        index=pd.to_datetime(["2025-01-10 14:00:00"]),
    )
    provider = JoinQuantMinuteProvider(
        username="u",
        password="p",
        ask_v1_field="volume",
        jq_adapter=FakeJQAdapter(frame, price_error=RuntimeError("属于付费模块")),
    )
    with pytest.raises(RuntimeError) as exc:
        provider.fetch_intraday_minutes(code="600000", trade_date=date(2025, 1, 10))
    assert "permission/quota" in str(exc.value)
