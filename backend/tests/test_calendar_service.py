import unittest
from datetime import datetime, timezone

from app.api.v1.calendar import get_enabled_calendar_ids
from app.services.calendar import merge_intervals, redact_events_for_permission


class CalendarServiceTests(unittest.TestCase):
    def test_merge_intervals(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        intervals = [
            (start, start.replace(hour=2)),
            (start.replace(hour=1), start.replace(hour=3)),
            (start.replace(hour=5), start.replace(hour=6)),
        ]
        merged = merge_intervals(intervals)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0], (start, start.replace(hour=3)))

    def test_redact_private_events_in_details(self) -> None:
        events = [
            {"start_at": "2026-01-01T10:00:00Z", "end_at": "2026-01-01T11:00:00Z", "is_private": True},
            {
                "start_at": "2026-01-01T12:00:00Z",
                "end_at": "2026-01-01T13:00:00Z",
                "is_private": False,
                "title": "Lunch",
            },
        ]
        payload = redact_events_for_permission(events, "details")
        self.assertEqual(len(payload["busy"]), 1)
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["title"], "Lunch")

    def test_free_busy_returns_busy_only(self) -> None:
        events = [
            {"start_at": "2026-01-01T10:00:00Z", "end_at": "2026-01-01T11:00:00Z", "is_private": False},
        ]
        payload = redact_events_for_permission(events, "free_busy")
        self.assertIn("busy", payload)
        self.assertNotIn("events", payload)

    def test_toggle_excludes_disabled_calendar(self) -> None:
        class Calendar:
            def __init__(self, provider, provider_calendar_id, is_enabled):
                self.provider = provider
                self.provider_calendar_id = provider_calendar_id
                self.is_enabled = is_enabled

        calendars = [
            Calendar("google", "cal-1", True),
            Calendar("google", "cal-2", False),
        ]
        enabled = get_enabled_calendar_ids(calendars, "google")
        self.assertEqual(enabled, ["cal-1"])


if __name__ == "__main__":
    unittest.main()
