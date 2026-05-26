from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

class ReminderPolicyPayload(BaseModel):
    initial_hours: int | None = Field(default=None, ge=1, le=720)
    followup_hours: int | None = Field(default=None, ge=1, le=720)
    max_per_participant: int | None = Field(default=None, ge=1, le=10)


class MeetingRequestCreate(BaseModel):
    title: str
    duration_min: int = Field(ge=5, le=480)
    timezone: str = "America/New_York"
    group_id: str | None = None
    event_type: str | None = None
    location: str | None = None
    video_link: str | None = None
    notes: str | None = None
    response_deadline: datetime | None = None
    reminders_enabled: bool = True
    reminder_policy: ReminderPolicyPayload | None = None


class ProposalCreate(BaseModel):
    rank: int = Field(ge=1, le=50)
    start_at: str
    score: float | None = None
    meta: dict | None = None


class ParticipantCreate(BaseModel):
    email: str | None = None
    phone: str | None = None
    display_name: str | None = None
    role: str = "attendee"


class ReminderSettingsUpdate(BaseModel):
    reminders_enabled: bool | None = None
    response_deadline: datetime | None = None
    reminder_policy: ReminderPolicyPayload | None = None


class SlotWindowPayload(BaseModel):
    start_minute: int = Field(ge=0, lt=1440)
    end_minute: int = Field(gt=0, le=1440)


class SuggestRequestPayload(BaseModel):
    start_date: str
    end_date: str
    days_of_week: list[int] | None = None
    time_windows: list[SlotWindowPayload] | None = None
    exclude_dates: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=10)
    replace_existing: bool = True
    mode: Literal["suggest", "preview"] = "suggest"
