from __future__ import annotations

from datetime import datetime

from src.runtime_status import RuntimeStatus


def test_runtime_status_counters_and_heartbeat_age() -> None:
    status = RuntimeStatus(service_started_at=datetime(2026, 2, 20, 9, 0, 0))
    now = datetime(2026, 2, 20, 9, 1, 0)

    status.mark_live_started(now)
    status.mark_poll(now)
    status.mark_alert(now)
    status.mark_error("boom", now)
    status.set_monitor_window(True, now)

    assert status.live_running is True
    assert status.monitor_rounds == 1
    assert status.alerts_sent == 1
    assert status.last_error == "boom"
    assert status.in_monitor_window is True

    later = datetime(2026, 2, 20, 9, 1, 8)
    assert status.heartbeat_age_sec(later) == 8

    status.mark_live_finished(later)
    assert status.live_running is False
