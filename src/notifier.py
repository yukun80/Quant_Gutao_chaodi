from __future__ import annotations

"""Notification gateway wrapper based on Apprise."""

from loguru import logger

from .models import AlertEvent


class NotificationGateway:
    """Send strategy alerts to configured messaging endpoint."""

    def __init__(self, dingtalk_url: str, keyword: str = "【翘板提醒】") -> None:
        self.dingtalk_url = dingtalk_url
        self.keyword = keyword.strip() or "【翘板提醒】"
        self.app = None
        try:
            import apprise

            app = apprise.Apprise()
            app.add(dingtalk_url)
            self.app = app
        except Exception as exc:
            logger.warning("apprise init failed: {}", exc)

    def send_alert(self, event: AlertEvent) -> bool:
        """Send one alert event and return whether delivery succeeded."""
        if not self.app:
            logger.error("notification gateway unavailable")
            return False

        body = f"{self.keyword}\n{event.format_message()}"
        try:
            ok = self.app.notify(title="Gutao_Chaodi Alert", body=body)
            if not ok:
                logger.error("notification send failed for {}", event.code)
            return bool(ok)
        except Exception as exc:
            logger.exception("notification exception for {}: {}", event.code, exc)
            return False
