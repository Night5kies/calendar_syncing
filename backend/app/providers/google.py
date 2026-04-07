from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings


def list_calendars(connection: Any) -> list[dict[str, Any]]:
    if not connection or not connection.access_token:
        return []
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
    return _google_request(
        connection.access_token,
        "POST",
        f"/calendars/{quote(calendar_id, safe='')}/events",
        json=payload,
    )


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
