from pydantic import BaseModel, Field
from typing import Any, Dict

class MeetingRequestCreate(BaseModel):
    title: str
    duration_min: int = Field(ge=5, le=480)
    timezone: str = "America/New_York"
    window_start: str
    window_end: str
    constraints: Dict[str, Any] = Field(default_factory=dict)
