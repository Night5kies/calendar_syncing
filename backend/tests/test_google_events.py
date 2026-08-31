"""Coverage for how raw Google payloads become busy intervals."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

from app.providers import google


def _connection() -> SimpleNamespace:
    return SimpleNamespace(access_token="acc-1", refresh_token="ref-1", expires_at=None)


WINDOW_START = datetime(2026, 3, 2, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 3, 9, tzinfo=timezone.utc)


def _timed(event_id: str, start: str, end: str, **extra) -> dict:
    payload = {
        "id": event_id,
        "status": "confirmed",
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    payload.update(extra)
    return payload


class BusyEventFilterTests(unittest.TestCase):
    def test_cancelled_events_are_not_busy(self) -> None:
        self.assertFalse(google.is_busy_event({"status": "cancelled"}))

    def test_free_marked_events_are_not_busy(self) -> None:
        self.assertFalse(google.is_busy_event({"transparency": "transparent"}))

    def test_declined_by_self_is_not_busy(self) -> None:
        event = {
            "attendees": [
                {"email": "other@example.com", "responseStatus": "accepted"},
                {"email": "me@example.com", "self": True, "responseStatus": "declined"},
            ]
        }
        self.assertFalse(google.is_busy_event(event))

    def test_someone_else_declining_leaves_it_busy(self) -> None:
        event = {
            "attendees": [
                {"email": "other@example.com", "responseStatus": "declined"},
                {"email": "me@example.com", "self": True, "responseStatus": "accepted"},
            ]
        }
        self.assertTrue(google.is_busy_event(event))

    def test_working_location_entries_are_not_busy(self) -> None:
        self.assertFalse(google.is_busy_event({"eventType": "workingLocation"}))

    def test_ordinary_event_is_busy(self) -> None:
        self.assertTrue(google.is_busy_event({"status": "confirmed", "summary": "Standup"}))


class AllDayParsingTests(unittest.TestCase):
    def test_all_day_uses_calendar_timezone(self) -> None:
        parsed = google._parse_google_datetime({"date": "2026-03-04"}, "America/New_York")
        self.assertEqual(
            parsed, datetime(2026, 3, 4, tzinfo=ZoneInfo("America/New_York"))
        )
        # 00:00 New York is 05:00 UTC -- not the 00:00 UTC the old code produced.
        self.assertEqual(parsed.astimezone(timezone.utc).hour, 5)

    def test_all_day_falls_back_to_utc_without_a_zone(self) -> None:
        parsed = google._parse_google_datetime({"date": "2026-03-04"}, None)
        self.assertEqual(parsed, datetime(2026, 3, 4, tzinfo=timezone.utc))

    def test_unknown_timezone_falls_back_to_utc(self) -> None:
        parsed = google._parse_google_datetime({"date": "2026-03-04"}, "Mars/Olympus")
        self.assertEqual(parsed, datetime(2026, 3, 4, tzinfo=timezone.utc))


class FetchEventsTests(unittest.TestCase):
    def test_follows_pagination(self) -> None:
        pages = [
            {
                "timeZone": "UTC",
                "items": [_timed("a", "2026-03-02T10:00:00Z", "2026-03-02T11:00:00Z")],
                "nextPageToken": "page-2",
            },
            {
                "timeZone": "UTC",
                "items": [_timed("b", "2026-03-03T10:00:00Z", "2026-03-03T11:00:00Z")],
            },
        ]
        with mock.patch.object(google, "_google_request", side_effect=pages) as request:
            events = google.fetch_events(
                _connection(), ["primary"], WINDOW_START, WINDOW_END
            )
        self.assertEqual([event["provider_event_id"] for event in events], ["a", "b"])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[1].kwargs["params"]["pageToken"], "page-2")

    def test_drops_non_busy_entries(self) -> None:
        page = {
            "timeZone": "UTC",
            "items": [
                _timed("busy", "2026-03-02T10:00:00Z", "2026-03-02T11:00:00Z"),
                _timed(
                    "free",
                    "2026-03-02T12:00:00Z",
                    "2026-03-02T13:00:00Z",
                    transparency="transparent",
                ),
                _timed(
                    "gone",
                    "2026-03-02T14:00:00Z",
                    "2026-03-02T15:00:00Z",
                    status="cancelled",
                ),
                _timed(
                    "declined",
                    "2026-03-02T16:00:00Z",
                    "2026-03-02T17:00:00Z",
                    attendees=[{"self": True, "responseStatus": "declined"}],
                ),
            ],
        }
        with mock.patch.object(google, "_google_request", return_value=page):
            events = google.fetch_events(
                _connection(), ["primary"], WINDOW_START, WINDOW_END
            )
        self.assertEqual([event["provider_event_id"] for event in events], ["busy"])

    def test_zero_length_events_are_dropped(self) -> None:
        page = {
            "timeZone": "UTC",
            "items": [_timed("point", "2026-03-02T10:00:00Z", "2026-03-02T10:00:00Z")],
        }
        with mock.patch.object(google, "_google_request", return_value=page):
            events = google.fetch_events(
                _connection(), ["primary"], WINDOW_START, WINDOW_END
            )
        self.assertEqual(events, [])

    def test_requests_exclude_deleted_events(self) -> None:
        with mock.patch.object(
            google, "_google_request", return_value={"items": []}
        ) as request:
            google.fetch_events(_connection(), ["primary"], WINDOW_START, WINDOW_END)
        self.assertEqual(request.call_args.kwargs["params"]["showDeleted"], "false")


class ListCalendarsTests(unittest.TestCase):
    def test_unselected_calendars_are_disabled(self) -> None:
        page = {
            "items": [
                {"id": "primary@example.com", "summary": "Me", "primary": True},
                {"id": "holidays", "summary": "Holidays"},
                {"id": "team", "summary": "Team", "selected": True},
                {"id": "old", "summary": "Old", "deleted": True},
            ]
        }
        with mock.patch.object(google, "_google_request", return_value=page):
            calendars = google.list_calendars(_connection())
        by_id = {calendar["provider_calendar_id"]: calendar for calendar in calendars}
        self.assertNotIn("old", by_id)
        # Google omits `selected` for hidden calendars, so it must not default True.
        self.assertFalse(by_id["holidays"]["is_enabled"])
        self.assertTrue(by_id["team"]["is_enabled"])
        # The primary calendar stays usable even without an explicit `selected`.
        self.assertTrue(by_id["primary@example.com"]["is_enabled"])


class RevokeTests(unittest.TestCase):
    def test_success_and_already_invalid_both_count(self) -> None:
        for code in (200, 400):
            with mock.patch.object(
                google.httpx, "post", return_value=SimpleNamespace(status_code=code, text="")
            ):
                self.assertTrue(google.revoke_token("tok"))

    def test_unexpected_status_is_a_failure(self) -> None:
        with mock.patch.object(
            google.httpx, "post", return_value=SimpleNamespace(status_code=500, text="boom")
        ):
            self.assertFalse(google.revoke_token("tok"))

    def test_missing_token_is_a_noop(self) -> None:
        self.assertFalse(google.revoke_token(None))


if __name__ == "__main__":
    unittest.main()
