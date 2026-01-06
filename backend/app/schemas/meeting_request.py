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
