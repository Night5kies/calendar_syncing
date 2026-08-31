from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence


FRESHNESS_MINUTES = 10


def freshness_threshold(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - timedelta(minutes=FRESHNESS_MINUTES)


def is_window_stale(
    markers: Sequence[tuple[datetime, datetime, datetime]],
    start_at: datetime,
    end_at: datetime,
    now: datetime | None = None,
) -> bool:
    """Whether [start_at, end_at) needs a re-fetch.

    `markers` are `(window_start, window_end, last_synced_at)` rows. The window
    is fresh when some marker both covers the requested range and was synced
    inside the freshness horizon. This is what makes an empty window cacheable:
    the marker exists even when the sync returned zero events.
    """
    threshold = freshness_threshold(now)
    for window_start, window_end, last_synced_at in markers:
        if last_synced_at < threshold:
            continue
        if window_start <= start_at and window_end >= end_at:
            return False
    return True


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
