"""Fetcher configuration and parsing tests."""

from __future__ import annotations

import pytest

from src.config import Settings
from src.fetcher import EastMoneyFetcher


def test_fetcher_accepts_optional_headers_and_cookie() -> None:
    settings = Settings(
        TUSHARE_TOKEN="token",
        DINGTALK_URL="https://oapi.dingtalk.com/robot/send?access_token=dummy",
        EM_HEADERS_JSON='{"User-Agent":"gutao-test","X-Env":"dev"}',
        EM_COOKIE="a=1; b=2",
    )
    fetcher = EastMoneyFetcher(settings)
    assert fetcher.extra_headers["User-Agent"] == "gutao-test"
    assert fetcher.extra_headers["X-Env"] == "dev"
    assert fetcher.extra_headers["Cookie"] == "a=1; b=2"


def test_fetcher_rejects_invalid_header_json() -> None:
    settings = Settings(
        TUSHARE_TOKEN="token",
        DINGTALK_URL="https://oapi.dingtalk.com/robot/send?access_token=dummy",
        EM_HEADERS_JSON="{bad",
    )
    with pytest.raises(ValueError):
        EastMoneyFetcher(settings)
