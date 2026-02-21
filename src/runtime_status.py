from __future__ import annotations

"""Runtime service status registry shared by scheduler and live monitor."""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class RuntimeStatus:
    """Mutable runtime state used by scheduler and alert pipeline."""

    service_started_at: datetime = field(default_factory=datetime.now)
    last_heartbeat_at: datetime | None = None
    last_poll_at: datetime | None = None
    last_alert_at: datetime | None = None
    last_error: str | None = None
    in_monitor_window: bool = False
    live_running: bool = False
    monitor_rounds: int = 0
    alerts_sent: int = 0
    last_live_date: date | None = None

    def mark_heartbeat(self, now: datetime | None = None) -> None:
        """Update generic process heartbeat timestamp."""
        self.last_heartbeat_at = now or datetime.now()

    def mark_live_started(self, now: datetime | None = None) -> None:
        """Mark live monitor session as started."""
        timestamp = now or datetime.now()
        self.live_running = True
        self.last_error = None
        self.last_live_date = timestamp.date()
        self.mark_heartbeat(timestamp)

    def mark_live_finished(self, now: datetime | None = None) -> None:
        """Mark live monitor session as finished."""
        timestamp = now or datetime.now()
        self.live_running = False
        self.mark_heartbeat(timestamp)

    def mark_poll(self, now: datetime | None = None) -> None:
        """Record one polling round in live monitoring loop."""
        timestamp = now or datetime.now()
        self.monitor_rounds += 1
        self.last_poll_at = timestamp
        self.mark_heartbeat(timestamp)

    def mark_alert(self, now: datetime | None = None) -> None:
        """Record one successful notification event."""
        timestamp = now or datetime.now()
        self.alerts_sent += 1
        self.last_alert_at = timestamp
        self.mark_heartbeat(timestamp)

    def mark_error(self, error: str, now: datetime | None = None) -> None:
        """Record latest runtime error."""
        self.last_error = error
        self.mark_heartbeat(now or datetime.now())

    def set_monitor_window(self, in_window: bool, now: datetime | None = None) -> None:
        """Track whether current wall-clock time is in monitor range."""
        self.in_monitor_window = in_window
        self.mark_heartbeat(now or datetime.now())

    def heartbeat_age_sec(self, now: datetime | None = None) -> int | None:
        """Return seconds since last heartbeat, or None if not available yet."""
        if self.last_heartbeat_at is None:
            return None
        reference = now or datetime.now()
        return max(int((reference - self.last_heartbeat_at).total_seconds()), 0)
