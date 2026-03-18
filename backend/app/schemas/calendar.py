import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class CalendarToggle(BaseModel):
    provider: str
    provider_calendar_id: str
    is_enabled: bool


class CalendarShareCreate(BaseModel):
    viewer_id: uuid.UUID
    permission_level: Literal["none", "free_busy", "details"] = "free_busy"


class CalendarRangeQuery(BaseModel):
    start: datetime
    end: datetime


class CalendarEventOut(BaseModel):
    start_at: datetime
    end_at: datetime
    is_all_day: bool = False
    title: str | None = None
    location: str | None = None
    is_private: bool = False
    provider: str
    provider_calendar_id: str


class BusyIntervalOut(BaseModel):
    start_at: datetime
    end_at: datetime


class ProviderCalendarOut(BaseModel):
    provider: str
    provider_calendar_id: str
    name: str
    is_primary: bool = False
    is_enabled: bool = True
    color: str | None = None
    updated_at: datetime | None = None
