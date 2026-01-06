import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.deps import get_db
from app.models.meeting_request import MeetingRequest
from app.schemas.meeting_request import MeetingRequestCreate

router = APIRouter()

@router.post("")
def create_request(
    payload: MeetingRequestCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    organizer_id = current_user.user_id
    req = MeetingRequest(
        organizer_id=organizer_id,
        title=payload.title,
        duration_min=payload.duration_min,
        timezone=payload.timezone,
        group_id=payload.group_id,
        event_type=payload.event_type,
        location=payload.location,
        video_link=payload.video_link,
        notes=payload.notes,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"id": str(req.id)}


@router.get("/{request_id}")
def get_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    stmt = select(MeetingRequest).where(
        MeetingRequest.id == request_id,
        MeetingRequest.organizer_id == current_user.user_id,
    )
    req = db.execute(stmt).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    return {
        "id": str(req.id),
        "organizer_id": str(req.organizer_id),
        "title": req.title,
        "duration_min": req.duration_min,
        "timezone": req.timezone,
        "window_start": req.window_start,
        "window_end": req.window_end,
        "constraints": req.constraints,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }
