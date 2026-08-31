import base64
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.db.deps import get_db
from app.models.availability_block import AvailabilityBlock
from app.models.busy_cache import BusyCache
from app.models.calendar_connection import CalendarConnection
from app.models.calendar_share import CalendarShare
from app.models.calendar_sync_state import CalendarSyncState
from app.models.event_cache import EventCache
from app.models.profile import Profile
from app.models.provider_calendar import ProviderCalendar
from app.providers import google
from app.schemas.calendar import CalendarShareCreate, CalendarToggle
from app.services.calendar import (
    is_window_stale,
    merge_intervals,
    redact_events_for_permission,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar")


# --- OAuth state ------------------------------------------------------------
#
# The state parameter carries the SYZY user id across the Google round trip.
# It is HMAC-signed and time-boxed: an unsigned state let anyone bind their own
# Google account to another user's SYZY account (or the reverse) simply by
# editing the base64 payload before hitting the callback.


def _state_signature(payload: bytes) -> str:
    digest = hmac.new(
        settings.supabase_jwt_secret.encode(), payload, hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode())


def _encode_state(user_id: uuid.UUID, return_to: str | None) -> str:
    raw = json.dumps(
        {
            "uid": str(user_id),
            "nonce": secrets.token_urlsafe(16),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "return_to": sanitize_return_to(return_to),
        }
    ).encode()
    payload = _b64encode(raw)
    return f"{payload}.{_state_signature(raw)}"


def _decode_state(state: str) -> dict:
    """Verify and decode an OAuth state parameter.

    Raises ValueError when the signature is missing, forged, or expired.
    """
    payload, _, signature = state.partition(".")
    if not payload or not signature:
        raise ValueError("state is not signed")
    raw = _b64decode(payload)
    if not hmac.compare_digest(signature, _state_signature(raw)):
        raise ValueError("state signature mismatch")
    decoded = json.loads(raw)
    issued_at = decoded.get("iat")
    if not isinstance(issued_at, int):
        raise ValueError("state is missing an issue time")
    age = datetime.now(timezone.utc).timestamp() - issued_at
    if age < -60 or age > settings.oauth_state_ttl_seconds:
        raise ValueError("state has expired")
    return decoded


def sanitize_return_to(return_to: str | None) -> str:
    """Confine the post-callback redirect to origins we control.

    Without this the `return_to` inside `state` turned the callback into an
    open redirect.
    """
    fallback = settings.app_base_url
    if not return_to:
        return fallback
    try:
        parsed = urlparse(return_to)
    except ValueError:
        return fallback
    if not parsed.scheme or not parsed.netloc:
        return fallback
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if origin not in settings.allowed_return_to_origins:
        logger.warning("Rejected out-of-allowlist OAuth return_to origin %s", origin)
        return fallback
    return return_to


# --- helpers ----------------------------------------------------------------


def parse_iso(value: str) -> datetime:
    """Parse a caller-supplied ISO timestamp into an aware datetime."""
    raw = value
    if raw.endswith("Z"):
        raw = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid timestamp: {value}",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_window(start: str, end: str) -> tuple[datetime, datetime]:
    """Validate a read window, rejecting inverted or unbounded ranges."""
    start_at = parse_iso(start)
    end_at = parse_iso(end)
    if start_at >= end_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid range")
    if end_at - start_at > timedelta(days=settings.calendar_max_window_days):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Range exceeds the {settings.calendar_max_window_days}-day maximum",
        )
    return start_at, end_at


def active_connections(db: Session, user_id: uuid.UUID) -> list[CalendarConnection]:
    """Connections that are still authorized.

    Revoked rows must be excluded everywhere: after a disconnect their cached
    events would otherwise keep being served and shared.
    """
    return list(
        db.execute(
            select(CalendarConnection).where(
                CalendarConnection.user_id == user_id,
                CalendarConnection.revoked_at.is_(None),
            )
        )
        .scalars()
        .all()
    )


def get_enabled_calendar_ids(calendars: list[ProviderCalendar], provider: str) -> list[str]:
    return [
        calendar.provider_calendar_id
        for calendar in calendars
        if calendar.provider == provider and calendar.is_enabled
    ]


def refresh_provider_calendars(db: Session, connection: CalendarConnection) -> None:
    try:
        calendars = google.list_calendars(connection) if connection.provider == "google" else []
    except Exception:
        logger.warning(
            "Failed to list %s calendars for user %s",
            connection.provider,
            connection.user_id,
            exc_info=True,
        )
        return
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
                # `is_enabled` is deliberately not refreshed from the provider:
                # it is the user's own toggle (POST /calendar/calendars/toggle)
                # and syncing it back would silently undo their choice.
                "color": stmt.excluded.color,
                "updated_at": now,
            },
        )
        db.execute(stmt)


def sync_event_cache(
    db: Session,
    user_id: uuid.UUID,
    provider: str,
    calendar_ids: list[str],
    start_at: datetime,
    end_at: datetime,
    events: list[dict[str, object]],
) -> None:
    """Make the cached window match the provider exactly.

    Upserting alone left deleted and rescheduled events behind forever (the
    conflict key includes start/end, so a moved event wrote a second row), and
    those ghosts kept blocking real slots. Anything in the window that the
    provider no longer reports is dropped.
    """
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

    # Every row the provider still reports was just stamped with `now`, so
    # anything older in this window is an event that was deleted or moved.
    db.execute(
        delete(EventCache)
        .where(EventCache.user_id == user_id)
        .where(EventCache.provider == provider)
        .where(EventCache.provider_calendar_id.in_(calendar_ids))
        .where(EventCache.start_at < end_at)
        .where(EventCache.end_at > start_at)
        .where(EventCache.last_fetched_at < now)
    )


def record_sync_window(
    db: Session, user_id: uuid.UUID, provider: str, start_at: datetime, end_at: datetime
) -> None:
    """Mark a window as synced so an empty result is cacheable."""
    now = datetime.now(timezone.utc)
    stmt = insert(CalendarSyncState.__table__).values(
        id=uuid.uuid4(),
        user_id=user_id,
        provider=provider,
        window_start=start_at,
        window_end=end_at,
        last_synced_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "provider", "window_start", "window_end"],
        set_={"last_synced_at": now},
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
    # The session runs with autoflush=False, so without this an in-request read
    # of BusyCache would still see the pre-rebuild rows.
    db.flush()


def ensure_event_cache(
    db: Session,
    user_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    connections: list[CalendarConnection],
) -> list[str]:
    """Refresh the cached events for every connection, then rebuild busy once.

    Returns the enabled calendar ids across all providers. The busy rebuild is
    deliberately outside the per-connection loop: it clears the whole window
    before rewriting it, so running it per connection made the last provider
    erase every earlier provider's busy blocks.
    """
    calendars = (
        db.execute(select(ProviderCalendar).where(ProviderCalendar.user_id == user_id))
        .scalars()
        .all()
    )
    all_enabled_ids: list[str] = []

    for connection in connections:
        enabled_ids = get_enabled_calendar_ids(list(calendars), connection.provider)
        if not enabled_ids:
            continue
        all_enabled_ids.extend(enabled_ids)

        markers = db.execute(
            select(
                CalendarSyncState.window_start,
                CalendarSyncState.window_end,
                CalendarSyncState.last_synced_at,
            )
            .where(CalendarSyncState.user_id == user_id)
            .where(CalendarSyncState.provider == connection.provider)
            .where(CalendarSyncState.window_start <= start_at)
            .where(CalendarSyncState.window_end >= end_at)
        ).all()
        if not is_window_stale([(row[0], row[1], row[2]) for row in markers], start_at, end_at):
            continue

        try:
            events = (
                google.fetch_events(connection, enabled_ids, start_at, end_at)
                if connection.provider == "google"
                else []
            )
        except Exception:
            # A provider outage must not take the endpoint down: serve whatever
            # is already cached and try again on the next request.
            logger.warning(
                "Calendar sync failed for user %s provider %s; serving cached data",
                user_id,
                connection.provider,
                exc_info=True,
            )
            continue

        sync_event_cache(
            db, user_id, connection.provider, enabled_ids, start_at, end_at, events
        )
        record_sync_window(db, user_id, connection.provider, start_at, end_at)

    refresh_busy_cache(db, user_id, start_at, end_at, all_enabled_ids)
    return all_enabled_ids


def load_calendars(db: Session, user_id: uuid.UUID) -> list[ProviderCalendar]:
    """Provider calendars for a user, discovering them on first use."""
    calendars = (
        db.execute(select(ProviderCalendar).where(ProviderCalendar.user_id == user_id))
        .scalars()
        .all()
    )
    if calendars:
        return list(calendars)
    connections = active_connections(db, user_id)
    if not connections:
        return []
    for connection in connections:
        refresh_provider_calendars(db, connection)
    db.commit()
    return list(
        db.execute(select(ProviderCalendar).where(ProviderCalendar.user_id == user_id))
        .scalars()
        .all()
    )


# --- routes -----------------------------------------------------------------


@router.get("/events")
def get_events(
    start: str = Query(...),
    end: str = Query(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    start_at, end_at = parse_window(start, end)

    connections = active_connections(db, current_user.user_id)
    calendars = load_calendars(db, current_user.user_id)

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

    start_at, end_at = parse_window(start, end)

    connections = active_connections(db, owner_id)
    calendars = load_calendars(db, owner_id)

    enabled_ids = ensure_event_cache(db, owner_id, start_at, end_at, connections)
    db.commit()

    if share.permission_level == "free_busy":
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
    calendars = load_calendars(db, current_user.user_id)
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
    # The enabled set drives every cached read, so force a re-sync rather than
    # serving a window computed from the previous selection.
    db.execute(
        delete(CalendarSyncState).where(
            CalendarSyncState.user_id == current_user.user_id,
            CalendarSyncState.provider == payload.provider,
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/shares")
def create_share(
    payload: CalendarShareCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if payload.viewer_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot share a calendar with yourself",
        )
    if db.get(Profile, payload.viewer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Viewer not found")

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
    rows = active_connections(db, current_user.user_id)
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
        # Covers a forged signature, an expired state, and a malformed payload.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid state") from exc

    return_to = sanitize_return_to(decoded.get("return_to"))

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
            logger.warning("Google userinfo lookup failed during callback", exc_info=True)

    profile_row = db.get(Profile, user_id)
    if profile_row is None:
        # dev-auth path: organizer profile row may not exist yet
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organizer not found")

    existing = (
        db.execute(
            select(CalendarConnection)
            .where(CalendarConnection.user_id == user_id)
            .where(CalendarConnection.provider == "google")
            .where(
                or_(
                    CalendarConnection.provider_account_id == (provider_account_id or ""),
                    CalendarConnection.provider_account_id == "",
                )
            )
            .order_by(CalendarConnection.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

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

    # A reconnect may land on a different account or a changed calendar set, so
    # discard the previous sync markers and re-read on the next request.
    db.execute(
        delete(CalendarSyncState).where(
            CalendarSyncState.user_id == user_id,
            CalendarSyncState.provider == "google",
        )
    )
    db.commit()
    return RedirectResponse(url=f"{return_to}?google=connected", status_code=302)


@router.post("/google/disconnect")
def google_disconnect(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Revoke the Google grant and purge everything it produced.

    Nulling the local tokens is not enough on its own: the grant stays live at
    Google, and the cached events/busy blocks keep being served (and shared via
    /calendar/overlay) long after the user disconnected.
    """
    rows = db.execute(
        select(CalendarConnection).where(
            CalendarConnection.user_id == current_user.user_id,
            CalendarConnection.provider == "google",
            CalendarConnection.revoked_at.is_(None),
        )
    ).scalars().all()

    now = datetime.now(timezone.utc)
    revoked_upstream = 0
    for row in rows:
        # Revoking the refresh token invalidates the whole grant; fall back to
        # the access token when no refresh token was ever issued.
        if google.revoke_token(row.refresh_token or row.access_token):
            revoked_upstream += 1
        row.revoked_at = now
        row.access_token = None
        row.refresh_token = None

    calendar_ids = list(
        db.execute(
            select(ProviderCalendar.provider_calendar_id).where(
                ProviderCalendar.user_id == current_user.user_id,
                ProviderCalendar.provider == "google",
            )
        )
        .scalars()
        .all()
    )
    if calendar_ids:
        db.execute(
            delete(EventCache).where(
                EventCache.user_id == current_user.user_id,
                EventCache.provider == "google",
                EventCache.provider_calendar_id.in_(calendar_ids),
            )
        )
    db.execute(
        delete(ProviderCalendar).where(
            ProviderCalendar.user_id == current_user.user_id,
            ProviderCalendar.provider == "google",
        )
    )
    db.execute(
        delete(CalendarSyncState).where(
            CalendarSyncState.user_id == current_user.user_id,
            CalendarSyncState.provider == "google",
        )
    )
    # Busy blocks are derived, so rebuild them from what is left (manual
    # availability blocks and any other provider) rather than dropping them.
    db.execute(delete(BusyCache).where(BusyCache.user_id == current_user.user_id))
    remaining = active_connections(db, current_user.user_id)
    remaining_calendars = (
        db.execute(
            select(ProviderCalendar).where(ProviderCalendar.user_id == current_user.user_id)
        )
        .scalars()
        .all()
    )
    remaining_ids = [
        calendar.provider_calendar_id
        for calendar in remaining_calendars
        if calendar.is_enabled
        and any(connection.provider == calendar.provider for connection in remaining)
    ]
    horizon_start = now - timedelta(days=settings.calendar_max_window_days)
    horizon_end = now + timedelta(days=settings.calendar_max_window_days)
    refresh_busy_cache(db, current_user.user_id, horizon_start, horizon_end, remaining_ids)

    db.commit()
    return {"ok": True, "revoked": len(rows), "revoked_upstream": revoked_upstream}
