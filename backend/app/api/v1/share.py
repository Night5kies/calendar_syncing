import secrets
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.share_link import ShareLink
from app.models.meeting_request import MeetingRequest
from app.models.proposal import Proposal
from app.services.meeting_requests import compute_end_at

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/{request_id}")
def create_share_link(request_id: uuid.UUID, db: Session = Depends(get_db)):
    req = db.get(MeetingRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")

    token = secrets.token_urlsafe(32)[:48]
    link = ShareLink(meeting_request_id=req.id, token=token)
    db.add(link)
    if req.status == "draft":
        req.status = "sent"
    db.commit()
    return {"token": token, "url": f"/v1/share/public/{token}"}

@router.get("/public/{token}")
def get_share(token: str, db: Session = Depends(get_db)):
    link = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="invalid token")
    req = db.get(MeetingRequest, link.meeting_request_id)
    proposals = (
        db.execute(
            select(Proposal)
            .where(Proposal.meeting_request_id == req.id)
            .order_by(Proposal.rank)
        )
        .scalars()
        .all()
    )
    return {
        "request": {
            "id": str(req.id),
            "title": req.title,
            "duration_min": req.duration_min,
            "timezone": req.timezone,
            "event_type": req.event_type,
            "location": req.location,
            "video_link": req.video_link,
            "notes": req.notes,
            "status": req.status,
            "proposals": [
                {
                    "id": str(proposal.id),
                    "rank": proposal.rank,
                    "start_at": proposal.start_at.isoformat(),
                    "end_at": compute_end_at(proposal.start_at, req.duration_min).isoformat(),
                    "score": proposal.score,
                    "meta": proposal.meta,
                }
                for proposal in proposals
            ],
        }
    }
