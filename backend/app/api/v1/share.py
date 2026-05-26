import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_verified_organizer
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.share_link import ShareLink
from app.models.meeting_request import MeetingRequest
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.proposal_response import ProposalResponse
from app.services.meeting_requests import compute_end_at, next_status_on_response
from app.services.participants import (
    ParticipantResolutionError,
    build_invite_url,
    resolve_participant,
    send_magic_respond_link,
)

router = APIRouter()


class PublicResponseCreate(BaseModel):
    display_name: str
    guest_key: str
    proposal_id: uuid.UUID | None = None
    choice: str = "picked"
    comment: str | None = None
    email: str | None = None
    phone: str | None = None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/{request_id}")
def create_share_link(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_verified_organizer),
):
    req = db.get(MeetingRequest, request_id)
    if not req or req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request not found")

    token = secrets.token_urlsafe(32)[:48]
    link = ShareLink(meeting_request_id=req.id, token=token)
    db.add(link)
    if req.status == "draft":
        req.status = "sent"
    db.commit()
    return {
        "token": token,
        "url": f"{settings.app_base_url}/events/{req.id}/respond",
        "legacy_url": f"{settings.app_base_url}/respond/{token}",
    }

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


@router.post("/public/{token}/responses")
def submit_public_response(token: str, payload: PublicResponseCreate, db: Session = Depends(get_db)):
    """Legacy general-share-link response endpoint.

    Delegates to the same resolve_participant flow the new
    /v1/events/{event_id}/responses endpoint uses, so identity
    resolution stays consistent regardless of which URL the
    attendee landed on.
    """
    link = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="invalid token")

    req = db.get(MeetingRequest, link.meeting_request_id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")

    proposal = None
    if payload.proposal_id:
        proposal = db.get(Proposal, payload.proposal_id)
        if not proposal or proposal.meeting_request_id != req.id:
            raise HTTPException(status_code=404, detail="proposal not found")

    try:
        resolved = resolve_participant(
            db,
            event_id=req.id,
            submitted_name=payload.display_name,
            submitted_email=payload.email,
            submitted_phone=payload.phone,
            came_from_general_link=True,
        )
    except ParticipantResolutionError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    if resolved.requires_email_link:
        result = send_magic_respond_link(db, participant=resolved.participant, request=req)
        db.commit()
        return result

    participant = resolved.participant

    if payload.display_name and payload.display_name.strip():
        participant.display_name = payload.display_name.strip()

    existing = db.execute(
        select(ProposalResponse).where(
            ProposalResponse.meeting_request_id == req.id,
            ProposalResponse.participant_id == participant.id,
        )
    ).scalar_one_or_none()

    if existing:
        existing.choice = payload.choice
        existing.proposal_id = payload.proposal_id
        existing.comment = payload.comment
    else:
        db.add(
            ProposalResponse(
                meeting_request_id=req.id,
                participant_id=participant.id,
                proposal_id=payload.proposal_id,
                choice=payload.choice,
                comment=payload.comment,
            )
        )

    participant.status = "responded"
    participant.responded_at = datetime.now(timezone.utc)
    req.status = next_status_on_response(req.status, payload.choice)
    db.commit()

    return {
        "ok": True,
        "status": "saved",
        "participant_id": str(participant.id),
        "choice": payload.choice,
        "proposal_id": str(payload.proposal_id) if payload.proposal_id else None,
        "invite_url": build_invite_url(req.id, participant.invite_token),
    }
