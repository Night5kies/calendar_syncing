from datetime import datetime
from typing import Any


def list_calendars(connection: Any) -> list[dict[str, Any]]:
    if not connection or not connection.access_token:
        return []
    # TODO: Implement Google Calendar API list call.
    return []


def fetch_events(
    connection: Any,
    calendar_ids: list[str],
    time_min: datetime,
    time_max: datetime,
) -> list[dict[str, Any]]:
    if not connection or not connection.access_token or not calendar_ids:
        return []
    # TODO: Implement Google Calendar API events list call and normalization.
    return []
