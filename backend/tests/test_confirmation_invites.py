import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.confirmation_invites import _build_email_body, _format_local


class ConfirmationInviteCopyTests(unittest.TestCase):
    def test_body_includes_title_time_and_links(self) -> None:
        request = SimpleNamespace(
            id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            title="Team Dinner",
            timezone="America/New_York",
        )
        scheduled = SimpleNamespace(
            start_at=datetime(2026, 6, 1, 18, 30, tzinfo=timezone.utc),
            duration_min=75,
            timezone="America/New_York",
            location="Joe's",
            video_link="https://meet.example/abc",
            notes="Reservation under SYZY",
        )
        participant = SimpleNamespace(display_name="Alex", email="alex@example.com")

        body = _build_email_body(request, scheduled, participant)
        self.assertIn("Hi Alex", body)
        self.assertIn("Team Dinner", body)
        self.assertIn("Joe's", body)
        self.assertIn("https://meet.example/abc", body)
        self.assertIn("artifact.ics", body)
        self.assertIn("Reservation under SYZY", body)
        self.assertIn("America/New_York", body)

    def test_body_handles_missing_optional_fields(self) -> None:
        request = SimpleNamespace(
            id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            title="Coffee",
            timezone="UTC",
        )
        scheduled = SimpleNamespace(
            start_at=datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc),
            duration_min=30,
            timezone="UTC",
            location=None,
            video_link=None,
            notes=None,
        )
        participant = SimpleNamespace(display_name=None, email="x@example.com")

        body = _build_email_body(request, scheduled, participant)
        self.assertIn("Hi there", body)
        self.assertNotIn("Location:", body)
        self.assertNotIn("Video link:", body)

    def test_format_local_returns_string(self) -> None:
        start = datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc)
        text = _format_local(start, "America/New_York")
        self.assertIn(",", text)
        self.assertTrue(text)


if __name__ == "__main__":
    unittest.main()
