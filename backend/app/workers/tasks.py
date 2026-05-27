import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.meeting_request import MeetingRequest
from app.services.confirmation_invites import dispatch_confirmation_invites
from app.services.meeting_requests import dispatch_request_reminders, due_requests_stmt
from app.workers.celery_app import celery


@celery.task
def send_request_reminders(request_id: str, reason: str = "scheduled") -> dict:
    with SessionLocal() as db:
        return _send_request_reminders(db, request_id, reason)


@celery.task
def enqueue_due_reminders() -> dict:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        requests = db.execute(due_requests_stmt(now)).scalars().all()
        results = []
        for meeting_request in requests:
            reason = "deadline" if meeting_request.response_deadline and meeting_request.response_deadline <= now else "scheduled"
            results.append(_send_request_reminders(db, str(meeting_request.id), reason))
        return {"processed": len(results), "results": results}


@celery.task
def send_confirmation_invites(scheduled_event_id: str) -> dict:
    with SessionLocal() as db:
        result = dispatch_confirmation_invites(db, scheduled_event_id=scheduled_event_id)
        db.commit()
        return result


def _send_request_reminders(db: Session, request_id: str, reason: str) -> dict:
    try:
        request_uuid = uuid.UUID(request_id)
    except ValueError:
        return {"request_id": request_id, "sent_count": 0, "error": "invalid_request_id"}

    meeting_request = db.get(MeetingRequest, request_uuid)
    if not meeting_request:
        return {"request_id": request_id, "sent_count": 0, "error": "request_not_found"}

    result = dispatch_request_reminders(db, meeting_request, reason=reason)
    db.commit()
    return {"request_id": request_id, "reason": reason, **result}
