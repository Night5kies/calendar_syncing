from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.core.config import settings


REFRESH_BUFFER = timedelta(minutes=5)


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


def ensure_fresh_access_token(connection: Any) -> str | None:
    """Refresh the access token in place if it is near expiry.

    Returns the access token to use for the next call, or None if the
    connection is missing the credentials needed to refresh.
    """
    if not connection or not connection.access_token:
        return None
    expires_at = getattr(connection, "expires_at", None)
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
    response = _google_request(connection.access_token, "GET", "/users/me/calendarList")
    items = response.get("items", [])
    return [
        {
            "provider_calendar_id": item["id"],
            "name": item.get("summary", "Calendar"),
            "is_primary": item.get("primary", False),
            "is_enabled": item.get("selected", True),
            "color": item.get("backgroundColor"),
        }
        for item in items
    ]


def fetch_events(
    connection: Any,
    calendar_ids: list[str],
    time_min: datetime,
    time_max: datetime,
) -> list[dict[str, Any]]:
    if not connection or not connection.access_token or not calendar_ids:
        return []

    ensure_fresh_access_token(connection)
    events: list[dict[str, Any]] = []
    for calendar_id in calendar_ids:
        response = _google_request(
            connection.access_token,
            "GET",
            f"/calendars/{quote(calendar_id, safe='')}/events",
            params={
                "singleEvents": "true",
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "maxResults": "250",
                "orderBy": "startTime",
            },
        )
        for item in response.get("items", []):
            start_at = _parse_google_datetime(item.get("start", {}))
            end_at = _parse_google_datetime(item.get("end", {}))
            if not start_at or not end_at:
                continue
            events.append(
                {
                    "provider": "google",
                    "provider_event_id": item["id"],
                    "provider_calendar_id": calendar_id,
                    "start_at": start_at,
                    "end_at": end_at,
                    "is_all_day": "date" in item.get("start", {}),
                    "timezone": item.get("start", {}).get("timeZone") or item.get("end", {}).get("timeZone"),
                    "title": item.get("summary"),
                    "location": item.get("location"),
                    "is_private": item.get("visibility") == "private",
                    "etag": item.get("etag"),
                }
            )
    return events


def create_event(connection: Any, calendar_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not connection or not connection.access_token:
        return {}
    ensure_fresh_access_token(connection)
    return _google_request(
        connection.access_token,
        "POST",
        f"/calendars/{quote(calendar_id, safe='')}/events",
        json=payload,
    )


def fetch_busy_intervals(
    connection: Any,
    calendar_ids: list[str],
    time_min: datetime,
    time_max: datetime,
) -> list[tuple[datetime, datetime]]:
    """Return merged busy intervals from the given calendars over the window."""
    events = fetch_events(connection, calendar_ids, time_min, time_max)
    intervals: list[tuple[datetime, datetime]] = []
    for event in events:
        start = event.get("start_at")
        end = event.get("end_at")
        if isinstance(start, datetime) and isinstance(end, datetime) and start < end:
            intervals.append((start, end))
    return intervals


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
    response.raise_for_status()
    return response.json()


def _parse_google_datetime(value: dict[str, Any]) -> datetime | None:
    raw = value.get("dateTime")
    if raw:
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    all_day = value.get("date")
    if all_day:
        return datetime.fromisoformat(f"{all_day}T00:00:00+00:00")
    return None
