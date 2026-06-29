from __future__ import annotations

import logging
import uuid
from datetime import timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.calendar_connection import CalendarConnection
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
    ics_path = write_ics_artifact(scheduled_event, artifact_uid, organizer_email)

    scheduled_event.artifact_uid = artifact_uid
    scheduled_event.artifact_path = str(ics_path)

    provider = None
    provider_event_id = None
    connection = get_google_connection(db, organizer_id)
    if connection:
        calendar_id = choose_google_calendar_id(db, organizer_id)
        if calendar_id:
            try:
                created = retry_call(
                    lambda: create_google_calendar_event(
                        connection, calendar_id, scheduled_event, artifact_uid, organizer_email
                    )
                )
                provider = "google"
                provider_event_id = created.get("id")
            except Exception:
                # Write-back is best-effort: the ICS artifact already exists and
                # the event is confirmed regardless. Log loudly so the failure is
                # not silent (organizer's calendar simply won't have the event).
                logger.warning(
                    "Google Calendar write-back failed for scheduled_event %s after retries",
                    scheduled_event.id,
                    exc_info=True,
                )
                provider = None
                provider_event_id = None

    scheduled_event.provider = provider
    scheduled_event.provider_event_id = provider_event_id
    return {
        "artifact_path": str(ics_path),
        "provider": provider,
        "provider_event_id": provider_event_id,
    }


def write_ics_artifact(
    scheduled_event: ScheduledEvent,
    artifact_uid: str,
    organizer_email: str | None,
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
    )
    artifact_dir = ensure_artifact_dir("artifacts")
    file_path = artifact_dir / artifact_filename(scheduled_event.title, str(scheduled_event.meeting_request_id))
    file_path.write_text(ics, encoding="utf-8")
    return file_path


def get_google_connection(db: Session, organizer_id: Any) -> CalendarConnection | None:
    return db.execute(
        select(CalendarConnection)
        .where(CalendarConnection.user_id == organizer_id)
        .where(CalendarConnection.provider == "google")
        .where(CalendarConnection.revoked_at.is_(None))
        .order_by(CalendarConnection.created_at.desc())
    ).scalar_one_or_none()


def choose_google_calendar_id(db: Session, organizer_id: Any) -> str | None:
    calendar = db.execute(
        select(ProviderCalendar)
        .where(ProviderCalendar.user_id == organizer_id)
        .where(ProviderCalendar.provider == "google")
        .where(ProviderCalendar.is_enabled.is_(True))
        .order_by(ProviderCalendar.is_primary.desc(), ProviderCalendar.updated_at.desc())
    ).scalar_one_or_none()
    return calendar.provider_calendar_id if calendar else "primary"


def create_google_calendar_event(
    connection: CalendarConnection,
    calendar_id: str,
    scheduled_event: ScheduledEvent,
    artifact_uid: str,
    organizer_email: str | None,
) -> dict[str, Any]:
    payload = {
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
        "extendedProperties": {"private": {"syzy_uid": artifact_uid}},
    }
    if organizer_email:
        payload["guestsCanModify"] = False
    return google.create_event(connection, calendar_id, payload)
