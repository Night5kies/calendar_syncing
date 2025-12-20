import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.share_link import ShareLink
from app.models.meeting_request import MeetingRequest

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/{request_id}")
def create_share_link(request_id: str, db: Session = Depends(get_db)):
    req = db.get(MeetingRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")

    token = secrets.token_urlsafe(32)[:48]
    link = ShareLink(request_id=req.id, token=token)
    db.add(link)
    db.commit()
    return {"token": token, "url": f"/v1/share/public/{token}"}

@router.get("/public/{token}")
def get_share(token: str, db: Session = Depends(get_db)):
    link = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="invalid token")
    req = db.get(MeetingRequest, link.request_id)
    return {
        "request": {
            "id": str(req.id),
            "title": req.title,
            "duration_min": req.duration_min,
            "timezone": req.timezone,
            "window_start": req.window_start,
            "window_end": req.window_end,
            "constraints": req.constraints,
        }
    }
