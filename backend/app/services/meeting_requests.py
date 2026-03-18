from datetime import datetime, timedelta
from typing import Any

MAX_MANUAL_PROPOSALS = 5


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
