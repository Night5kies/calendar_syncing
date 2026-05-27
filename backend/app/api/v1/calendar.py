import base64
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.db.deps import get_db
from app.models.availability_block import AvailabilityBlock
from app.models.busy_cache import BusyCache
from app.models.calendar_connection import CalendarConnection
from app.models.calendar_share import CalendarShare
from app.models.event_cache import EventCache
from app.models.profile import Profile
from app.models.provider_calendar import ProviderCalendar
from app.providers import google
from app.schemas.calendar import CalendarShareCreate, CalendarToggle
from app.services.calendar import is_cache_stale, merge_intervals, redact_events_for_permission

router = APIRouter(prefix="/calendar")


def _encode_state(user_id: uuid.UUID, return_to: str | None) -> str:
    raw = json.dumps(
        {
            "uid": str(user_id),
            "nonce": secrets.token_urlsafe(16),
            "return_to": return_to or settings.app_base_url,
        }
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_state(state: str) -> dict:
    padded = state + "=" * (-len(state) % 4)
    raw = base64.urlsafe_b64decode(padded.encode())
    return json.loads(raw)


def parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def get_enabled_calendar_ids(calendars: list[ProviderCalendar], provider: str) -> list[str]:
    return [
        calendar.provider_calendar_id
        for calendar in calendars
        if calendar.provider == provider and calendar.is_enabled
    ]


def refresh_provider_calendars(db: Session, connection: CalendarConnection) -> None:
    calendars = google.list_calendars(connection) if connection.provider == "google" else []
    if not calendars:
        return
    table = ProviderCalendar.__table__
    now = datetime.now(timezone.utc)
    for calendar in calendars:
        stmt = insert(table).values(
            id=uuid.uuid4(),
            user_id=connection.user_id,
            provider=connection.provider,
            provider_calendar_id=calendar["provider_calendar_id"],
            name=calendar["name"],
            is_primary=calendar.get("is_primary", False),
            is_enabled=calendar.get("is_enabled", True),
            color=calendar.get("color"),
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "provider", "provider_calendar_id"],
            set_={
                "name": stmt.excluded.name,
                "is_primary": stmt.excluded.is_primary,
                "is_enabled": stmt.excluded.is_enabled,
                "color": stmt.excluded.color,
                "updated_at": now,
            },
        )
        db.execute(stmt)


def upsert_event_cache(db: Session, user_id: uuid.UUID, events: list[dict[str, object]]) -> None:
    if not events:
        return
    table = EventCache.__table__
    now = datetime.now(timezone.utc)
    for event in events:
        stmt = insert(table).values(
            id=uuid.uuid4(),
            user_id=user_id,
            provider=event["provider"],
            provider_event_id=event["provider_event_id"],
            provider_calendar_id=event["provider_calendar_id"],
            start_at=event["start_at"],
            end_at=event["end_at"],
            is_all_day=event.get("is_all_day", False),
            timezone=event.get("timezone"),
            title=event.get("title"),
            location=event.get("location"),
            is_private=event.get("is_private", False),
            etag=event.get("etag"),
            last_fetched_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                "user_id",
                "provider",
                "provider_calendar_id",
                "provider_event_id",
                "start_at",
                "end_at",
            ],
            set_={
                "is_all_day": stmt.excluded.is_all_day,
                "timezone": stmt.excluded.timezone,
                "title": stmt.excluded.title,
                "location": stmt.excluded.location,
                "is_private": stmt.excluded.is_private,
                "etag": stmt.excluded.etag,
                "last_fetched_at": now,
            },
        )
        db.execute(stmt)


def refresh_busy_cache(
    db: Session,
    user_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    enabled_calendar_ids: list[str],
) -> None:
    event_rows = []
    if enabled_calendar_ids:
        event_rows = db.execute(
            select(EventCache.start_at, EventCache.end_at)
            .where(EventCache.user_id == user_id)
            .where(EventCache.provider_calendar_id.in_(enabled_calendar_ids))
            .where(EventCache.start_at < end_at)
            .where(EventCache.end_at > start_at)
        ).all()
    block_rows = db.execute(
        select(AvailabilityBlock.start_at, AvailabilityBlock.end_at)
        .where(AvailabilityBlock.user_id == user_id)
        .where(AvailabilityBlock.start_at < end_at)
        .where(AvailabilityBlock.end_at > start_at)
    ).all()
    intervals = [(row[0], row[1]) for row in event_rows] + [(row[0], row[1]) for row in block_rows]
    merged = merge_intervals(intervals)
    db.execute(
        delete(BusyCache)
        .where(BusyCache.user_id == user_id)
        .where(BusyCache.start_at < end_at)
        .where(BusyCache.end_at > start_at)
    )
    now = datetime.now(timezone.utc)
    for start, end in merged:
        db.add(
            BusyCache(
                user_id=user_id,
                start_at=start,
                end_at=end,
                source="computed:merged",
                last_fetched_at=now,
            )
        )


def ensure_event_cache(
    db: Session,
    user_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    connections: list[CalendarConnection],
) -> None:
    calendars = db.execute(select(ProviderCalendar).where(ProviderCalendar.user_id == user_id)).scalars().all()
    for connection in connections:
        enabled_ids = get_enabled_calendar_ids(calendars, connection.provider)
        if not enabled_ids:
            continue
        last_fetched_rows = db.execute(
            select(EventCache.last_fetched_at)
            .where(EventCache.user_id == user_id)
            .where(EventCache.provider == connection.provider)
            .where(EventCache.provider_calendar_id.in_(enabled_ids))
            .where(EventCache.start_at < end_at)
            .where(EventCache.end_at > start_at)
        ).all()
        if is_cache_stale([row[0] for row in last_fetched_rows]):
            events = (
                google.fetch_events(connection, enabled_ids, start_at, end_at)
                if connection.provider == "google"
                else []
            )
            upsert_event_cache(db, user_id, events)
        refresh_busy_cache(db, user_id, start_at, end_at, enabled_ids)


@router.get("/events")
def get_events(
    start: str = Query(...),
    end: str = Query(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    start_at = parse_iso(start)
    end_at = parse_iso(end)
    if start_at >= end_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid range")

    connections = db.execute(
        select(CalendarConnection).where(CalendarConnection.user_id == current_user.user_id)
    ).scalars().all()
    calendars = db.execute(select(ProviderCalendar).where(ProviderCalendar.user_id == current_user.user_id)).scalars().all()
    if not calendars and connections:
        for connection in connections:
            refresh_provider_calendars(db, connection)
        db.commit()
        calendars = db.execute(
            select(ProviderCalendar).where(ProviderCalendar.user_id == current_user.user_id)
        ).scalars().all()

    ensure_event_cache(db, current_user.user_id, start_at, end_at, connections)
    db.commit()

    enabled_ids = [calendar.provider_calendar_id for calendar in calendars if calendar.is_enabled]
    if not enabled_ids:
        return {"events": []}

    events = db.execute(
        select(EventCache)
        .where(EventCache.user_id == current_user.user_id)
        .where(EventCache.provider_calendar_id.in_(enabled_ids))
        .where(EventCache.start_at < end_at)
        .where(EventCache.end_at > start_at)
    ).scalars().all()

    return {
        "events": [
            {
                "start_at": event.start_at,
                "end_at": event.end_at,
                "is_all_day": event.is_all_day,
                "title": event.title,
                "location": event.location,
                "is_private": event.is_private,
                "provider": event.provider,
                "provider_calendar_id": event.provider_calendar_id,
            }
            for event in events
        ]
    }


@router.get("/overlay")
def get_overlay(
    owner_id: uuid.UUID,
    start: str = Query(...),
    end: str = Query(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    share = db.execute(
        select(CalendarShare).where(
            CalendarShare.owner_id == owner_id,
            CalendarShare.viewer_id == current_user.user_id,
        )
    ).scalar_one_or_none()
    if not share or share.permission_level == "none":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    start_at = parse_iso(start)
    end_at = parse_iso(end)
    if start_at >= end_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid range")

    connections = db.execute(select(CalendarConnection).where(CalendarConnection.user_id == owner_id)).scalars().all()
    calendars = db.execute(select(ProviderCalendar).where(ProviderCalendar.user_id == owner_id)).scalars().all()
    if not calendars and connections:
        for connection in connections:
            refresh_provider_calendars(db, connection)
        db.commit()
        calendars = db.execute(select(ProviderCalendar).where(ProviderCalendar.user_id == owner_id)).scalars().all()

    ensure_event_cache(db, owner_id, start_at, end_at, connections)
    db.commit()

    enabled_ids = [calendar.provider_calendar_id for calendar in calendars if calendar.is_enabled]
    if share.permission_level == "free_busy":
        busy_rows = db.execute(
            select(BusyCache.start_at, BusyCache.end_at, BusyCache.last_fetched_at)
            .where(BusyCache.user_id == owner_id)
            .where(BusyCache.start_at < end_at)
            .where(BusyCache.end_at > start_at)
        ).all()
        if is_cache_stale([row[2] for row in busy_rows]):
            refresh_busy_cache(db, owner_id, start_at, end_at, enabled_ids)
            db.commit()
            busy_rows = db.execute(
                select(BusyCache.start_at, BusyCache.end_at)
                .where(BusyCache.user_id == owner_id)
                .where(BusyCache.start_at < end_at)
                .where(BusyCache.end_at > start_at)
            ).all()
        return {"busy": [{"start_at": row[0], "end_at": row[1]} for row in busy_rows]}

    events = []
    if enabled_ids:
        events = db.execute(
            select(EventCache)
            .where(EventCache.user_id == owner_id)
            .where(EventCache.provider_calendar_id.in_(enabled_ids))
            .where(EventCache.start_at < end_at)
            .where(EventCache.end_at > start_at)
        ).scalars().all()
    payload = [
        {
            "start_at": event.start_at,
            "end_at": event.end_at,
            "is_all_day": event.is_all_day,
            "title": event.title,
            "location": event.location,
            "is_private": event.is_private,
        }
        for event in events
    ]
    return redact_events_for_permission(payload, share.permission_level)


@router.get("/calendars")
def list_calendars(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    calendars = db.execute(select(ProviderCalendar).where(ProviderCalendar.user_id == current_user.user_id)).scalars().all()
    if not calendars:
        connections = db.execute(
            select(CalendarConnection).where(CalendarConnection.user_id == current_user.user_id)
        ).scalars().all()
        for connection in connections:
            refresh_provider_calendars(db, connection)
        db.commit()
        calendars = db.execute(
            select(ProviderCalendar).where(ProviderCalendar.user_id == current_user.user_id)
        ).scalars().all()
    return {
        "calendars": [
            {
                "provider": calendar.provider,
                "provider_calendar_id": calendar.provider_calendar_id,
                "name": calendar.name,
                "is_primary": calendar.is_primary,
                "is_enabled": calendar.is_enabled,
                "color": calendar.color,
                "updated_at": calendar.updated_at,
            }
            for calendar in calendars
        ]
    }


@router.post("/calendars/toggle")
def toggle_calendar(
    payload: CalendarToggle,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    calendar = db.execute(
        select(ProviderCalendar).where(
            ProviderCalendar.user_id == current_user.user_id,
            ProviderCalendar.provider == payload.provider,
            ProviderCalendar.provider_calendar_id == payload.provider_calendar_id,
        )
    ).scalar_one_or_none()
    if not calendar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found")
    calendar.is_enabled = payload.is_enabled
    calendar.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.post("/shares")
def create_share(
    payload: CalendarShareCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    table = CalendarShare.__table__
    now = datetime.now(timezone.utc)
    stmt = insert(table).values(
        owner_id=current_user.user_id,
        viewer_id=payload.viewer_id,
        permission_level=payload.permission_level,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["owner_id", "viewer_id"],
        set_={
            "permission_level": stmt.excluded.permission_level,
            "updated_at": now,
        },
    )
    db.execute(stmt)
    db.commit()
    return {"ok": True}


@router.get("/shares")
def list_shares(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    outgoing = db.execute(
        select(CalendarShare).where(CalendarShare.owner_id == current_user.user_id)
    ).scalars().all()
    incoming = db.execute(
        select(CalendarShare).where(CalendarShare.viewer_id == current_user.user_id)
    ).scalars().all()
    return {
        "outgoing": [
            {
                "viewer_id": str(row.viewer_id),
                "permission_level": row.permission_level,
                "updated_at": row.updated_at,
            }
            for row in outgoing
        ],
        "incoming": [
            {
                "owner_id": str(row.owner_id),
                "permission_level": row.permission_level,
                "updated_at": row.updated_at,
            }
            for row in incoming
        ],
    }


@router.get("/connections")
def list_connections(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rows = db.execute(
        select(CalendarConnection).where(
            CalendarConnection.user_id == current_user.user_id,
            CalendarConnection.revoked_at.is_(None),
        )
    ).scalars().all()
    return {
        "connections": [
            {
                "provider": row.provider,
                "provider_account_id": row.provider_account_id,
                "provider_email": row.provider_email,
                "connected_at": row.created_at,
                "expires_at": row.expires_at,
                "scopes": row.scopes,
            }
            for row in rows
        ]
    }


@router.get("/google/connect")
def google_connect(
    return_to: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "google_oauth_not_configured",
                "message": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to enable Google connect.",
            },
        )
    state = _encode_state(current_user.user_id, return_to)
    return {"authorize_url": google.build_authorize_url(state), "state": state}


@router.get("/google/callback")
def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        decoded = _decode_state(state)
        user_id = uuid.UUID(decoded["uid"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid state") from exc

    return_to = decoded.get("return_to") or settings.app_base_url

    try:
        token_payload = google.exchange_code_for_tokens(code)
    except Exception as exc:  # pragma: no cover - integration path
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    access_token = token_payload.get("access_token")
    refresh_token = token_payload.get("refresh_token")
    expires_in = token_payload.get("expires_in")
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if isinstance(expires_in, (int, float))
        else None
    )
    scope = token_payload.get("scope")

    provider_account_id = None
    provider_email = None
    if access_token:
        try:
            info = google.fetch_userinfo(access_token)
            provider_account_id = info.get("sub")
            provider_email = info.get("email")
        except Exception:  # pragma: no cover - integration path
            pass

    profile_row = db.get(Profile, user_id)
    if profile_row is None:
        # dev-auth path: organizer profile row may not exist yet
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organizer not found")

    existing = db.execute(
        select(CalendarConnection).where(
            CalendarConnection.user_id == user_id,
            CalendarConnection.provider == "google",
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = CalendarConnection(
            user_id=user_id,
            provider="google",
            provider_account_id=provider_account_id or "",
            provider_email=provider_email,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes={"granted": scope} if scope else None,
            revoked_at=None,
        )
        db.add(existing)
    else:
        existing.provider_account_id = provider_account_id or existing.provider_account_id
        existing.provider_email = provider_email or existing.provider_email
        existing.access_token = access_token or existing.access_token
        if refresh_token:
            existing.refresh_token = refresh_token
        if expires_at:
            existing.expires_at = expires_at
        if scope:
            existing.scopes = {"granted": scope}
        existing.revoked_at = None

    db.commit()
    return RedirectResponse(url=f"{return_to}?google=connected", status_code=302)


@router.post("/google/disconnect")
def google_disconnect(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rows = db.execute(
        select(CalendarConnection).where(
            CalendarConnection.user_id == current_user.user_id,
            CalendarConnection.provider == "google",
            CalendarConnection.revoked_at.is_(None),
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.revoked_at = now
        row.access_token = None
        row.refresh_token = None
    db.commit()
    return {"ok": True, "revoked": len(rows)}
