from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.calendar_connection import CalendarConnection
from app.models.participant import Participant
from app.models.provider_calendar import ProviderCalendar
from app.models.scheduled_event import ScheduledEvent
from app.providers import google
from app.services.confirmation_artifacts import artifact_filename, build_ics_body, ensure_artifact_dir
from app.services.meeting_requests import compute_end_at
from app.services.retry import retry_call

logger = logging.getLogger(__name__)


def finalize_scheduled_event(
    db: Session,
    *,
    scheduled_event: ScheduledEvent,
    organizer_email: str | None,
    organizer_id: Any,
) -> dict[str, str | None]:
    artifact_uid = scheduled_event.artifact_uid or f"{uuid.uuid4()}@syzy"
    # A re-finalize must look like an update to calendar clients, not a
    # duplicate, so the ICS SEQUENCE climbs every time we rewrite the file.
    sequence = (scheduled_event.artifact_sequence or 0) if scheduled_event.artifact_uid else 0
    if scheduled_event.artifact_uid:
        sequence += 1

    attendees = load_attendee_emails(db, scheduled_event)
    ics_path = write_ics_artifact(
        scheduled_event, artifact_uid, organizer_email, sequence, attendees
    )

    scheduled_event.artifact_uid = artifact_uid
    scheduled_event.artifact_path = str(ics_path)
    scheduled_event.artifact_sequence = sequence

    # Preserve any event we already created: a failed write-back must not blank
    # the id and orphan the event sitting in the organizer's calendar.
    provider = scheduled_event.provider
    provider_event_id = scheduled_event.provider_event_id

    connection = get_google_connection(db, organizer_id)
    if connection:
        calendar_id = choose_google_calendar_id(db, organizer_id)
        try:
            created = retry_call(
                lambda: write_google_calendar_event(
                    connection,
                    calendar_id,
                    scheduled_event,
                    artifact_uid,
                    organizer_email,
                    attendees,
                    sequence,
                )
            )
            if created.get("id"):
                provider = "google"
                provider_event_id = created["id"]
        except Exception:
            # Write-back is best-effort: the ICS artifact already exists and
            # the event is confirmed regardless. Log loudly so the failure is
            # not silent (organizer's calendar simply won't have the event).
            logger.warning(
                "Google Calendar write-back failed for scheduled_event %s after retries",
                scheduled_event.id,
                exc_info=True,
            )

    scheduled_event.provider = provider
    scheduled_event.provider_event_id = provider_event_id
    return {
        "artifact_path": str(ics_path),
        "provider": provider,
        "provider_event_id": provider_event_id,
    }


def load_attendee_emails(db: Session, scheduled_event: ScheduledEvent) -> list[str]:
    rows = (
        db.execute(
            select(Participant.email).where(
                Participant.meeting_request_id == scheduled_event.meeting_request_id
            )
        )
        .scalars()
        .all()
    )
    seen: list[str] = []
    for email in rows:
        if email and email not in seen:
            seen.append(email)
    return seen


def write_ics_artifact(
    scheduled_event: ScheduledEvent,
    artifact_uid: str,
    organizer_email: str | None,
    sequence: int = 0,
    attendees: list[str] | None = None,
) -> Path:
    start_at_utc = scheduled_event.start_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end_at_utc = compute_end_at(scheduled_event.start_at, scheduled_event.duration_min).astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    description_parts = [part for part in [scheduled_event.notes, scheduled_event.video_link] if part]
    ics = build_ics_body(
        uid=artifact_uid,
        title=scheduled_event.title,
        start_at_utc=start_at_utc,
        end_at_utc=end_at_utc,
        description="\n".join(description_parts) if description_parts else None,
        location=scheduled_event.location,
        organizer_email=organizer_email,
        attendees=attendees,
        sequence=sequence,
        dtstamp_utc=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    artifact_dir = ensure_artifact_dir("artifacts")
    file_path = artifact_dir / artifact_filename(scheduled_event.title, str(scheduled_event.meeting_request_id))
    file_path.write_text(ics, encoding="utf-8")
    return file_path


def get_google_connection(db: Session, organizer_id: Any) -> CalendarConnection | None:
    """Most recent live Google connection for the organizer.

    `.first()` rather than `.scalar_one_or_none()`: a user is allowed more than
    one Google connection row, and the strict variant raised
    MultipleResultsFound instead of picking the newest.
    """
    return (
        db.execute(
            select(CalendarConnection)
            .where(CalendarConnection.user_id == organizer_id)
            .where(CalendarConnection.provider == "google")
            .where(CalendarConnection.revoked_at.is_(None))
            .order_by(CalendarConnection.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def choose_google_calendar_id(db: Session, organizer_id: Any) -> str:
    """Pick the calendar to write the confirmed event into.

    Prefers the primary calendar, then the most recently updated enabled one,
    and falls back to Google's "primary" alias. Any account with more than one
    enabled calendar -- which is the common case -- used to raise
    MultipleResultsFound here and 500 the whole finalize.
    """
    calendar = (
        db.execute(
            select(ProviderCalendar)
            .where(ProviderCalendar.user_id == organizer_id)
            .where(ProviderCalendar.provider == "google")
            .where(ProviderCalendar.is_enabled.is_(True))
            .order_by(ProviderCalendar.is_primary.desc(), ProviderCalendar.updated_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return calendar.provider_calendar_id if calendar else "primary"


def build_google_event_payload(
    scheduled_event: ScheduledEvent,
    artifact_uid: str,
    attendees: list[str] | None = None,
    sequence: int = 0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "summary": scheduled_event.title,
        "description": scheduled_event.notes or "",
        "location": scheduled_event.location,
        "start": {
            "dateTime": scheduled_event.start_at.isoformat(),
            "timeZone": scheduled_event.timezone,
        },
        "end": {
            "dateTime": compute_end_at(scheduled_event.start_at, scheduled_event.duration_min).isoformat(),
            "timeZone": scheduled_event.timezone,
        },
        "source": {"title": "SYZY", "url": settings.app_base_url},
        "extendedProperties": {
            "private": {"syzy_uid": artifact_uid, "syzy_sequence": str(sequence)}
        },
    }
    # Off by default: attendees already get the SYZY confirmation email with an
    # ICS attachment, so inviting them here too would double-notify them.
    if settings.google_invite_attendees and attendees:
        payload["attendees"] = [{"email": email} for email in attendees]
        payload["guestsCanModify"] = False
    return payload


def write_google_calendar_event(
    connection: CalendarConnection,
    calendar_id: str,
    scheduled_event: ScheduledEvent,
    artifact_uid: str,
    organizer_email: str | None,
    attendees: list[str] | None = None,
    sequence: int = 0,
) -> dict[str, Any]:
    """Create the event, or overwrite the one a previous finalize created.

    Without the update branch, re-confirming left a duplicate event behind in
    the organizer's calendar.
    """
    payload = build_google_event_payload(scheduled_event, artifact_uid, attendees, sequence)
    existing_id = scheduled_event.provider_event_id
    if existing_id and scheduled_event.provider == "google":
        if google.get_event(connection, calendar_id, existing_id) is not None:
            return google.update_event(connection, calendar_id, existing_id, payload)
    return google.create_event(connection, calendar_id, payload)
