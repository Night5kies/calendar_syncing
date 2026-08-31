import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from app.schemas.availability import (
    AvailabilityBlockCreate,
    AvailabilityRuleUpsert,
    DailyWindow,
    WeeklyHoursPayload,
)


class AvailabilitySchemaTests(unittest.TestCase):
    def test_daily_window_round_trip(self) -> None:
        window = DailyWindow(start="9:00", end="17:00")
        self.assertEqual(window.start, "09:00")
        self.assertEqual(window.end, "17:00")

    def test_daily_window_rejects_invalid_order(self) -> None:
        with self.assertRaises(ValidationError):
            DailyWindow(start="18:00", end="09:00")

    def test_daily_window_rejects_invalid_format(self) -> None:
        with self.assertRaises(ValidationError):
            DailyWindow(start="not-a-time", end="10:00")

    def test_weekly_hours_default_empty(self) -> None:
        hours = WeeklyHoursPayload()
        self.assertEqual(hours.mon, [])
        self.assertEqual(hours.sun, [])

    def test_rule_upsert_serializes(self) -> None:
        payload = AvailabilityRuleUpsert(
            timezone="America/New_York",
            weekly_hours={
                "mon": [{"start": "09:00", "end": "17:00"}],
                "tue": [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],
            },
        )
        dumped = payload.weekly_hours.model_dump()
        self.assertEqual(len(dumped["mon"]), 1)
        self.assertEqual(len(dumped["tue"]), 2)
        self.assertEqual(dumped["wed"], [])

    def test_block_create_validates_order(self) -> None:
        now = datetime.now(timezone.utc)
        AvailabilityBlockCreate(start_at=now, end_at=now + timedelta(hours=2))
        with self.assertRaises(ValidationError):
            AvailabilityBlockCreate(start_at=now + timedelta(hours=2), end_at=now)


if __name__ == "__main__":
    unittest.main()
