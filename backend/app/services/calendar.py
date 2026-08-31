from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable


FRESHNESS_MINUTES = 10


def is_cache_stale(last_fetched_at_values: Iterable[datetime]) -> bool:
    threshold = datetime.now(timezone.utc) - timedelta(minutes=FRESHNESS_MINUTES)
    values = list(last_fetched_at_values)
    if not values:
        return True
    return any(value < threshold for value in values)


def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda item: item[0])
    merged = [intervals[0]]
    for start_at, end_at in intervals[1:]:
        last_start, last_end = merged[-1]
        if start_at <= last_end:
            merged[-1] = (last_start, max(last_end, end_at))
        else:
            merged.append((start_at, end_at))
    return merged


def redact_events_for_permission(
    events: list[dict[str, object]], permission_level: str
) -> dict[str, list[dict[str, object]]]:
    if permission_level == "free_busy":
        return {
            "busy": [
                {"start_at": event["start_at"], "end_at": event["end_at"]}
                for event in events
            ]
        }
    if permission_level == "details":
        redacted = []
        busy = []
        for event in events:
            if event.get("is_private"):
                busy.append({"start_at": event["start_at"], "end_at": event["end_at"]})
            else:
                redacted.append(
                    {
                        "start_at": event["start_at"],
                        "end_at": event["end_at"],
                        "is_all_day": event.get("is_all_day", False),
                        "title": event.get("title"),
                        "location": event.get("location"),
                    }
                )
        return {"events": redacted, "busy": busy}
    return {"busy": []}
