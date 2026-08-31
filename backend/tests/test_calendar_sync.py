"""Coverage for cache freshness, ICS output, and the suggestion busy window."""
import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.calendar import FRESHNESS_MINUTES, is_window_stale
from app.services.confirmation_artifacts import build_ics_body, escape_ics, fold_line
from app.services.scheduling import local_day_range, resolve_timezone


def _unfold(body: str) -> str:
    """Reverse RFC 5545 line folding, the way a calendar client would."""
    return body.replace("\r\n ", "")


NOW = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
FRESH = NOW - timedelta(minutes=FRESHNESS_MINUTES - 1)
STALE = NOW - timedelta(minutes=FRESHNESS_MINUTES + 1)


class WindowFreshnessTests(unittest.TestCase):
    """A synced-but-empty window must not re-hit the provider every request."""

    def setUp(self) -> None:
        self.start = datetime(2026, 3, 2, tzinfo=timezone.utc)
        self.end = datetime(2026, 3, 9, tzinfo=timezone.utc)

    def test_no_markers_is_stale(self) -> None:
        self.assertTrue(is_window_stale([], self.start, self.end, now=NOW))

    def test_recent_covering_marker_is_fresh(self) -> None:
        markers = [(self.start, self.end, FRESH)]
        self.assertFalse(is_window_stale(markers, self.start, self.end, now=NOW))

    def test_wider_marker_covers_a_narrower_request(self) -> None:
        markers = [(self.start - timedelta(days=7), self.end + timedelta(days=7), FRESH)]
        self.assertFalse(is_window_stale(markers, self.start, self.end, now=NOW))

    def test_partial_marker_does_not_cover(self) -> None:
        markers = [(self.start, self.end - timedelta(days=1), FRESH)]
        self.assertTrue(is_window_stale(markers, self.start, self.end, now=NOW))

    def test_aged_marker_is_stale(self) -> None:
        markers = [(self.start, self.end, STALE)]
        self.assertTrue(is_window_stale(markers, self.start, self.end, now=NOW))


class LocalDayRangeTests(unittest.TestCase):
    def test_window_spans_local_midnights(self) -> None:
        start, end = local_day_range(date(2026, 3, 2), date(2026, 3, 4), "America/New_York")
        tz = ZoneInfo("America/New_York")
        self.assertEqual(start, datetime(2026, 3, 2, tzinfo=tz))
        self.assertEqual(end, datetime(2026, 3, 5, tzinfo=tz))

    def test_covers_the_final_local_evening(self) -> None:
        """The UTC-midnight window used to stop before the last local evening."""
        start, end = local_day_range(date(2026, 3, 2), date(2026, 3, 4), "America/New_York")
        last_evening = datetime(2026, 3, 4, 21, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertTrue(start <= last_evening < end)
        naive_utc_end = datetime(2026, 3, 5, tzinfo=timezone.utc)
        self.assertGreater(end, naive_utc_end)

    def test_covers_the_first_local_morning_east_of_utc(self) -> None:
        start, end = local_day_range(date(2026, 3, 2), date(2026, 3, 4), "Asia/Tokyo")
        first_morning = datetime(2026, 3, 2, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.assertTrue(start <= first_morning < end)
        naive_utc_start = datetime(2026, 3, 2, tzinfo=timezone.utc)
        self.assertLess(start, naive_utc_start)

    def test_unknown_timezone_is_a_value_error(self) -> None:
        # `timezone` is unvalidated at request creation, and a raw
        # ZoneInfoNotFoundError surfaced as a 500 instead of a 422.
        with self.assertRaises(ValueError):
            resolve_timezone("Nowhere/Fake")
        with self.assertRaises(ValueError):
            local_day_range(date(2026, 3, 2), date(2026, 3, 4), "Nowhere/Fake")


class IcsBodyTests(unittest.TestCase):
    def _build(self, **overrides) -> str:
        kwargs = {
            "uid": "abc@syzy",
            "title": "Coffee",
            "start_at_utc": "20260302T150000Z",
            "end_at_utc": "20260302T153000Z",
            "description": None,
            "location": None,
            "organizer_email": "organizer@example.com",
        }
        kwargs.update(overrides)
        return build_ics_body(**kwargs)

    def test_dtstamp_is_generation_time_not_event_start(self) -> None:
        body = self._build(dtstamp_utc="20260301T090000Z")
        self.assertIn("DTSTAMP:20260301T090000Z", body)
        self.assertIn("DTSTART:20260302T150000Z", body)

    def test_dtstamp_defaults_to_now(self) -> None:
        body = self._build()
        stamp = next(line for line in body.split("\r\n") if line.startswith("DTSTAMP:"))
        self.assertNotIn("20260302T150000Z", stamp)

    def test_sequence_is_emitted(self) -> None:
        self.assertIn("SEQUENCE:3", self._build(sequence=3))
        self.assertIn("SEQUENCE:0", self._build())

    def test_method_matches_attendee_presence(self) -> None:
        # Long ATTENDEE lines are folded, so assert against the unfolded body.
        with_attendees = _unfold(self._build(attendees=["guest@example.com"]))
        self.assertIn("METHOD:REQUEST", with_attendees)
        self.assertIn("mailto:guest@example.com", with_attendees)
        self.assertIn("RSVP=TRUE", with_attendees)

        without = _unfold(self._build())
        self.assertIn("METHOD:PUBLISH", without)
        self.assertNotIn("ATTENDEE", without)

    def test_blank_attendee_entries_are_ignored(self) -> None:
        body = _unfold(self._build(attendees=["", None]))
        self.assertIn("METHOD:PUBLISH", body)
        self.assertNotIn("ATTENDEE", body)

    def test_lines_are_folded_to_75_octets(self) -> None:
        body = self._build(title="A" * 300)
        for line in body.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)

    def test_folding_preserves_content(self) -> None:
        folded = fold_line("SUMMARY:" + "B" * 200)
        self.assertEqual(folded.replace("\r\n ", ""), "SUMMARY:" + "B" * 200)

    def test_folding_never_splits_a_multibyte_character(self) -> None:
        folded = fold_line("SUMMARY:" + "é" * 100)
        for chunk in folded.split("\r\n "):
            chunk.encode("utf-8").decode("utf-8")  # must not raise
        self.assertEqual(folded.replace("\r\n ", ""), "SUMMARY:" + "é" * 100)

    def test_carriage_returns_are_escaped(self) -> None:
        self.assertEqual(escape_ics("a\r\nb"), r"a\nb")
        self.assertEqual(escape_ics("a\rb"), r"a\nb")

    def test_crlf_terminated(self) -> None:
        body = self._build()
        self.assertTrue(body.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n\n", body)


if __name__ == "__main__":
    unittest.main()
