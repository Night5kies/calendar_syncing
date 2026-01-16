import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.schemas.proposal_response import ProposalResponseCreate
from app.services.meeting_requests import compute_end_at, next_status_on_response, scheduled_event_snapshot


class MeetingRequestTests(unittest.TestCase):
    def test_status_transitions(self) -> None:
        self.assertEqual(next_status_on_response("sent", "picked"), "collecting")
        self.assertEqual(next_status_on_response("collecting", "maybe"), "needs_organizer_confirm")
        self.assertEqual(next_status_on_response("confirmed", "declined"), "confirmed")

    def test_proposal_response_constraints(self) -> None:
        participant_id = uuid.uuid4()
        proposal_id = uuid.uuid4()
        ProposalResponseCreate(participant_id=participant_id, proposal_id=proposal_id, choice="picked")
        with self.assertRaises(ValueError):
            ProposalResponseCreate(participant_id=participant_id, proposal_id=None, choice="picked")
        with self.assertRaises(ValueError):
            ProposalResponseCreate(participant_id=participant_id, proposal_id=proposal_id, choice="declined")

    def test_scheduled_event_snapshot(self) -> None:
        start_at = datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc)
        meeting_request = SimpleNamespace(
            title="Team Sync",
            timezone="America/New_York",
            duration_min=30,
            event_type="meeting",
            location="Room 1",
            video_link=None,
            notes="Bring notes",
        )
        proposal = SimpleNamespace(start_at=start_at)
        snapshot = scheduled_event_snapshot(meeting_request, proposal)
        self.assertEqual(snapshot["title"], "Team Sync")
        self.assertEqual(snapshot["timezone"], "America/New_York")
        self.assertEqual(snapshot["start_at"], start_at)
        self.assertEqual(snapshot["duration_min"], 30)
        self.assertEqual(snapshot["event_type"], "meeting")
        self.assertEqual(snapshot["location"], "Room 1")
        self.assertIsNone(snapshot["video_link"])
        self.assertEqual(snapshot["notes"], "Bring notes")

    def test_compute_end_at(self) -> None:
        start_at = datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc)
        end_at = compute_end_at(start_at, 45)
        self.assertEqual(end_at, datetime(2026, 1, 6, 12, 45, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
