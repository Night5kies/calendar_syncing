"""Coverage for the Google write-back path used by POST /requests/{id}/finalize."""
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.calendar_connection import CalendarConnection
from app.models.meeting_request import MeetingRequest
from app.models.participant import Participant
from app.models.profile import Profile
from app.models.proposal import Proposal
from app.models.provider_calendar import ProviderCalendar
from app.models.scheduled_event import ScheduledEvent
from app.services import scheduled_events as service


class WriteBackPayloadTests(unittest.TestCase):
    """Pure payload construction -- no database required."""

    def _scheduled(self) -> SimpleNamespace:
        return SimpleNamespace(
            title="Team Dinner",
            notes="Bring the deck",
            location="Joe's",
            timezone="America/New_York",
            start_at=datetime(2026, 6, 1, 18, 30, tzinfo=timezone.utc),
            duration_min=60,
        )

    def test_attendees_are_omitted_by_default(self) -> None:
        # Attendees already receive the SYZY email + ICS; inviting them through
        # Google as well would double-notify them.
        payload = service.build_google_event_payload(
            self._scheduled(), "uid@syzy", ["guest@example.com"]
        )
        self.assertNotIn("attendees", payload)
        self.assertNotIn("guestsCanModify", payload)

    def test_attendees_are_included_when_enabled(self) -> None:
        with mock.patch.object(settings, "google_invite_attendees", True):
            payload = service.build_google_event_payload(
                self._scheduled(), "uid@syzy", ["guest@example.com"]
            )
        self.assertEqual(payload["attendees"], [{"email": "guest@example.com"}])
        self.assertFalse(payload["guestsCanModify"])

    def test_uid_and_sequence_are_carried_in_extended_properties(self) -> None:
        payload = service.build_google_event_payload(self._scheduled(), "uid@syzy", None, 2)
        private = payload["extendedProperties"]["private"]
        self.assertEqual(private["syzy_uid"], "uid@syzy")
        self.assertEqual(private["syzy_sequence"], "2")


class WriteBackIdempotencyTests(unittest.TestCase):
    def _scheduled(self, **overrides) -> SimpleNamespace:
        base = dict(
            title="Coffee",
            notes=None,
            location=None,
            timezone="UTC",
            start_at=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
            duration_min=30,
            provider=None,
            provider_event_id=None,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_first_write_creates(self) -> None:
        with mock.patch.object(
            service.google, "create_event", return_value={"id": "evt-1"}
        ) as create, mock.patch.object(service.google, "update_event") as update:
            result = service.write_google_calendar_event(
                SimpleNamespace(), "primary", self._scheduled(), "uid@syzy", None
            )
        self.assertEqual(result["id"], "evt-1")
        create.assert_called_once()
        update.assert_not_called()

    def test_refinalize_updates_instead_of_duplicating(self) -> None:
        scheduled = self._scheduled(provider="google", provider_event_id="evt-1")
        with mock.patch.object(
            service.google, "get_event", return_value={"id": "evt-1"}
        ), mock.patch.object(
            service.google, "update_event", return_value={"id": "evt-1"}
        ) as update, mock.patch.object(
            service.google, "create_event"
        ) as create:
            service.write_google_calendar_event(
                SimpleNamespace(), "primary", scheduled, "uid@syzy", None
            )
        update.assert_called_once()
        create.assert_not_called()

    def test_recreates_when_the_event_was_deleted_upstream(self) -> None:
        scheduled = self._scheduled(provider="google", provider_event_id="evt-gone")
        with mock.patch.object(
            service.google, "get_event", return_value=None
        ), mock.patch.object(
            service.google, "create_event", return_value={"id": "evt-2"}
        ) as create, mock.patch.object(service.google, "update_event") as update:
            result = service.write_google_calendar_event(
                SimpleNamespace(), "primary", scheduled, "uid@syzy", None
            )
        self.assertEqual(result["id"], "evt-2")
        create.assert_called_once()
        update.assert_not_called()


class CalendarSelectionTests(unittest.TestCase):
    """DB-backed: multiple enabled calendars must not raise MultipleResultsFound."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        try:
            self.db.connection()
        except OperationalError as exc:
            self.db.close()
            self.skipTest(f"Postgres not reachable for db-backed test: {exc}")

        self.user_id = uuid.uuid4()
        self.db.add(
            Profile(id=self.user_id, email=f"organizer-{self.user_id}@example.com")
        )
        self.db.flush()

    def tearDown(self) -> None:
        if getattr(self, "db", None) is None:
            return
        self.db.rollback()
        self.db.close()

    def _add_calendar(self, calendar_id: str, *, primary: bool, enabled: bool = True) -> None:
        self.db.add(
            ProviderCalendar(
                user_id=self.user_id,
                provider="google",
                provider_calendar_id=calendar_id,
                name=calendar_id,
                is_primary=primary,
                is_enabled=enabled,
                updated_at=datetime.now(timezone.utc),
            )
        )
        self.db.flush()

    def test_picks_primary_out_of_several_enabled_calendars(self) -> None:
        # A stock Google account has primary + Holidays + Birthdays all enabled;
        # the strict scalar_one_or_none() here used to 500 the whole finalize.
        self._add_calendar("holidays@group.calendar.google.com", primary=False)
        self._add_calendar("me@example.com", primary=True)
        self._add_calendar("birthdays@group.calendar.google.com", primary=False)

        chosen = service.choose_google_calendar_id(self.db, self.user_id)
        self.assertEqual(chosen, "me@example.com")

    def test_falls_back_to_primary_alias_without_calendars(self) -> None:
        self.assertEqual(service.choose_google_calendar_id(self.db, self.user_id), "primary")

    def test_ignores_disabled_calendars(self) -> None:
        self._add_calendar("hidden@example.com", primary=True, enabled=False)
        self._add_calendar("team@example.com", primary=False, enabled=True)
        self.assertEqual(
            service.choose_google_calendar_id(self.db, self.user_id), "team@example.com"
        )

    def test_picks_newest_connection_when_several_exist(self) -> None:
        older = CalendarConnection(
            user_id=self.user_id,
            provider="google",
            provider_account_id="acct-old",
            access_token="tok-old",
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        newer = CalendarConnection(
            user_id=self.user_id,
            provider="google",
            provider_account_id="acct-new",
            access_token="tok-new",
            created_at=datetime.now(timezone.utc),
        )
        self.db.add_all([older, newer])
        self.db.flush()

        connection = service.get_google_connection(self.db, self.user_id)
        self.assertIsNotNone(connection)
        self.assertEqual(connection.provider_account_id, "acct-new")

    def test_revoked_connections_are_ignored(self) -> None:
        self.db.add(
            CalendarConnection(
                user_id=self.user_id,
                provider="google",
                provider_account_id="acct-dead",
                access_token=None,
                revoked_at=datetime.now(timezone.utc),
            )
        )
        self.db.flush()
        self.assertIsNone(service.get_google_connection(self.db, self.user_id))

    def test_tokens_are_encrypted_at_rest(self) -> None:
        from sqlalchemy import text

        from app.core.crypto import ENCRYPTION_PREFIX

        key_present = bool(settings.token_encryption_key)
        connection = CalendarConnection(
            user_id=self.user_id,
            provider="google",
            provider_account_id="acct-enc",
            access_token="super-secret-token",
            refresh_token="super-secret-refresh",
        )
        self.db.add(connection)
        self.db.flush()

        raw = self.db.execute(
            text("SELECT access_token FROM calendar_connections WHERE id = :id"),
            {"id": connection.id},
        ).scalar_one()
        self.db.expire(connection)

        if key_present:
            self.assertTrue(raw.startswith(ENCRYPTION_PREFIX))
            self.assertNotIn("super-secret-token", raw)
        # Either way the ORM round-trips plaintext for application code.
        self.assertEqual(connection.access_token, "super-secret-token")


class FinalizeSequenceTests(unittest.TestCase):
    """DB-backed: re-finalizing bumps SEQUENCE and reuses the same UID."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        try:
            self.db.connection()
        except OperationalError as exc:
            self.db.close()
            self.skipTest(f"Postgres not reachable for db-backed test: {exc}")

        self.user_id = uuid.uuid4()
        self.db.add(Profile(id=self.user_id, email=f"org-{self.user_id}@example.com"))
        request = MeetingRequest(
            organizer_id=self.user_id,
            title="Finalize test",
            duration_min=30,
            timezone="UTC",
            status="confirmed",
        )
        self.db.add(request)
        self.db.flush()
        proposal = Proposal(
            meeting_request_id=request.id,
            rank=1,
            start_at=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
        )
        self.db.add(proposal)
        self.db.add(
            Participant(
                meeting_request_id=request.id,
                display_name="Alex",
                email="alex@example.com",
                contact_key="alex@example.com",
                status="invited",
            )
        )
        self.db.flush()
        self.scheduled = ScheduledEvent(
            meeting_request_id=request.id,
            proposal_id=proposal.id,
            title="Finalize test",
            timezone="UTC",
            start_at=proposal.start_at,
            duration_min=30,
            status="confirmed",
        )
        self.db.add(self.scheduled)
        self.db.flush()

    def tearDown(self) -> None:
        if getattr(self, "db", None) is None:
            return
        self.db.rollback()
        self.db.close()

    def test_sequence_increments_and_uid_is_stable(self) -> None:
        first = service.finalize_scheduled_event(
            self.db,
            scheduled_event=self.scheduled,
            organizer_email="organizer@example.com",
            organizer_id=self.user_id,
        )
        uid = self.scheduled.artifact_uid
        self.assertEqual(self.scheduled.artifact_sequence, 0)

        service.finalize_scheduled_event(
            self.db,
            scheduled_event=self.scheduled,
            organizer_email="organizer@example.com",
            organizer_id=self.user_id,
        )
        self.assertEqual(self.scheduled.artifact_uid, uid)
        self.assertEqual(self.scheduled.artifact_sequence, 1)

        body = open(first["artifact_path"], encoding="utf-8").read()
        self.assertIn("SEQUENCE:1", body)
        # The participant has an email, so the invite is a REQUEST with an ATTENDEE.
        self.assertIn("METHOD:REQUEST", body)

    def test_write_back_failure_keeps_the_existing_event_id(self) -> None:
        self.scheduled.provider = "google"
        self.scheduled.provider_event_id = "evt-existing"
        connection = CalendarConnection(
            user_id=self.user_id,
            provider="google",
            provider_account_id="acct",
            access_token="tok",
        )
        self.db.add(connection)
        self.db.flush()

        with mock.patch.object(
            service, "write_google_calendar_event", side_effect=RuntimeError("google down")
        ), mock.patch.object(service, "retry_call", side_effect=lambda fn: fn()):
            service.finalize_scheduled_event(
                self.db,
                scheduled_event=self.scheduled,
                organizer_email="organizer@example.com",
                organizer_id=self.user_id,
            )

        # Blanking these would orphan the event already sitting in the calendar.
        self.assertEqual(self.scheduled.provider, "google")
        self.assertEqual(self.scheduled.provider_event_id, "evt-existing")


if __name__ == "__main__":
    unittest.main()
