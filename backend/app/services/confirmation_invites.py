from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.meeting_request import MeetingRequest
from app.models.notification_event import NotificationEvent
from app.models.participant import Participant
from app.models.scheduled_event import ScheduledEvent
from app.services.confirmation_artifacts import artifact_filename
from app.services.meeting_requests import compute_end_at
from app.services.notifications import EmailAttachment, send_notification


INVITE_KIND = "confirmation_invite"


def _format_local(start_at: datetime, timezone_name: str) -> str:
    try:
        from zoneinfo import ZoneInfo

        local = start_at.astimezone(ZoneInfo(timezone_name))
    except Exception:  # pragma: no cover - fallback
        local = start_at
    return local.strftime("%a %b %d, %I:%M %p")


def _build_email_body(
    meeting_request: MeetingRequest,
    scheduled: ScheduledEvent,
    participant: Participant,
) -> str:
    name = participant.display_name or "there"
    when = _format_local(scheduled.start_at, scheduled.timezone or meeting_request.timezone)
    duration = scheduled.duration_min
    lines = [
        f"Hi {name},",
        "",
        f"\"{meeting_request.title}\" is confirmed for {when} ({scheduled.timezone}, {duration} min).",
    ]
    if scheduled.location:
        lines.append(f"Location: {scheduled.location}")
    if scheduled.video_link:
        lines.append(f"Video link: {scheduled.video_link}")
    if scheduled.notes:
        lines.append("")
        lines.append(scheduled.notes)
    lines.extend(
        [
            "",
            f"Add to your calendar: {settings.api_base_url}/v1/events/{meeting_request.id}/artifact.ics",
            "",
            "— SYZY",
        ]
    )
    return "\n".join(lines)


def _read_ics_body(scheduled: ScheduledEvent) -> str | None:
    if not scheduled.artifact_path:
        return None
    path = Path(scheduled.artifact_path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _ics_method(ics_body: str) -> str:
    """Mirror the METHOD declared inside the file.

    The MIME part's `method` parameter and the VCALENDAR METHOD property have
    to agree; hard-coding REQUEST here while the body said PUBLISH left some
    clients refusing to render the invite.
    """
    for line in ics_body.splitlines():
        if line.upper().startswith("METHOD:"):
            return line.split(":", 1)[1].strip() or "PUBLISH"
    return "PUBLISH"


def dispatch_confirmation_invites(
    db: Session,
    *,
    scheduled_event_id: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    scheduled_event_uuid = (
        scheduled_event_id
        if isinstance(scheduled_event_id, uuid.UUID)
        else uuid.UUID(str(scheduled_event_id))
    )
    scheduled = db.get(ScheduledEvent, scheduled_event_uuid)
    if scheduled is None:
        return {"sent_count": 0, "skipped_count": 0, "error": "scheduled_event_not_found"}

    meeting_request = db.get(MeetingRequest, scheduled.meeting_request_id)
    if meeting_request is None:
        return {"sent_count": 0, "skipped_count": 0, "error": "meeting_request_not_found"}

    participants = (
        db.execute(
            select(Participant).where(Participant.meeting_request_id == meeting_request.id)
        )
        .scalars()
        .all()
    )

    ics_body = _read_ics_body(scheduled)
    ics_filename = artifact_filename(meeting_request.title, str(meeting_request.id))

    sent = 0
    skipped = 0
    failed = 0
    for participant in participants:
        if not participant.email:
            skipped += 1
            continue
        log = NotificationEvent(
            scheduled_event_id=scheduled.id,
            meeting_request_id=meeting_request.id,
            participant_id=participant.id,
            kind=INVITE_KIND,
            channel="email",
            target=participant.email,
            status="queued",
            payload={
                "title": meeting_request.title,
                "start_at": scheduled.start_at.isoformat() if scheduled.start_at else None,
                "end_at": compute_end_at(scheduled.start_at, scheduled.duration_min).isoformat()
                if scheduled.start_at
                else None,
                "timezone": scheduled.timezone,
            },
        )
        # A savepoint, not db.rollback(): a plain rollback here discarded the
        # caller's entire uncommitted transaction -- the ScheduledEvent insert
        # and the request's move to "confirmed" included -- so one duplicate
        # notification row silently unwound the whole confirmation.
        savepoint = db.begin_nested()
        db.add(log)
        try:
            db.flush()
        except IntegrityError:
            savepoint.rollback()
            skipped += 1
            continue
        savepoint.commit()

        attachments = (
            [
                EmailAttachment(
                    filename=ics_filename,
                    media_type="text/calendar",
                    content=ics_body,
                    method=_ics_method(ics_body),
                )
            ]
            if ics_body
            else None
        )
        delivery = send_notification(
            channel="email",
            target=participant.email,
            subject=f"Confirmed: {meeting_request.title}",
            body=_build_email_body(meeting_request, scheduled, participant),
            metadata={
                "scheduled_event_id": str(scheduled.id),
                "meeting_request_id": str(meeting_request.id),
                "participant_id": str(participant.id),
                "kind": INVITE_KIND,
            },
            attachments=attachments,
        )
        log.status = delivery.status
        if delivery.status == "failed":
            failed += 1
        else:
            sent += 1

    return {
        "sent_count": sent,
        "skipped_count": skipped,
        "failed_count": failed,
        "participant_count": len(participants),
        "scheduled_event_id": str(scheduled.id),
    }
