"""Notifier behavior tests."""

from __future__ import annotations

import sys
import types

from src.models import AlertEvent
from src.notifier import NotificationGateway


class DummyApprise:
    """Simple fake Apprise client for testing body composition."""

    last_instance = None

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.last_title: str | None = None
        self.last_body: str | None = None
        DummyApprise.last_instance = self

    def add(self, url: str) -> None:
        self.urls.append(url)

    def notify(self, title: str, body: str) -> bool:
        self.last_title = title
        self.last_body = body
        return True


def test_notification_includes_keyword(monkeypatch) -> None:
    fake_module = types.SimpleNamespace(Apprise=DummyApprise)
    monkeypatch.setitem(sys.modules, "apprise", fake_module)

    gateway = NotificationGateway(
        dingtalk_url="https://oapi.dingtalk.com/robot/send?access_token=dummy",
        keyword="【翘板提醒】",
    )
    ok = gateway.send_alert(
        AlertEvent(
            code="600000",
            name="A",
            pool_type="all",
            initial_ask_v1=1000,
            current_ask_v1=600,
            drop_ratio=0.4,
        )
    )

    assert ok is True
    assert DummyApprise.last_instance is not None
    assert DummyApprise.last_instance.last_body is not None
    assert DummyApprise.last_instance.last_body.startswith("【翘板提醒】")


def test_send_text(monkeypatch) -> None:
    fake_module = types.SimpleNamespace(Apprise=DummyApprise)
    monkeypatch.setitem(sys.modules, "apprise", fake_module)

    gateway = NotificationGateway(
        dingtalk_url="https://oapi.dingtalk.com/robot/send?access_token=dummy",
        keyword="【翘板提醒】",
    )
    ok = gateway.send_text(title="【服务状态】", body="状态: 正常")

    assert ok is True
    assert DummyApprise.last_instance is not None
    assert DummyApprise.last_instance.last_title == "【服务状态】"
    assert "状态: 正常" in (DummyApprise.last_instance.last_body or "")
