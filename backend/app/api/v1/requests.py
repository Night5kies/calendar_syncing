import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_verified_organizer
from app.core.config import settings
from app.db.deps import get_db
from app.models.meeting_request import MeetingRequest
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.proposal_response import ProposalResponse
from app.models.reminder_log import ReminderLog
from app.models.scheduled_event import ScheduledEvent
from app.models.share_link import ShareLink
from app.schemas.meeting_request import (
    MeetingRequestCreate,
    ParticipantCreate,
    ProposalCreate,
    ReminderSettingsUpdate,
    SuggestRequestPayload,
)
from app.schemas.proposal_response import ProposalResponseCreate, RequestFinalize
from app.services.meeting_requests import (
    can_edit_proposals,
    compute_end_at,
    dispatch_request_reminders,
    get_outstanding_participants,
    next_status_on_response,
    resolve_reminder_policy,
    scheduled_event_snapshot,
    validate_manual_proposal_rules,
)
from app.services.scheduling import (
    generate_suggestions,
    load_organizer_constraints,
    materialize_suggestions,
    parse_inputs_from_payload,
)
from app.services.participants import (
    build_invite_url,
    generate_invite_token,
    normalize_email,
)
from app.models.profile import Profile
from app.services.scheduled_events import finalize_scheduled_event

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
        response_deadline=payload.response_deadline,
        reminders_enabled=payload.reminders_enabled,
        reminder_policy=(
            payload.reminder_policy.model_dump(exclude_none=True)
            if payload.reminder_policy is not None
            else None
        ),
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
    participants = (
        db.execute(select(Participant).where(Participant.meeting_request_id == request_id))
        .scalars()
        .all()
    )
    responses = (
        db.execute(select(ProposalResponse).where(ProposalResponse.meeting_request_id == request_id))
        .scalars()
        .all()
    )
    reminder_logs = (
        db.execute(
            select(ReminderLog)
            .where(ReminderLog.meeting_request_id == request_id)
            .order_by(ReminderLog.created_at.desc())
        )
        .scalars()
        .all()
    )
    share_link = db.execute(
        select(ShareLink).where(ShareLink.meeting_request_id == request_id).order_by(ShareLink.created_at.desc())
    ).scalar_one_or_none()
    scheduled = db.execute(
        select(ScheduledEvent).where(ScheduledEvent.meeting_request_id == request_id)
    ).scalar_one_or_none()

    tallies: dict[str, dict[str, int]] = {
        str(proposal.id): {"picked": 0, "maybe": 0, "declined": 0} for proposal in proposals
    }
    unassigned_maybe = 0
    declined_count = 0
    responded_participant_ids: set[uuid.UUID] = set()
    for response in responses:
        responded_participant_ids.add(response.participant_id)
        if response.choice == "picked" and response.proposal_id:
            tallies[str(response.proposal_id)]["picked"] += 1
        elif response.choice == "maybe":
            if response.proposal_id:
                tallies[str(response.proposal_id)]["maybe"] += 1
            else:
                unassigned_maybe += 1
        elif response.choice == "declined":
            declined_count += 1

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
        "participants": [
            {
                "id": str(participant.id),
                "display_name": participant.display_name,
                "email": participant.email,
                "phone": participant.phone,
                "status": participant.status,
                "source": participant.source,
                "responded_at": participant.responded_at.isoformat() if participant.responded_at else None,
                "invite_url": build_invite_url(request_id, participant.invite_token)
                if participant.invite_token
                else None,
            }
            for participant in participants
        ],
        "responses": [
            {
                "participant_id": str(response.participant_id),
                "proposal_id": str(response.proposal_id) if response.proposal_id else None,
                "choice": response.choice,
                "comment": response.comment,
            }
            for response in responses
        ],
        "progress": {
            "responded_count": len(responded_participant_ids),
            "participant_count": len(participants),
            "outstanding_count": max(len(participants) - len(responded_participant_ids), 0),
            "declined_count": declined_count,
            "unassigned_maybe_count": unassigned_maybe,
        },
        "tallies": tallies,
        "reminders": {
            "enabled": req.reminders_enabled,
            "response_deadline": req.response_deadline.isoformat() if req.response_deadline else None,
            "last_reminded_at": req.last_reminded_at.isoformat() if req.last_reminded_at else None,
            "sent_count": req.reminder_count,
            "policy": resolve_reminder_policy(req),
            "history": [
                {
                    "id": str(log.id),
                    "participant_id": str(log.participant_id),
                    "channel": log.channel,
                    "reason": log.reason,
                    "sequence": log.reminder_sequence,
                    "status": log.status,
                    "target": log.target,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in reminder_logs[:25]
            ],
        },
        "outstanding_participants": [
            {
                "id": str(participant.id),
                "display_name": participant.display_name,
                "email": participant.email,
                "phone": participant.phone,
            }
            for participant in get_outstanding_participants(db, request_id)
        ],
        "share": {
            "token": share_link.token,
            "url": build_invite_url(request_id, None),
            "legacy_url": f"{settings.app_base_url}/respond/{share_link.token}",
        }
        if share_link
        else None,
        "confirmed_event": {
            "id": str(scheduled.id),
            "proposal_id": str(scheduled.proposal_id),
            "provider": scheduled.provider,
            "provider_event_id": scheduled.provider_event_id,
            "artifact_uid": scheduled.artifact_uid,
            "title": scheduled.title,
            "start_at": scheduled.start_at.isoformat() if scheduled.start_at else None,
            "end_at": compute_end_at(scheduled.start_at, scheduled.duration_min).isoformat()
            if scheduled.start_at
            else None,
            "timezone": scheduled.timezone,
            "artifact_url": f"{settings.api_base_url}/v1/requests/{request_id}/artifact.ics"
            if scheduled.artifact_path
            else None,
        }
        if scheduled
        else None,
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

    normalized_email = normalize_email(payload.email)
    normalized_phone = payload.phone.strip() if payload.phone else None

    contact_key = None
    if normalized_email:
        contact_key = f"email:{normalized_email}"
    elif normalized_phone:
        contact_key = f"phone:{normalized_phone}"

    user_id_for_invite: uuid.UUID | None = None
    email_verified_at = None
    if normalized_email:
        profile = db.execute(
            select(Profile).where(func.lower(Profile.email) == normalized_email)
        ).scalar_one_or_none()
        if profile is not None:
            user_id_for_invite = profile.id
            email_verified_at = profile.email_verified_at

    participant = Participant(
        meeting_request_id=request_id,
        user_id=user_id_for_invite,
        email=normalized_email,
        phone=normalized_phone,
        display_name=payload.display_name,
        role=payload.role,
        status="invited",
        source="invited",
        invite_token=generate_invite_token(),
        email_verified_at=email_verified_at,
        contact_key=contact_key,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return {
        "id": str(participant.id),
        "invite_url": build_invite_url(request_id, participant.invite_token),
    }


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

    proposal_count = db.execute(
        select(func.count()).select_from(Proposal).where(Proposal.meeting_request_id == request_id)
    ).scalar_one()
    try:
        validate_manual_proposal_rules(req.status, proposal_count)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

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


@router.post("/{request_id}/suggest")
def suggest_proposals(
    request_id: uuid.UUID,
    payload: SuggestRequestPayload,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    req = db.get(MeetingRequest, request_id)
    if not req or req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if payload.mode == "suggest" and not can_edit_proposals(req.status):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Proposals are locked after the request is sent",
        )

    try:
        inputs = parse_inputs_from_payload(
            payload.model_dump(exclude_none=True),
            meeting_request=req,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    range_start = _dt.combine(inputs.start_date, _dt.min.time(), tzinfo=_tz.utc)
    range_end = _dt.combine(inputs.end_date, _dt.min.time(), tzinfo=_tz.utc) + _td(days=1)

    organizer_rule, blocked_intervals = load_organizer_constraints(
        db, current_user.user_id, range_start, range_end
    )

    try:
        suggestions = generate_suggestions(
            inputs,
            organizer_rule=organizer_rule,
            blocked_intervals=blocked_intervals,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    response_payload = {
        "suggestions": [
            {
                "start_at": suggestion.start_at.isoformat(),
                "end_at": suggestion.end_at.isoformat(),
                "score": suggestion.score,
                "reasons": suggestion.reasons,
            }
            for suggestion in suggestions
        ]
    }

    if payload.mode == "preview":
        return response_payload

    materialize_suggestions(
        db,
        req,
        suggestions,
        replace_existing=payload.replace_existing,
    )
    db.commit()
    return response_payload


@router.post("/{request_id}/finalize")
def finalize_request(
    request_id: uuid.UUID,
    payload: RequestFinalize,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_verified_organizer),
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
    finalize_scheduled_event(
        db,
        scheduled_event=scheduled,
        organizer_email=current_user.email,
        organizer_id=current_user.user_id,
    )
    db.commit()
    return {"id": str(scheduled.id)}


@router.post("/{request_id}/reminders/ping")
def ping_non_responders(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_verified_organizer),
):
    req = db.get(MeetingRequest, request_id)
    if not req or req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    result = dispatch_request_reminders(db, req, reason="manual_ping")
    db.commit()
    return result


@router.patch("/{request_id}/reminders")
def update_reminders(
    request_id: uuid.UUID,
    payload: ReminderSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_verified_organizer),
):
    req = db.get(MeetingRequest, request_id)
    if not req or req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if "reminders_enabled" in payload.model_fields_set:
        req.reminders_enabled = bool(payload.reminders_enabled)
    if "response_deadline" in payload.model_fields_set:
        req.response_deadline = payload.response_deadline
    if "reminder_policy" in payload.model_fields_set:
        if payload.reminder_policy is None:
            req.reminder_policy = None
        else:
            req.reminder_policy = payload.reminder_policy.model_dump(exclude_none=True) or None

    db.commit()
    return {
        "reminders_enabled": req.reminders_enabled,
        "response_deadline": req.response_deadline.isoformat() if req.response_deadline else None,
        "policy": resolve_reminder_policy(req),
    }


@router.get("/{request_id}/artifact.ics")
def download_confirmation_artifact(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    req = db.get(MeetingRequest, request_id)
    if not req or req.organizer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    scheduled = db.execute(
        select(ScheduledEvent).where(ScheduledEvent.meeting_request_id == request_id)
    ).scalar_one_or_none()
    if not scheduled or not scheduled.artifact_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    return FileResponse(
        scheduled.artifact_path,
        media_type="text/calendar",
        filename=f"{req.title}.ics",
    )
