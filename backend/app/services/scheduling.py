"""Slot generation for `POST /v1/requests/{id}/suggest`.

Generates candidate start times at 15-minute increments, intersected against:
- a date range (inclusive),
- an allowed list of weekdays (Monday=0..Sunday=6),
- caller-supplied time-of-day windows (minutes from midnight in the request timezone),
- the organizer's saved availability rule (weekly hours) if present,
- a set of "blocked" intervals (organizer's `AvailabilityBlock` rows, plus
  optional external busy windows fed in by the caller),
- a set of exclude dates.

The generator is deterministic: same inputs in, same ranked output. Scoring is
intentionally simple — earlier dates win, template-aligned windows win, and
slots fully inside the organizer's rule win. Reasons are surfaced through the
proposal `meta` field so the UI can render a one-liner per suggestion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.availability_block import AvailabilityBlock
from app.models.availability_rule import AvailabilityRule
from app.models.meeting_request import MeetingRequest
from app.models.proposal import Proposal


SLOT_INCREMENT_MINUTES = 15
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

TEMPLATE_WINDOWS: dict[str, tuple[tuple[int, int], ...]] = {
    "meal": ((12 * 60, 14 * 60), (18 * 60, 20 * 60 + 30)),
    "coffee": ((8 * 60, 11 * 60), (15 * 60, 17 * 60)),
    "study": ((9 * 60, 12 * 60), (13 * 60, 18 * 60)),
    "hangout": ((16 * 60, 22 * 60),),
}


@dataclass(frozen=True)
class TimeWindow:
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if not (0 <= self.start_minute < self.end_minute <= 1440):
            raise ValueError("time window must satisfy 0 <= start < end <= 1440")


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class SuggestionInputs:
    start_date: date
    end_date: date
    duration_min: int
    timezone: str
    event_type: str | None = None
    days_of_week: tuple[int, ...] | None = None
    time_windows: tuple[TimeWindow, ...] = ()
    exclude_dates: tuple[date, ...] = ()
    limit: int = 5


@dataclass
class Suggestion:
    start_at: datetime
    end_at: datetime
    score: float
    reasons: list[str] = field(default_factory=list)


# --- helpers ----------------------------------------------------------------


def _ensure_aware(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _windows_for_template(event_type: str | None) -> tuple[TimeWindow, ...]:
    if not event_type:
        return ()
    raw = TEMPLATE_WINDOWS.get(event_type.lower())
    if not raw:
        return ()
    return tuple(TimeWindow(start_minute=start, end_minute=end) for start, end in raw)


def _weekly_rule_windows(rule: AvailabilityRule | None, weekday: int) -> tuple[TimeWindow, ...]:
    if rule is None:
        return ()
    weekly = rule.weekly_hours or {}
    key = WEEKDAY_KEYS[weekday]
    raw_windows = weekly.get(key) or []
    windows: list[TimeWindow] = []
    for entry in raw_windows:
        try:
            start_h, start_m = (int(part) for part in str(entry["start"]).split(":"))
            end_h, end_m = (int(part) for part in str(entry["end"]).split(":"))
        except (KeyError, ValueError):
            continue
        start_minute = start_h * 60 + start_m
        end_minute = end_h * 60 + end_m
        if 0 <= start_minute < end_minute <= 1440:
            windows.append(TimeWindow(start_minute=start_minute, end_minute=end_minute))
    return tuple(windows)


def _intersect_windows(
    primary: Sequence[TimeWindow], secondary: Sequence[TimeWindow]
) -> tuple[TimeWindow, ...]:
    if not primary:
        return tuple(secondary)
    if not secondary:
        return tuple(primary)
    out: list[TimeWindow] = []
    for left in primary:
        for right in secondary:
            start = max(left.start_minute, right.start_minute)
            end = min(left.end_minute, right.end_minute)
            if start < end:
                out.append(TimeWindow(start_minute=start, end_minute=end))
    return tuple(out)


def _overlaps_blocked(start: datetime, end: datetime, blocked: Sequence[Interval]) -> bool:
    for interval in blocked:
        if start < interval.end and end > interval.start:
            return True
    return False


def _iter_candidate_starts(
    day: date,
    duration_min: int,
    windows: Sequence[TimeWindow],
    tz: ZoneInfo,
) -> Iterable[datetime]:
    duration = timedelta(minutes=duration_min)
    for window in windows:
        cursor_minute = window.start_minute
        if cursor_minute % SLOT_INCREMENT_MINUTES != 0:
            cursor_minute += SLOT_INCREMENT_MINUTES - (cursor_minute % SLOT_INCREMENT_MINUTES)
        latest_start_minute = window.end_minute - duration_min
        while cursor_minute <= latest_start_minute:
            hours, minutes = divmod(cursor_minute, 60)
            start_local = datetime.combine(day, time(hour=hours, minute=minutes), tzinfo=tz)
            yield start_local
            cursor_minute += SLOT_INCREMENT_MINUTES


# --- public API -------------------------------------------------------------


def load_organizer_constraints(
    db: Session, organizer_id: uuid.UUID, start_at: datetime, end_at: datetime
) -> tuple[AvailabilityRule | None, list[Interval]]:
    rule = (
        db.execute(select(AvailabilityRule).where(AvailabilityRule.user_id == organizer_id))
        .scalars()
        .first()
    )
    block_rows = db.execute(
        select(AvailabilityBlock.start_at, AvailabilityBlock.end_at)
        .where(AvailabilityBlock.user_id == organizer_id)
        .where(AvailabilityBlock.start_at < end_at)
        .where(AvailabilityBlock.end_at > start_at)
    ).all()
    intervals = [Interval(start=row[0], end=row[1]) for row in block_rows]
    return rule, intervals


def generate_suggestions(
    inputs: SuggestionInputs,
    *,
    organizer_rule: AvailabilityRule | None = None,
    blocked_intervals: Sequence[Interval] = (),
) -> list[Suggestion]:
    if inputs.start_date > inputs.end_date:
        raise ValueError("start_date must be on or before end_date")
    if inputs.duration_min <= 0:
        raise ValueError("duration_min must be positive")

    tz = ZoneInfo(inputs.timezone)
    template_windows = _windows_for_template(inputs.event_type)
    explicit_windows = tuple(inputs.time_windows)
    allowed_weekdays = (
        set(inputs.days_of_week) if inputs.days_of_week is not None else set(range(7))
    )
    excluded_dates = set(inputs.exclude_dates)
    duration = timedelta(minutes=inputs.duration_min)

    aware_blocks: list[Interval] = []
    for interval in blocked_intervals:
        start = _ensure_aware(interval.start, tz)
        end = _ensure_aware(interval.end, tz)
        if start < end:
            aware_blocks.append(Interval(start=start, end=end))

    suggestions: list[Suggestion] = []
    day = inputs.start_date
    day_index = 0
    while day <= inputs.end_date:
        if day in excluded_dates or day.weekday() not in allowed_weekdays:
            day = day + timedelta(days=1)
            day_index += 1
            continue

        rule_windows = _weekly_rule_windows(organizer_rule, day.weekday())
        base_windows: tuple[TimeWindow, ...]
        if explicit_windows:
            base_windows = explicit_windows
        elif template_windows:
            base_windows = template_windows
        elif rule_windows:
            base_windows = rule_windows
        else:
            base_windows = (TimeWindow(start_minute=9 * 60, end_minute=18 * 60),)

        effective_windows = _intersect_windows(base_windows, rule_windows) if rule_windows else base_windows

        for start_local in _iter_candidate_starts(day, inputs.duration_min, effective_windows, tz):
            end_local = start_local + duration
            if _overlaps_blocked(start_local, end_local, aware_blocks):
                continue

            reasons: list[str] = []
            score = max(0.0, 1.0 - (day_index * 0.05))
            if template_windows and any(
                window.start_minute <= (start_local.hour * 60 + start_local.minute) < window.end_minute
                for window in template_windows
            ):
                reasons.append(f"Aligned with {inputs.event_type} window")
                score += 0.25
            if rule_windows:
                reasons.append("Inside your weekly availability")
                score += 0.15
            if not rule_windows and organizer_rule is None:
                reasons.append("Default working-hours window (no availability set)")
            reasons.append(f"Day {day_index + 1} of range")

            suggestions.append(
                Suggestion(
                    start_at=start_local,
                    end_at=end_local,
                    score=round(score, 4),
                    reasons=reasons,
                )
            )

        day = day + timedelta(days=1)
        day_index += 1

    suggestions.sort(key=lambda item: (-item.score, item.start_at))

    # de-dupe overlapping suggestions inside the same day
    deduped: list[Suggestion] = []
    chosen_intervals: list[tuple[datetime, datetime]] = []
    for suggestion in suggestions:
        if any(
            suggestion.start_at < end and suggestion.end_at > start
            for start, end in chosen_intervals
        ):
            continue
        deduped.append(suggestion)
        chosen_intervals.append((suggestion.start_at, suggestion.end_at))
        if len(deduped) >= inputs.limit:
            break
    return deduped


def materialize_suggestions(
    db: Session,
    meeting_request: MeetingRequest,
    suggestions: Sequence[Suggestion],
    *,
    replace_existing: bool = True,
) -> list[Proposal]:
    if replace_existing:
        existing = (
            db.execute(select(Proposal).where(Proposal.meeting_request_id == meeting_request.id))
            .scalars()
            .all()
        )
        for proposal in existing:
            db.delete(proposal)
        db.flush()

    new_proposals: list[Proposal] = []
    for index, suggestion in enumerate(suggestions, start=1):
        proposal = Proposal(
            meeting_request_id=meeting_request.id,
            rank=index,
            start_at=suggestion.start_at,
            score=suggestion.score,
            meta={
                "reasons": suggestion.reasons,
                "generator": "scheduling.v1",
            },
        )
        db.add(proposal)
        new_proposals.append(proposal)
    return new_proposals


def parse_inputs_from_payload(
    payload_dict: dict,
    *,
    meeting_request: MeetingRequest,
) -> SuggestionInputs:
    raw_start = payload_dict.get("start_date")
    raw_end = payload_dict.get("end_date")
    if not raw_start or not raw_end:
        raise ValueError("start_date and end_date are required")

    days = payload_dict.get("days_of_week")
    weekdays: tuple[int, ...] | None
    if days is None:
        weekdays = None
    else:
        weekdays = tuple(sorted(int(day) for day in days if 0 <= int(day) <= 6))
        if not weekdays:
            raise ValueError("days_of_week must include at least one weekday")

    raw_windows = payload_dict.get("time_windows") or []
    windows = tuple(
        TimeWindow(start_minute=int(item["start_minute"]), end_minute=int(item["end_minute"]))
        for item in raw_windows
    )

    raw_excludes = payload_dict.get("exclude_dates") or []
    excludes = tuple(_parse_date(value) for value in raw_excludes)

    return SuggestionInputs(
        start_date=_parse_date(raw_start),
        end_date=_parse_date(raw_end),
        duration_min=meeting_request.duration_min,
        timezone=meeting_request.timezone,
        event_type=meeting_request.event_type,
        days_of_week=weekdays,
        time_windows=windows,
        exclude_dates=excludes,
        limit=int(payload_dict.get("limit", 5)),
    )
