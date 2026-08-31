from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.meeting_request import MeetingRequest
from app.models.participant import Participant
from app.models.proposal_response import ProposalResponse
from app.models.reminder_log import ReminderLog
from app.services.notifications import send_notification
from app.services.participants import build_invite_url

MAX_MANUAL_PROPOSALS = 5
MAX_REMINDERS_PER_PARTICIPANT = 3
DEFAULT_INITIAL_REMINDER_HOURS = 12
DEFAULT_FOLLOWUP_REMINDER_HOURS = 24


def resolve_reminder_policy(meeting_request: MeetingRequest) -> dict[str, int]:
    policy = meeting_request.reminder_policy or {}
    initial_hours = policy.get("initial_hours")
    followup_hours = policy.get("followup_hours")
    max_per_participant = policy.get("max_per_participant")
    return {
        "initial_hours": int(initial_hours) if isinstance(initial_hours, (int, float)) and initial_hours > 0 else DEFAULT_INITIAL_REMINDER_HOURS,
        "followup_hours": int(followup_hours) if isinstance(followup_hours, (int, float)) and followup_hours > 0 else DEFAULT_FOLLOWUP_REMINDER_HOURS,
        "max_per_participant": int(max_per_participant) if isinstance(max_per_participant, (int, float)) and max_per_participant > 0 else MAX_REMINDERS_PER_PARTICIPANT,
    }


def compute_end_at(start_at: datetime, duration_min: int) -> datetime:
    return start_at + timedelta(minutes=duration_min)


def next_status_on_response(current_status: str, choice: str) -> str:
    if current_status in ("confirmed", "canceled", "expired"):
        return current_status
    status = current_status
    if status == "sent":
        status = "collecting"
    if choice in ("declined", "maybe"):
        status = "needs_organizer_confirm"
    return status


def can_edit_proposals(current_status: str) -> bool:
    return current_status == "draft"


def validate_manual_proposal_rules(current_status: str, existing_count: int) -> None:
    if not can_edit_proposals(current_status):
        raise ValueError("Proposals are locked after the request is sent")
    if existing_count >= MAX_MANUAL_PROPOSALS:
        raise ValueError(f"Only {MAX_MANUAL_PROPOSALS} manual proposals are allowed in the MVP")


def scheduled_event_snapshot(meeting_request: Any, proposal: Any) -> dict[str, Any]:
    return {
        "title": meeting_request.title,
        "timezone": meeting_request.timezone,
        "start_at": proposal.start_at,
        "duration_min": meeting_request.duration_min,
        "event_type": meeting_request.event_type,
        "location": meeting_request.location,
        "video_link": meeting_request.video_link,
        "notes": meeting_request.notes,
    }


def get_outstanding_participants(
    db: Session,
    request_id: Any,
) -> list[Participant]:
    responded_participant_ids = (
        db.execute(
            select(ProposalResponse.participant_id).where(ProposalResponse.meeting_request_id == request_id)
        )
        .scalars()
        .all()
    )
    responded_ids = set(responded_participant_ids)
    participants = (
        db.execute(select(Participant).where(Participant.meeting_request_id == request_id))
        .scalars()
        .all()
    )
    return [participant for participant in participants if participant.id not in responded_ids]


def reminder_target_for_participant(participant: Participant) -> tuple[str, str] | None:
    if participant.email:
        return ("email", participant.email)
    if participant.phone:
        return ("sms", participant.phone)
    return None


def build_reminder_copy(meeting_request: MeetingRequest, participant: Participant, reason: str) -> str:
    name = participant.display_name or "there"
    deadline_text = (
        f" Respond by {meeting_request.response_deadline.isoformat()}."
        if meeting_request.response_deadline
        else ""
    )
    reason_text = "Final reminder." if reason == "deadline" else "Quick ping from the organizer."
    url = build_invite_url(meeting_request.id, participant.invite_token)
    return (
        f"Hi {name}, please respond to \"{meeting_request.title}\".{deadline_text} "
        f"{reason_text} {url}"
    ).strip()


def build_reminder_subject(meeting_request: MeetingRequest) -> str:
    return f"Reminder: respond to {meeting_request.title}"


def dispatch_request_reminders(
    db: Session,
    meeting_request: MeetingRequest,
    *,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    policy = resolve_reminder_policy(meeting_request)
    max_per_participant = policy["max_per_participant"]
    outstanding_participants = get_outstanding_participants(db, meeting_request.id)

    sent_logs: list[ReminderLog] = []
    skipped = 0
    for participant in outstanding_participants:
        target = reminder_target_for_participant(participant)
        if not target:
            skipped += 1
            continue

        existing_count = db.execute(
            select(func.count())
            .select_from(ReminderLog)
            .where(
                ReminderLog.meeting_request_id == meeting_request.id,
                ReminderLog.participant_id == participant.id,
            )
        ).scalar_one()
        if existing_count >= max_per_participant:
            skipped += 1
            continue

        next_sequence = int(existing_count) + 1
        channel, address = target
        body = build_reminder_copy(meeting_request, participant, reason)
        delivery = send_notification(
            channel=channel,
            target=address,
            subject=build_reminder_subject(meeting_request),
            body=body,
            metadata={
                "meeting_request_id": str(meeting_request.id),
                "participant_id": str(participant.id),
                "reminder_sequence": next_sequence,
            },
        )
        log = ReminderLog(
            meeting_request_id=meeting_request.id,
            participant_id=participant.id,
            channel=channel,
            reason=reason,
            reminder_sequence=next_sequence,
            status=delivery.status,
            target=address,
        )
        db.add(log)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            skipped += 1
            continue
        sent_logs.append(log)

    if sent_logs:
        meeting_request.last_reminded_at = now
        meeting_request.reminder_count = (meeting_request.reminder_count or 0) + len(sent_logs)

    return {
        "sent_count": len(sent_logs),
        "skipped_count": skipped,
        "outstanding_count": len(outstanding_participants),
        "policy": policy,
        "message_preview": [
            build_reminder_copy(meeting_request, participant, reason)
            for participant in outstanding_participants[:3]
        ],
    }


def due_requests_stmt(now: datetime | None = None) -> Select[tuple[MeetingRequest]]:
    now = now or datetime.now(timezone.utc)
    first_reminder_cutoff = now - timedelta(hours=DEFAULT_INITIAL_REMINDER_HOURS)
    return select(MeetingRequest).where(
        MeetingRequest.reminders_enabled.is_(True),
        MeetingRequest.status.in_(("sent", "collecting", "needs_organizer_confirm")),
        MeetingRequest.response_deadline.is_not(None),
        (
            (MeetingRequest.last_reminded_at.is_(None) & (MeetingRequest.created_at <= first_reminder_cutoff))
            | (MeetingRequest.response_deadline <= now + timedelta(hours=6))
        ),
    )
