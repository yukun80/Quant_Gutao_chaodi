from __future__ import annotations

"""CLI argument and execution contract tests."""

from datetime import date, datetime
from typing import Any

from src.backtest_cli import run_cli
from src.config import get_settings


class FakeProvider:
    def __init__(self, bars: list[dict[str, Any]]) -> None:
        self.bars = bars

    def fetch_intraday_minutes(self, code: str, trade_date: date) -> list[dict[str, Any]]:
        return self.bars


class ErrorProvider:
    def fetch_intraday_minutes(self, code: str, trade_date: date) -> list[dict[str, Any]]:
        raise RuntimeError("network down")


def _seed_required_env(monkeypatch) -> None:
    monkeypatch.setenv("DINGTALK_URL", "https://oapi.dingtalk.com/robot/send?access_token=dummy")
    monkeypatch.setenv("JQ_USERNAME", "jq_user")
    monkeypatch.setenv("JQ_PASSWORD", "jq_password")
    get_settings.cache_clear()


def test_cli_triggered(monkeypatch, capsys) -> None:
    _seed_required_env(monkeypatch)

    def provider_factory(
        source: str,
        username: str | None,
        password: str | None,
    ):
        assert source == "joinquant"
        assert username == "jq_user"
        assert password == "jq_password"
        return FakeProvider(
            [
                {
                    "ts": datetime(2025, 1, 10, 9, 31),
                    "close": 10.0,
                    "high": 10.0,
                    "limit_down_price": 10.0,
                    "volume": 100,
                },
                {
                    "ts": datetime(2025, 1, 10, 13, 1),
                    "close": 10.0,
                    "high": 10.0,
                    "limit_down_price": 10.0,
                    "volume": 80,
                },
                {
                    "ts": datetime(2025, 1, 10, 13, 2),
                    "close": 10.0,
                    "high": 10.0,
                    "limit_down_price": 10.0,
                    "volume": 300,
                },
            ]
        )

    rc = run_cli(
        ["--date", "2025-01-10", "--code", "600000", "--source", "joinquant"],
        provider_factory=provider_factory,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "=== Gutao_Chaodi Backtest Precheck ===" in out
    assert "jq_code: 600000.XSHG" in out
    assert "strategy: buy_flow_breakout" in out
    assert "trigger_rule: current_buy_volume > cumulative_buy_volume_before" in out
    assert "window: 13:00-15:00" in out
    assert "triggered: YES" in out
    assert "reason: buy_flow_breakout" in out
    assert "data_quality: minute_proxy" in out
    assert "samples_one_word_in_window: 2" in out
    assert "current_buy_volume: 300" in out


def test_cli_invalid_date(monkeypatch, capsys) -> None:
    _seed_required_env(monkeypatch)
    rc = run_cli(["--date", "20250110", "--code", "600000"], provider_factory=lambda *_: FakeProvider([]))
    out = capsys.readouterr().out
    assert rc == 2
    assert "invalid --date" in out


def test_cli_invalid_code(monkeypatch, capsys) -> None:
    _seed_required_env(monkeypatch)
    rc = run_cli(
        ["--date", "2025-01-10", "--code", "6000"],
        provider_factory=lambda *_: FakeProvider([]),
    )
    out = capsys.readouterr().out
    assert rc == 2
    assert "invalid --code" in out


def test_cli_invalid_window(monkeypatch, capsys) -> None:
    _seed_required_env(monkeypatch)
    rc = run_cli(
        ["--date", "2025-01-10", "--code", "600000", "--window-start", "xx:yy"],
        provider_factory=lambda *_: FakeProvider([]),
    )
    out = capsys.readouterr().out
    assert rc == 2
    assert "invalid window" in out


def test_cli_execution_error(monkeypatch, capsys) -> None:
    _seed_required_env(monkeypatch)
    rc = run_cli(
        ["--date", "2025-01-10", "--code", "600000", "--source", "joinquant"],
        provider_factory=lambda *_: ErrorProvider(),
    )
    out = capsys.readouterr().out
    assert rc == 3
    assert "backtest execution failed" in out


def test_cli_invalid_source(monkeypatch, capsys) -> None:
    _seed_required_env(monkeypatch)
    rc = run_cli(
        ["--date", "2025-01-10", "--code", "600000", "--source", "foo"],
        provider_factory=lambda *_: FakeProvider([]),
    )
    out = capsys.readouterr().out
    assert rc == 2
    assert "source must be 'joinquant'" in out
