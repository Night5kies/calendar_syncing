import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.deps import get_db
from app.models.meeting_request import MeetingRequest
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.proposal_response import ProposalResponse
from app.models.scheduled_event import ScheduledEvent
from app.schemas.meeting_request import MeetingRequestCreate, ParticipantCreate, ProposalCreate
from app.schemas.proposal_response import ProposalResponseCreate, RequestFinalize
from app.services.meeting_requests import compute_end_at, next_status_on_response, scheduled_event_snapshot

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
        status="draft",
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

    proposals = (
        db.execute(select(Proposal).where(Proposal.meeting_request_id == request_id).order_by(Proposal.rank))
        .scalars()
        .all()
    )

    return {
        "id": str(req.id),
        "organizer_id": str(req.organizer_id),
        "title": req.title,
        "duration_min": req.duration_min,
        "timezone": req.timezone,
        "group_id": str(req.group_id) if req.group_id else None,
        "event_type": req.event_type,
        "location": req.location,
        "video_link": req.video_link,
        "notes": req.notes,
        "status": req.status,
        "proposals": [
            {
                "id": str(proposal.id),
                "rank": proposal.rank,
                "start_at": proposal.start_at.isoformat() if proposal.start_at else None,
                "end_at": compute_end_at(proposal.start_at, req.duration_min).isoformat()
                if proposal.start_at
                else None,
                "score": proposal.score,
                "meta": proposal.meta,
            }
            for proposal in proposals
        ],
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }


@router.post("/{request_id}/responses")
def submit_response(
    request_id: uuid.UUID,
    payload: ProposalResponseCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    req = db.get(MeetingRequest, request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    participant = db.get(Participant, payload.participant_id)
    if not participant or participant.meeting_request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")

    if participant.user_id and participant.user_id != current_user.user_id and req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for participant")

    proposal_id = payload.proposal_id
    if proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if not proposal or proposal.meeting_request_id != request_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    existing = db.execute(
        select(ProposalResponse).where(
            ProposalResponse.meeting_request_id == request_id,
            ProposalResponse.participant_id == participant.id,
        )
    ).scalar_one_or_none()

    if existing:
        existing.choice = payload.choice
        existing.proposal_id = proposal_id
        existing.comment = payload.comment
    else:
        existing = ProposalResponse(
            meeting_request_id=request_id,
            participant_id=participant.id,
            proposal_id=proposal_id,
            choice=payload.choice,
            comment=payload.comment,
        )
        db.add(existing)

    participant.status = "responded"
    participant.responded_at = participant.responded_at or datetime.now(timezone.utc)

    next_status = next_status_on_response(req.status, payload.choice)
    if req.status != next_status:
        req.status = next_status

    db.commit()
    return {"id": str(existing.id), "choice": existing.choice}


@router.post("/{request_id}/participants")
def create_participant(
    request_id: uuid.UUID,
    payload: ParticipantCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    req = db.get(MeetingRequest, request_id)
    if not req or req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if not payload.email and not payload.phone:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email or phone required")

    contact_key = None
    if payload.email:
        contact_key = f"email:{payload.email.strip().lower()}"
    elif payload.phone:
        contact_key = f"phone:{payload.phone.strip()}"

    participant = Participant(
        meeting_request_id=request_id,
        user_id=None,
        email=payload.email,
        phone=payload.phone,
        display_name=payload.display_name,
        role=payload.role,
        status="invited",
        contact_key=contact_key,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return {"id": str(participant.id)}


@router.post("/{request_id}/proposals")
def create_proposal(
    request_id: uuid.UUID,
    payload: ProposalCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    req = db.get(MeetingRequest, request_id)
    if not req or req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    try:
        start_at = datetime.fromisoformat(payload.start_at)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid start_at") from exc

    proposal = Proposal(
        meeting_request_id=request_id,
        rank=payload.rank,
        start_at=start_at,
        score=payload.score,
        meta=payload.meta,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return {"id": str(proposal.id)}


@router.post("/{request_id}/finalize")
def finalize_request(
    request_id: uuid.UUID,
    payload: RequestFinalize,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    req = db.get(MeetingRequest, request_id)
    if not req or req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    proposal = db.get(Proposal, payload.proposal_id)
    if not proposal or proposal.meeting_request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")

    snapshot = scheduled_event_snapshot(req, proposal)
    scheduled = db.execute(
        select(ScheduledEvent).where(ScheduledEvent.meeting_request_id == request_id)
    ).scalar_one_or_none()
    if scheduled:
        scheduled.proposal_id = proposal.id
        scheduled.status = "confirmed"
        for key, value in snapshot.items():
            setattr(scheduled, key, value)
    else:
        scheduled = ScheduledEvent(
            meeting_request_id=request_id,
            proposal_id=proposal.id,
            status="confirmed",
            **snapshot,
        )
        db.add(scheduled)

    req.status = "confirmed"
    db.commit()
    return {"id": str(scheduled.id)}
