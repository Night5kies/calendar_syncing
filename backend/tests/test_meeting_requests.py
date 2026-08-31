import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.services.confirmation_artifacts import artifact_filename, build_ics_body, ensure_artifact_dir
from app.schemas.proposal_response import ProposalResponseCreate
from app.services.meeting_requests import (
    DEFAULT_FOLLOWUP_REMINDER_HOURS,
    DEFAULT_INITIAL_REMINDER_HOURS,
    MAX_MANUAL_PROPOSALS,
    MAX_REMINDERS_PER_PARTICIPANT,
    build_reminder_copy,
    can_edit_proposals,
    compute_end_at,
    next_status_on_response,
    reminder_target_for_participant,
    resolve_reminder_policy,
    scheduled_event_snapshot,
    validate_manual_proposal_rules,
)


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

    def test_reminder_helpers(self) -> None:
        meeting_request = SimpleNamespace(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            title="Dinner",
            response_deadline=datetime(2026, 1, 7, 1, 0, tzinfo=timezone.utc),
        )
        participant = SimpleNamespace(
            display_name="Alex",
            email="alex@example.com",
            phone=None,
            invite_token="abc123",
        )
        self.assertEqual(reminder_target_for_participant(participant), ("email", "alex@example.com"))
        message = build_reminder_copy(meeting_request, participant, "deadline")
        self.assertIn("Dinner", message)
        self.assertIn("Final reminder.", message)
        self.assertIn("/events/11111111-1111-1111-1111-111111111111/respond?token=abc123", message)

    def test_confirmation_artifact_helpers(self) -> None:
        ics = build_ics_body(
            uid="event-1@syzy",
            title="Dinner",
            start_at_utc="20260106T120000Z",
            end_at_utc="20260106T130000Z",
            description="Bring notes",
            location="Cafe",
            organizer_email="organizer@example.com",
        )
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("SUMMARY:Dinner", ics)
        self.assertIn("LOCATION:Cafe", ics)
        self.assertTrue(artifact_filename("Dinner Plan", "abc").endswith(".ics"))

        with TemporaryDirectory() as temp_dir:
            ensured = ensure_artifact_dir(temp_dir)
            self.assertTrue(Path(ensured).exists())

    def test_resolve_reminder_policy_uses_defaults(self) -> None:
        req = SimpleNamespace(reminder_policy=None)
        policy = resolve_reminder_policy(req)
        self.assertEqual(policy["initial_hours"], DEFAULT_INITIAL_REMINDER_HOURS)
        self.assertEqual(policy["followup_hours"], DEFAULT_FOLLOWUP_REMINDER_HOURS)
        self.assertEqual(policy["max_per_participant"], MAX_REMINDERS_PER_PARTICIPANT)

    def test_resolve_reminder_policy_honors_overrides(self) -> None:
        req = SimpleNamespace(
            reminder_policy={"initial_hours": 4, "followup_hours": 8, "max_per_participant": 5}
        )
        policy = resolve_reminder_policy(req)
        self.assertEqual(policy["initial_hours"], 4)
        self.assertEqual(policy["followup_hours"], 8)
        self.assertEqual(policy["max_per_participant"], 5)

    def test_resolve_reminder_policy_falls_back_on_invalid(self) -> None:
        req = SimpleNamespace(
            reminder_policy={"initial_hours": -3, "max_per_participant": 0}
        )
        policy = resolve_reminder_policy(req)
        self.assertEqual(policy["initial_hours"], DEFAULT_INITIAL_REMINDER_HOURS)
        self.assertEqual(policy["max_per_participant"], MAX_REMINDERS_PER_PARTICIPANT)

    def test_manual_proposal_rules(self) -> None:
        self.assertTrue(can_edit_proposals("draft"))
        self.assertFalse(can_edit_proposals("sent"))
        validate_manual_proposal_rules("draft", MAX_MANUAL_PROPOSALS - 1)
        with self.assertRaises(ValueError):
            validate_manual_proposal_rules("sent", 0)
        with self.assertRaises(ValueError):
            validate_manual_proposal_rules("draft", MAX_MANUAL_PROPOSALS)

    def test_confirmed_event_payload_shape(self) -> None:
        from app.api.v1.events import _confirmed_event_payload

        req = SimpleNamespace(id=uuid.UUID("22222222-2222-2222-2222-222222222222"))
        self.assertIsNone(_confirmed_event_payload(req, None))

        start_at = datetime(2026, 1, 6, 23, 0, tzinfo=timezone.utc)
        scheduled = SimpleNamespace(
            id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            proposal_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
            title="Dinner",
            timezone="America/New_York",
            start_at=start_at,
            duration_min=75,
            location="Joe's",
            video_link=None,
            notes=None,
            artifact_path="/tmp/dinner.ics",
        )
        payload = _confirmed_event_payload(req, scheduled)
        assert payload is not None
        self.assertEqual(payload["id"], str(scheduled.id))
        self.assertEqual(payload["proposal_id"], str(scheduled.proposal_id))
        self.assertEqual(payload["timezone"], "America/New_York")
        self.assertEqual(payload["duration_min"], 75)
        self.assertEqual(payload["location"], "Joe's")
        self.assertEqual(payload["start_at"], start_at.isoformat())
        self.assertEqual(payload["end_at"], compute_end_at(start_at, 75).isoformat())
        self.assertTrue(payload["artifact_url"].endswith(f"/v1/events/{req.id}/artifact.ics"))

        scheduled_no_artifact = SimpleNamespace(
            id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
            proposal_id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
            title="Coffee",
            timezone="UTC",
            start_at=start_at,
            duration_min=30,
            location=None,
            video_link=None,
            notes=None,
            artifact_path=None,
        )
        payload_no_artifact = _confirmed_event_payload(req, scheduled_no_artifact)
        assert payload_no_artifact is not None
        self.assertIsNone(payload_no_artifact["artifact_url"])


if __name__ == "__main__":
    unittest.main()
