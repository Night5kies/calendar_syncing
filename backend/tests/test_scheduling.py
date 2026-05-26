import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.scheduling import (
    Interval,
    SuggestionInputs,
    TimeWindow,
    generate_suggestions,
)


NY = ZoneInfo("America/New_York")


def make_inputs(**overrides):
    base = dict(
        start_date=date(2026, 5, 25),
        end_date=date(2026, 5, 29),
        duration_min=60,
        timezone="America/New_York",
        event_type=None,
        days_of_week=(0, 1, 2, 3, 4),
        time_windows=(),
        exclude_dates=(),
        limit=5,
    )
    base.update(overrides)
    return SuggestionInputs(**base)


class GenerateSuggestionsTests(unittest.TestCase):
    def test_basic_generation_with_explicit_windows(self) -> None:
        inputs = make_inputs(
            time_windows=(TimeWindow(start_minute=10 * 60, end_minute=12 * 60),),
            limit=3,
        )
        results = generate_suggestions(inputs)
        self.assertEqual(len(results), 3)
        for suggestion in results:
            self.assertEqual(suggestion.end_at - suggestion.start_at, timedelta(minutes=60))
            self.assertTrue(10 <= suggestion.start_at.hour < 12)
            self.assertEqual(suggestion.start_at.tzinfo, NY)

    def test_excludes_dates(self) -> None:
        inputs = make_inputs(
            time_windows=(TimeWindow(start_minute=10 * 60, end_minute=12 * 60),),
            exclude_dates=(date(2026, 5, 25), date(2026, 5, 26)),
            limit=10,
        )
        results = generate_suggestions(inputs)
        for suggestion in results:
            self.assertNotIn(suggestion.start_at.date(), {date(2026, 5, 25), date(2026, 5, 26)})

    def test_respects_days_of_week(self) -> None:
        inputs = make_inputs(
            start_date=date(2026, 5, 25),
            end_date=date(2026, 5, 31),
            days_of_week=(5, 6),
            time_windows=(TimeWindow(start_minute=10 * 60, end_minute=12 * 60),),
            limit=10,
        )
        results = generate_suggestions(inputs)
        for suggestion in results:
            self.assertIn(suggestion.start_at.weekday(), {5, 6})

    def test_template_window_alignment_adds_score(self) -> None:
        # meal window is 12:00-14:00 / 18:00-20:30 — coffee at 09:00 should NOT match
        meal_inputs = make_inputs(event_type="meal", limit=3)
        meal_results = generate_suggestions(meal_inputs)
        self.assertTrue(meal_results)
        for suggestion in meal_results:
            hour = suggestion.start_at.hour
            self.assertTrue(
                (12 <= hour < 14) or (18 <= hour) or (hour == 20 and suggestion.start_at.minute <= 0),
                f"Unexpected start hour for meal suggestion: {suggestion.start_at}",
            )

    def test_blocked_intervals_filtered(self) -> None:
        block_start = datetime(2026, 5, 25, 10, 30, tzinfo=NY)
        block_end = datetime(2026, 5, 25, 12, 0, tzinfo=NY)
        inputs = make_inputs(
            start_date=date(2026, 5, 25),
            end_date=date(2026, 5, 25),
            time_windows=(TimeWindow(start_minute=10 * 60, end_minute=14 * 60),),
            limit=10,
        )
        results = generate_suggestions(
            inputs,
            blocked_intervals=[Interval(start=block_start, end=block_end)],
        )
        for suggestion in results:
            self.assertFalse(
                suggestion.start_at < block_end and suggestion.end_at > block_start,
                f"Suggestion {suggestion.start_at} overlaps blocked window",
            )
        # at least one suggestion should appear at 12:00 or later
        self.assertTrue(any(s.start_at.hour >= 12 for s in results))

    def test_deterministic_ordering(self) -> None:
        inputs = make_inputs(
            time_windows=(TimeWindow(start_minute=10 * 60, end_minute=12 * 60),),
            limit=4,
        )
        first = generate_suggestions(inputs)
        second = generate_suggestions(inputs)
        self.assertEqual(
            [s.start_at for s in first],
            [s.start_at for s in second],
        )

    def test_invalid_date_range(self) -> None:
        with self.assertRaises(ValueError):
            generate_suggestions(
                make_inputs(start_date=date(2026, 5, 30), end_date=date(2026, 5, 25))
            )

    def test_dedupes_overlapping_suggestions(self) -> None:
        inputs = make_inputs(
            start_date=date(2026, 5, 25),
            end_date=date(2026, 5, 25),
            time_windows=(TimeWindow(start_minute=10 * 60, end_minute=12 * 60),),
            limit=10,
        )
        results = generate_suggestions(inputs)
        for left, right in zip(results, results[1:]):
            self.assertFalse(
                left.start_at < right.end_at and left.end_at > right.start_at,
                "Overlap leaked through dedupe",
            )


if __name__ == "__main__":
    unittest.main()
