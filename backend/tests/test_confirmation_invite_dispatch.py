"""DB-backed coverage for dispatch_confirmation_invites transaction handling."""
import unittest
import uuid
from datetime import datetime, timezone
from unittest import mock

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.meeting_request import MeetingRequest
from app.models.notification_event import NotificationEvent
from app.models.participant import Participant
from app.models.profile import Profile
from app.models.proposal import Proposal
from app.models.scheduled_event import ScheduledEvent
from app.services import confirmation_invites as service
from app.services.confirmation_invites import INVITE_KIND, dispatch_confirmation_invites


class DispatchTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        try:
            self.db.connection()
        except OperationalError as exc:
            self.db.close()
            self.skipTest(f"Postgres not reachable for db-backed test: {exc}")

        self.user_id = uuid.uuid4()
        self.db.add(Profile(id=self.user_id, email=f"org-{self.user_id}@example.com"))
        self.request = MeetingRequest(
            organizer_id=self.user_id,
            title="Dinner",
            duration_min=60,
            timezone="UTC",
            status="confirmed",
        )
        self.db.add(self.request)
        self.db.flush()

        proposal = Proposal(
            meeting_request_id=self.request.id,
            rank=1,
            start_at=datetime(2026, 6, 1, 18, tzinfo=timezone.utc),
        )
        self.db.add(proposal)
        self.db.flush()

        for name, email in (("Alex", "alex@example.com"), ("Sam", "sam@example.com")):
            self.db.add(
                Participant(
                    meeting_request_id=self.request.id,
                    display_name=name,
                    email=email,
                    contact_key=email,
                    status="invited",
                )
            )
        self.scheduled = ScheduledEvent(
            meeting_request_id=self.request.id,
            proposal_id=proposal.id,
            title="Dinner",
            timezone="UTC",
            start_at=proposal.start_at,
            duration_min=60,
            status="confirmed",
        )
        self.db.add(self.scheduled)
        self.db.flush()

    def tearDown(self) -> None:
        if getattr(self, "db", None) is None:
            return
        self.db.rollback()
        self.db.close()

    def _logged_kinds(self) -> list[str]:
        return list(
            self.db.execute(
                select(NotificationEvent.kind).where(
                    NotificationEvent.scheduled_event_id == self.scheduled.id
                )
            )
            .scalars()
            .all()
        )

    def test_sends_to_every_participant_with_an_email(self) -> None:
        result = dispatch_confirmation_invites(
            self.db, scheduled_event_id=self.scheduled.id
        )
        self.assertEqual(result["sent_count"], 2)
        self.assertEqual(result["skipped_count"], 0)
        self.assertEqual(len(self._logged_kinds()), 2)

    def test_duplicate_invite_does_not_unwind_the_transaction(self) -> None:
        """A re-dispatch must skip the duplicate, not roll back the confirmation.

        The unique constraint on (scheduled_event, participant, kind) fires on
        the second run. A plain db.rollback() there discarded the caller's whole
        uncommitted transaction -- the ScheduledEvent row and the request's move
        to "confirmed" included -- while still returning success.
        """
        dispatch_confirmation_invites(self.db, scheduled_event_id=self.scheduled.id)

        result = dispatch_confirmation_invites(
            self.db, scheduled_event_id=self.scheduled.id
        )
        self.assertEqual(result["sent_count"], 0)
        self.assertEqual(result["skipped_count"], 2)

        # The work that existed before the duplicate must still be in the session.
        self.assertIsNotNone(self.db.get(ScheduledEvent, self.scheduled.id))
        self.assertEqual(self.db.get(MeetingRequest, self.request.id).status, "confirmed")
        self.assertEqual(len(self._logged_kinds()), 2)

    def test_participants_without_an_email_are_skipped(self) -> None:
        self.db.add(
            Participant(
                meeting_request_id=self.request.id,
                display_name="Phone Only",
                phone="+15555550123",
                contact_key="+15555550123",
                status="invited",
            )
        )
        self.db.flush()

        result = dispatch_confirmation_invites(
            self.db, scheduled_event_id=self.scheduled.id
        )
        self.assertEqual(result["sent_count"], 2)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["participant_count"], 3)

    def test_failed_delivery_is_counted_separately(self) -> None:
        from app.services.notifications import DeliveryResult

        with mock.patch.object(
            service,
            "send_notification",
            return_value=DeliveryResult(status="failed", detail="smtp down"),
        ):
            result = dispatch_confirmation_invites(
                self.db, scheduled_event_id=self.scheduled.id
            )
        # A failed send used to be reported as sent.
        self.assertEqual(result["sent_count"], 0)
        self.assertEqual(result["failed_count"], 2)

    def test_mime_method_matches_the_ics_body(self) -> None:
        self.assertEqual(service._ics_method("BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\n"), "REQUEST")
        self.assertEqual(service._ics_method("BEGIN:VCALENDAR\r\nMETHOD:PUBLISH\r\n"), "PUBLISH")
        self.assertEqual(service._ics_method("BEGIN:VCALENDAR\r\n"), "PUBLISH")


if __name__ == "__main__":
    unittest.main()
