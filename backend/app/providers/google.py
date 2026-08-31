from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


REFRESH_BUFFER = timedelta(minutes=5)

# Event kinds that occupy a row in the events feed but are annotations rather
# than commitments, so they must never be treated as busy.
NON_BUSY_EVENT_TYPES = {"workingLocation", "birthday"}


class GoogleAuthError(RuntimeError):
    """Raised when a connection can no longer authenticate against Google."""


def build_authorize_url(state: str) -> str:
    """Return the Google OAuth consent URL the user is redirected to."""
    params = {
        "client_id": settings.google_client_id or "",
        "response_type": "code",
        "redirect_uri": settings.google_redirect_uri,
        "scope": settings.google_oauth_scopes,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{settings.google_oauth_authorize_url}?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise RuntimeError("Google OAuth client credentials are not configured")
    response = httpx.post(
        settings.google_oauth_token_url,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_userinfo(access_token: str) -> dict[str, Any]:
    response = httpx.get(
        settings.google_oauth_userinfo_url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    if not settings.google_client_id or not settings.google_client_secret:
        raise RuntimeError("Google OAuth client credentials are not configured")
    response = httpx.post(
        settings.google_oauth_token_url,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def revoke_token(token: str | None) -> bool:
    """Revoke a Google grant. True when Google accepted the revocation.

    Google answers 400 for a token that is already invalid; that is still the
    terminal state we wanted, so it counts as success.
    """
    if not token:
        return False
    try:
        response = httpx.post(
            settings.google_oauth_revoke_url,
            data={"token": token},
            timeout=20.0,
        )
    except httpx.HTTPError:
        logger.warning("Google token revocation call failed", exc_info=True)
        return False
    if response.status_code in (200, 400):
        return True
    logger.warning(
        "Google token revocation returned %s: %s", response.status_code, response.text[:200]
    )
    return False


def ensure_fresh_access_token(connection: Any) -> str | None:
    """Refresh the access token in place if it is near expiry.

    Returns the access token to use for the next call, or None if the
    connection is missing the credentials needed to refresh.
    """
    if not connection or not connection.access_token:
        return None
    expires_at = getattr(connection, "expires_at", None)
    if expires_at is not None and expires_at.tzinfo is None:
        # Defensive: a naive value would raise on the comparison below.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is None or expires_at - REFRESH_BUFFER > datetime.now(timezone.utc):
        return connection.access_token
    if not connection.refresh_token:
        return connection.access_token
    payload = refresh_access_token(connection.refresh_token)
    connection.access_token = payload.get("access_token", connection.access_token)
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)):
        connection.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    return connection.access_token


def list_calendars(connection: Any) -> list[dict[str, Any]]:
    if not connection or not connection.access_token:
        return []
    ensure_fresh_access_token(connection)
    calendars: list[dict[str, Any]] = []
    for item in _paginate(connection.access_token, "/users/me/calendarList"):
        if item.get("deleted"):
            continue
        calendars.append(
            {
                "provider_calendar_id": item["id"],
                "name": item.get("summary", "Calendar"),
                "is_primary": bool(item.get("primary", False)),
                # Google omits `selected` for calendars the user has hidden, so
                # the API default is False -- not True. Defaulting to True here
                # silently re-enabled every calendar the user had deselected.
                "is_enabled": bool(item.get("selected", False)) or bool(item.get("primary", False)),
                "color": item.get("backgroundColor"),
                "timezone": item.get("timeZone"),
            }
        )
    return calendars


def fetch_events(
    connection: Any,
    calendar_ids: list[str],
    time_min: datetime,
    time_max: datetime,
) -> list[dict[str, Any]]:
    """Return busy-relevant events across `calendar_ids` in [time_min, time_max).

    Cancelled, declined, and free-marked ("transparent") entries are dropped:
    they consume no time and must not block a suggested slot.
    """
    if not connection or not connection.access_token or not calendar_ids:
        return []

    ensure_fresh_access_token(connection)
    events: list[dict[str, Any]] = []
    for calendar_id in calendar_ids:
        # Google reports the calendar's own zone on each events page; all-day
        # entries are only interpretable relative to it.
        calendar_timezone: str | None = None

        def _capture_timezone(page: dict[str, Any]) -> None:
            nonlocal calendar_timezone
            calendar_timezone = calendar_timezone or page.get("timeZone")

        items = _paginate(
            connection.access_token,
            f"/calendars/{quote(calendar_id, safe='')}/events",
            params={
                "singleEvents": "true",
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "maxResults": "250",
                "orderBy": "startTime",
                "showDeleted": "false",
            },
            on_page=_capture_timezone,
        )

        for item in items:
            if not is_busy_event(item):
                continue
            start_at = _parse_google_datetime(item.get("start", {}), calendar_timezone)
            end_at = _parse_google_datetime(item.get("end", {}), calendar_timezone)
            if not start_at or not end_at or start_at >= end_at:
                continue
            events.append(
                {
                    "provider": "google",
                    "provider_event_id": item["id"],
                    "provider_calendar_id": calendar_id,
                    "start_at": start_at,
                    "end_at": end_at,
                    "is_all_day": "date" in item.get("start", {}),
                    "timezone": item.get("start", {}).get("timeZone")
                    or item.get("end", {}).get("timeZone")
                    or calendar_timezone,
                    "title": item.get("summary"),
                    "location": item.get("location"),
                    "is_private": item.get("visibility") == "private",
                    "etag": item.get("etag"),
                }
            )
    return events


def is_busy_event(item: dict[str, Any]) -> bool:
    """Whether a Google event actually consumes the user's time.

    Excludes cancelled instances, entries marked "Free"
    (`transparency: transparent`), events this user declined, and event kinds
    that are annotations rather than commitments.
    """
    if item.get("status") == "cancelled":
        return False
    if item.get("transparency") == "transparent":
        return False
    if item.get("eventType") in NON_BUSY_EVENT_TYPES:
        return False
    for attendee in item.get("attendees") or []:
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return False
    return True


def create_event(connection: Any, calendar_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not connection or not connection.access_token:
        return {}
    ensure_fresh_access_token(connection)
    return _google_request(
        connection.access_token,
        "POST",
        f"/calendars/{quote(calendar_id, safe='')}/events",
        params=_send_updates_params(payload),
        json=payload,
    )


def update_event(
    connection: Any, calendar_id: str, event_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Overwrite an event we previously created, so re-finalizing is idempotent."""
    if not connection or not connection.access_token:
        return {}
    ensure_fresh_access_token(connection)
    return _google_request(
        connection.access_token,
        "PUT",
        f"/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
        params=_send_updates_params(payload),
        json=payload,
    )


def get_event(connection: Any, calendar_id: str, event_id: str) -> dict[str, Any] | None:
    """Fetch one event, or None when it no longer exists."""
    if not connection or not connection.access_token:
        return None
    ensure_fresh_access_token(connection)
    try:
        return _google_request(
            connection.access_token,
            "GET",
            f"/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (404, 410):
            return None
        raise


def fetch_busy_intervals(
    connection: Any,
    calendar_ids: list[str],
    time_min: datetime,
    time_max: datetime,
) -> list[tuple[datetime, datetime]]:
    """Return busy intervals from the given calendars over the window.

    Intervals come back as-is (unsorted, possibly overlapping); callers that
    care collapse them with `app.services.calendar.merge_intervals`.
    """
    events = fetch_events(connection, calendar_ids, time_min, time_max)
    intervals: list[tuple[datetime, datetime]] = []
    for event in events:
        start = event.get("start_at")
        end = event.get("end_at")
        if isinstance(start, datetime) and isinstance(end, datetime) and start < end:
            intervals.append((start, end))
    return intervals


def _send_updates_params(payload: dict[str, Any]) -> dict[str, str]:
    return {"sendUpdates": "all" if payload.get("attendees") else "none"}


def _paginate(
    access_token: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    on_page: Any = None,
) -> list[dict[str, Any]]:
    """Follow Google's `nextPageToken` so a full window is never truncated."""
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    for _ in range(max(1, settings.google_max_pages)):
        page_params = dict(params or {})
        if page_token:
            page_params["pageToken"] = page_token
        page = _google_request(access_token, "GET", path, params=page_params)
        if on_page is not None:
            on_page(page)
        items.extend(page.get("items", []))
        page_token = page.get("nextPageToken")
        if not page_token:
            return items
    logger.warning(
        "Google pagination hit the %s-page cap for %s; results may be incomplete",
        settings.google_max_pages,
        path,
    )
    return items


def _google_request(
    access_token: str,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{settings.google_api_base_url}{path}"
    response = httpx.request(
        method,
        url,
        params=params,
        json=json,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20.0,
    )
    if response.status_code in (401, 403):
        raise GoogleAuthError(
            f"Google rejected the credentials for {method} {path} ({response.status_code})"
        )
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def _parse_google_datetime(
    value: dict[str, Any], calendar_timezone: str | None = None
) -> datetime | None:
    raw = value.get("dateTime")
    if raw:
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_zone(value.get("timeZone") or calendar_timezone))
        return parsed
    all_day = value.get("date")
    if all_day:
        # An all-day event runs midnight-to-midnight in the *calendar's* zone,
        # not in UTC. Anchoring it to UTC shifted it by the offset, so a US
        # all-day event blocked the wrong 24 hours.
        zone = _zone(value.get("timeZone") or calendar_timezone)
        return datetime.combine(date.fromisoformat(all_day), datetime.min.time(), tzinfo=zone)
    return None


def _zone(timezone_name: str | None):
    if not timezone_name:
        return timezone.utc
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc
