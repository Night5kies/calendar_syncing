from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.meeting_request import MeetingRequest
from app.models.participant import Participant
from app.models.profile import Profile
from app.services.notifications import send_notification


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)[:48]


def build_invite_url(event_id: uuid.UUID | str, invite_token: str | None) -> str:
    base = f"{settings.app_base_url}/events/{event_id}/respond"
    if invite_token:
        return f"{base}?token={invite_token}"
    return base


class ParticipantResolutionError(Exception):
    """Raised when a response cannot be attributed to any participant."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ResolvedParticipant:
    participant: Participant
    requires_email_link: bool = False


def _find_by_user(db: Session, event_id: uuid.UUID, user_id: uuid.UUID) -> Participant | None:
    return db.execute(
        select(Participant).where(
            Participant.meeting_request_id == event_id,
            Participant.user_id == user_id,
        )
    ).scalar_one_or_none()


def _find_by_email(db: Session, event_id: uuid.UUID, email: str) -> Participant | None:
    return db.execute(
        select(Participant).where(
            Participant.meeting_request_id == event_id,
            func.lower(Participant.email) == email,
        )
    ).scalar_one_or_none()


def _find_by_invite_token(db: Session, event_id: uuid.UUID, invite_token: str) -> Participant | None:
    return db.execute(
        select(Participant).where(
            Participant.meeting_request_id == event_id,
            Participant.invite_token == invite_token,
        )
    ).scalar_one_or_none()


def _profile_by_email(db: Session, email: str) -> Profile | None:
    return db.execute(
        select(Profile).where(func.lower(Profile.email) == email)
    ).scalar_one_or_none()


def _contact_key_for(email: str | None, phone: str | None, fallback: str) -> str:
    if email:
        return f"email:{email}"
    if phone:
        return f"phone:{phone}"
    return f"guest:{fallback}"


def resolve_participant(
    db: Session,
    *,
    event_id: uuid.UUID,
    current_user_id: uuid.UUID | None = None,
    current_user_email: str | None = None,
    current_user_name: str | None = None,
    current_user_email_verified_at: datetime | None = None,
    invite_token: str | None = None,
    submitted_name: str | None = None,
    submitted_email: str | None = None,
    submitted_phone: str | None = None,
    came_from_general_link: bool = False,
) -> ResolvedParticipant:
    """Resolve the EventParticipant a response should be attributed to.

    Order of resolution:
    1. logged-in user (current_user_id)
    2. invite token
    3. email (general link)

    Never matches on display name. Raises ParticipantResolutionError if no
    identity can be established.
    """

    # 1. Logged-in user
    if current_user_id is not None:
        by_user = _find_by_user(db, event_id, current_user_id)
        if by_user is not None:
            return ResolvedParticipant(participant=by_user)

        normalized = normalize_email(current_user_email)
        if normalized:
            by_email = _find_by_email(db, event_id, normalized)
            if by_email is not None:
                by_email.user_id = current_user_id
                if current_user_email_verified_at is not None:
                    by_email.email_verified_at = (
                        by_email.email_verified_at or current_user_email_verified_at
                    )
                if current_user_name and not by_email.display_name:
                    by_email.display_name = current_user_name
                db.flush()
                return ResolvedParticipant(participant=by_email)

        # Logged-in user with no existing participant: create one.
        participant = Participant(
            meeting_request_id=event_id,
            user_id=current_user_id,
            email=normalized,
            display_name=current_user_name or submitted_name,
            role="attendee",
            source="public_link",
            status="responded",
            email_verified_at=current_user_email_verified_at,
            contact_key=_contact_key_for(normalized, None, str(current_user_id)),
            invite_token=generate_invite_token(),
        )
        db.add(participant)
        db.flush()
        return ResolvedParticipant(participant=participant)

    # 2. Invite token
    if invite_token:
        by_token = _find_by_invite_token(db, event_id, invite_token)
        if by_token is not None:
            return ResolvedParticipant(participant=by_token)
        # Spec: fall through if invalid token.

    # 3. General link with email
    normalized_email = normalize_email(submitted_email)
    if not normalized_email:
        raise ParticipantResolutionError(
            code="email_required",
            message="Email is required to respond.",
        )

    by_email = _find_by_email(db, event_id, normalized_email)
    if by_email is not None:
        if came_from_general_link and by_email.source == "invited" and by_email.status != "responded":
            # Don't overwrite an invited participant from the public form.
            # The caller should send a magic-respond link to the invited email
            # so the real invitee can claim the response.
            return ResolvedParticipant(participant=by_email, requires_email_link=True)
        return ResolvedParticipant(participant=by_email)

    # Link to an existing user account when the submitted email matches one.
    profile = _profile_by_email(db, normalized_email)
    user_id_for_new = profile.id if profile is not None else None
    verified_at = profile.email_verified_at if profile is not None else None

    participant = Participant(
        meeting_request_id=event_id,
        user_id=user_id_for_new,
        email=normalized_email,
        phone=submitted_phone.strip() if submitted_phone else None,
        display_name=(submitted_name or "").strip() or None,
        role="attendee",
        source="public_link",
        status="invited",  # caller will flip to "responded" after saving the response
        email_verified_at=verified_at,
        contact_key=_contact_key_for(normalized_email, submitted_phone, normalized_email),
        invite_token=generate_invite_token(),
    )
    db.add(participant)
    db.flush()
    return ResolvedParticipant(participant=participant)


def send_magic_respond_link(
    db: Session,
    *,
    participant: Participant,
    request: MeetingRequest,
) -> dict[str, Any]:
    """Email the participant their personal respond URL.

    Used when a general-link responder enters an email that matches an
    invited participant — we never overwrite from the public form; instead
    we send the invited participant their own scoped link.

    Returns a status dict the API can echo to the caller.
    """
    if not participant.email:
        raise ParticipantResolutionError(
            code="participant_has_no_email",
            message="Cannot send a respond link because the invited participant has no email.",
        )
    if not participant.invite_token:
        participant.invite_token = generate_invite_token()
        db.flush()

    url = build_invite_url(participant.meeting_request_id, participant.invite_token)
    subject = f"Your private response link for {request.title}"
    body = (
        f"Hi {participant.display_name or 'there'},\n\n"
        f"Someone just tried to respond to \"{request.title}\" using your email. "
        f"If that was you, use the private link below to record your response:\n\n"
        f"{url}\n\n"
        f"If it wasn't you, you can ignore this email."
    )
    result = send_notification(
        channel="email",
        target=participant.email,
        subject=subject,
        body=body,
        metadata={
            "meeting_request_id": str(participant.meeting_request_id),
            "participant_id": str(participant.id),
            "kind": "magic_respond_link",
        },
    )
    return {
        "status": "check_email",
        "message": (
            "Looks like this email was invited. We sent a private link to that "
            "email so you can respond from there."
        ),
        "delivery_status": result.status,
    }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
