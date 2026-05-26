from datetime import datetime

from pydantic import BaseModel, Field

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
