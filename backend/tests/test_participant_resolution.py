import unittest
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.meeting_request import MeetingRequest
from app.models.participant import Participant
from app.models.profile import Profile
from app.models.proposal import Proposal
from app.models.proposal_response import ProposalResponse
from app.services.participants import (
    ParticipantResolutionError,
    generate_invite_token,
    resolve_participant,
)


class ParticipantResolutionTests(unittest.TestCase):
    """Verifies the identity-resolution rules per WEBSITE_DEVELOPMENT_PLAN.md."""

    def setUp(self) -> None:
        self.db = SessionLocal()
        try:
            self.db.connection()
        except OperationalError as exc:
            self.db.close()
            self.skipTest(f"Postgres not reachable for db-backed test: {exc}")
        self.event = MeetingRequest(
            organizer_id=uuid.uuid4(),
            title="Test event",
            duration_min=60,
            timezone="America/New_York",
            status="sent",
        )
        self.db.add(self.event)
        self.db.flush()

    def tearDown(self) -> None:
        self.db.rollback()
        self.db.close()

    def _invite(self, email: str | None = None, phone: str | None = None, display_name: str | None = None) -> Participant:
        token = generate_invite_token()
        participant = Participant(
            meeting_request_id=self.event.id,
            email=email,
            phone=phone,
            display_name=display_name,
            role="attendee",
            status="invited",
            source="invited",
            invite_token=token,
            contact_key=(f"email:{email}" if email else f"phone:{phone}" if phone else f"guest:{token}"),
        )
        self.db.add(participant)
        self.db.flush()
        return participant

    def test_invite_token_returns_existing_participant(self) -> None:
        invited = self._invite(email="alex@example.com", display_name="Alex")
        resolved = resolve_participant(
            self.db,
            event_id=self.event.id,
            invite_token=invited.invite_token,
            submitted_name="Alex Smith",
            submitted_email=None,
        )
        self.assertFalse(resolved.requires_email_link)
        self.assertEqual(resolved.participant.id, invited.id)

    def test_public_response_with_new_email_creates_participant(self) -> None:
        resolved = resolve_participant(
            self.db,
            event_id=self.event.id,
            submitted_name="Stranger",
            submitted_email="stranger@example.com",
            came_from_general_link=True,
        )
        self.assertFalse(resolved.requires_email_link)
        self.assertEqual(resolved.participant.email, "stranger@example.com")
        self.assertEqual(resolved.participant.source, "public_link")
        self.assertIsNotNone(resolved.participant.invite_token)

    def test_public_response_with_invited_email_triggers_check_email(self) -> None:
        invited = self._invite(email="alex@example.com", display_name="Alex")
        resolved = resolve_participant(
            self.db,
            event_id=self.event.id,
            submitted_name="Imposter",
            submitted_email="ALEX@example.com",  # different case to confirm normalization
            came_from_general_link=True,
        )
        self.assertTrue(resolved.requires_email_link)
        self.assertEqual(resolved.participant.id, invited.id)

    def test_logged_in_user_links_existing_invited_participant_by_email(self) -> None:
        invited = self._invite(email="alex@example.com", display_name="Alex")
        self.assertIsNone(invited.user_id)

        user_id = uuid.uuid4()
        profile = Profile(
            id=user_id,
            display_name="Alex via Account",
            email="alex@example.com",
        )
        self.db.add(profile)
        self.db.flush()

        resolved = resolve_participant(
            self.db,
            event_id=self.event.id,
            current_user_id=user_id,
            current_user_email="alex@example.com",
            current_user_name="Alex via Account",
            submitted_name=None,
            submitted_email=None,
        )
        self.assertFalse(resolved.requires_email_link)
        self.assertEqual(resolved.participant.id, invited.id)
        self.assertEqual(resolved.participant.user_id, user_id)

    def test_duplicate_response_upserts_by_participant_id(self) -> None:
        invited = self._invite(email="alex@example.com", display_name="Alex")
        proposal = Proposal(
            meeting_request_id=self.event.id,
            rank=1,
            start_at=datetime.now(timezone.utc) + timedelta(days=2),
        )
        self.db.add(proposal)
        self.db.flush()

        for choice in ("maybe", "picked"):
            resolved = resolve_participant(
                self.db,
                event_id=self.event.id,
                invite_token=invited.invite_token,
                submitted_name="Alex",
                submitted_email="alex@example.com",
            )
            existing = self.db.execute(
                select(ProposalResponse).where(
                    ProposalResponse.meeting_request_id == self.event.id,
                    ProposalResponse.participant_id == resolved.participant.id,
                )
            ).scalar_one_or_none()
            if existing:
                existing.choice = choice
                existing.proposal_id = proposal.id
            else:
                self.db.add(
                    ProposalResponse(
                        meeting_request_id=self.event.id,
                        participant_id=resolved.participant.id,
                        proposal_id=proposal.id,
                        choice=choice,
                    )
                )
            self.db.flush()

        responses = self.db.execute(
            select(ProposalResponse).where(
                ProposalResponse.meeting_request_id == self.event.id,
                ProposalResponse.participant_id == invited.id,
            )
        ).scalars().all()
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].choice, "picked")

    def test_general_link_without_email_raises(self) -> None:
        with self.assertRaises(ParticipantResolutionError) as ctx:
            resolve_participant(
                self.db,
                event_id=self.event.id,
                submitted_name="Nameless",
                submitted_email=None,
                came_from_general_link=True,
            )
        self.assertEqual(ctx.exception.code, "email_required")


if __name__ == "__main__":
    unittest.main()
