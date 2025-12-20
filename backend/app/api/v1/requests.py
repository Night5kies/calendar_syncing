import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.meeting_request import MeetingRequest
from app.schemas.meeting_request import MeetingRequestCreate

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("")
def create_request(payload: MeetingRequestCreate, db: Session = Depends(get_db)):
    # organizer_id hardcoded for now; you'll replace with real auth later
    organizer_id = uuid.uuid4()
    req = MeetingRequest(
        organizer_id=organizer_id,
        title=payload.title,
        duration_min=payload.duration_min,
        timezone=payload.timezone,
        window_start=payload.window_start,
        window_end=payload.window_end,
        constraints=payload.constraints,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"id": str(req.id)}
