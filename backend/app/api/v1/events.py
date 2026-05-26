import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.deps import get_db
from app.models.meeting_request import MeetingRequest
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.proposal_response import ProposalResponse
from app.models.scheduled_event import ScheduledEvent
from app.services.meeting_requests import compute_end_at, next_status_on_response
from app.services.participants import (
    ParticipantResolutionError,
    build_invite_url,
    normalize_email,
    resolve_participant,
    send_magic_respond_link,
)


router = APIRouter()


class EventRespondPayload(BaseModel):
    proposal_id: uuid.UUID | None = None
    choice: str = "picked"
    comment: str | None = None
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None
    invite_token: str | None = None


def _event_payload(req: MeetingRequest, proposals: list[Proposal]) -> dict:
    return {
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


def _confirmed_event_payload(
    req: MeetingRequest, scheduled: ScheduledEvent | None
) -> dict | None:
    if scheduled is None:
        return None
    end_at = (
        compute_end_at(scheduled.start_at, scheduled.duration_min).isoformat()
        if scheduled.start_at
        else None
    )
    return {
        "id": str(scheduled.id),
        "proposal_id": str(scheduled.proposal_id),
        "title": scheduled.title,
        "timezone": scheduled.timezone,
        "start_at": scheduled.start_at.isoformat() if scheduled.start_at else None,
        "end_at": end_at,
        "duration_min": scheduled.duration_min,
        "location": scheduled.location,
        "video_link": scheduled.video_link,
        "notes": scheduled.notes,
        "artifact_url": (
            f"{settings.api_base_url}/v1/events/{req.id}/artifact.ics"
            if scheduled.artifact_path
            else None
        ),
    }


@router.get("/{event_id}/respond")
def get_event_respond_context(
    event_id: uuid.UUID,
    token: str | None = None,
    db: Session = Depends(get_db),
):
    req = db.get(MeetingRequest, event_id)
    if not req:
        raise HTTPException(status_code=404, detail="event not found")
    if req.status in ("canceled", "expired"):
        raise HTTPException(status_code=410, detail=f"event is {req.status}")

    proposals = (
        db.execute(
            select(Proposal).where(Proposal.meeting_request_id == event_id).order_by(Proposal.rank)
        )
        .scalars()
        .all()
    )

    invited_participant = None
    if token:
        invited_participant = db.execute(
            select(Participant).where(
                Participant.meeting_request_id == event_id,
                Participant.invite_token == token,
            )
        ).scalar_one_or_none()

    scheduled = db.execute(
        select(ScheduledEvent).where(ScheduledEvent.meeting_request_id == event_id)
    ).scalar_one_or_none()

    response: dict = {
        "event": _event_payload(req, proposals),
        "confirmed_event": _confirmed_event_payload(req, scheduled),
    }

    if invited_participant is not None:
        existing_response = db.execute(
            select(ProposalResponse).where(
                ProposalResponse.meeting_request_id == event_id,
                ProposalResponse.participant_id == invited_participant.id,
            )
        ).scalar_one_or_none()
        response["invited_as"] = {
            "id": str(invited_participant.id),
            "display_name": invited_participant.display_name,
            "email": invited_participant.email,
            "status": invited_participant.status,
            "current_response": {
                "proposal_id": str(existing_response.proposal_id) if existing_response and existing_response.proposal_id else None,
                "choice": existing_response.choice if existing_response else None,
                "comment": existing_response.comment if existing_response else None,
            }
            if existing_response
            else None,
        }
        invited_participant.last_viewed_at = datetime.now(timezone.utc)
        db.commit()

    return response


@router.post("/{event_id}/responses")
def submit_event_response(
    event_id: uuid.UUID,
    payload: EventRespondPayload,
    db: Session = Depends(get_db),
):
    req = db.get(MeetingRequest, event_id)
    if not req:
        raise HTTPException(status_code=404, detail="event not found")
    if req.status in ("canceled", "expired", "confirmed"):
        raise HTTPException(status_code=409, detail=f"event is {req.status}")

    if payload.choice not in ("picked", "maybe", "declined"):
        raise HTTPException(status_code=422, detail="invalid choice")

    proposal = None
    if payload.proposal_id:
        proposal = db.get(Proposal, payload.proposal_id)
        if not proposal or proposal.meeting_request_id != event_id:
            raise HTTPException(status_code=404, detail="proposal not found")
    if payload.choice == "picked" and not proposal:
        raise HTTPException(status_code=422, detail="proposal_id is required when choice is picked")

    came_from_general_link = payload.invite_token is None

    try:
        resolved = resolve_participant(
            db,
            event_id=event_id,
            invite_token=payload.invite_token,
            submitted_name=payload.display_name,
            submitted_email=payload.email,
            submitted_phone=payload.phone,
            came_from_general_link=came_from_general_link,
        )
    except ParticipantResolutionError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    if resolved.requires_email_link:
        result = send_magic_respond_link(db, participant=resolved.participant, request=req)
        db.commit()
        return result

    participant = resolved.participant

    submitted_name = (payload.display_name or "").strip()
    if submitted_name:
        participant.display_name = submitted_name

    existing = db.execute(
        select(ProposalResponse).where(
            ProposalResponse.meeting_request_id == event_id,
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
                meeting_request_id=event_id,
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
        "invite_url": build_invite_url(event_id, participant.invite_token),
    }


@router.get("/{event_id}/artifact.ics")
def download_event_artifact(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Public ICS download for attendees of a confirmed event.

    Only resolves once the event is confirmed and the artifact has been
    written. Returns 404 otherwise so a half-finished event never leaks
    its calendar metadata.
    """
    req = db.get(MeetingRequest, event_id)
    if not req or req.status != "confirmed":
        raise HTTPException(status_code=404, detail="event not confirmed")

    scheduled = db.execute(
        select(ScheduledEvent).where(ScheduledEvent.meeting_request_id == event_id)
    ).scalar_one_or_none()
    if not scheduled or not scheduled.artifact_path:
        raise HTTPException(status_code=404, detail="artifact not found")

    return FileResponse(
        scheduled.artifact_path,
        media_type="text/calendar",
        filename=f"{req.title}.ics",
    )
