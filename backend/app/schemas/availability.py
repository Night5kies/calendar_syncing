from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class DailyWindow(BaseModel):
    start: str = Field(description="HH:MM, 24h")
    end: str = Field(description="HH:MM, 24h, exclusive")

    @field_validator("start", "end")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("expected HH:MM")
        hours, minutes = parts
        if not (hours.isdigit() and minutes.isdigit()):
            raise ValueError("expected HH:MM")
        if not (0 <= int(hours) <= 23):
            raise ValueError("hour out of range")
        if not (0 <= int(minutes) <= 59):
            raise ValueError("minute out of range")
        return f"{int(hours):02d}:{int(minutes):02d}"

    @model_validator(mode="after")
    def _validate_order(self) -> "DailyWindow":
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class WeeklyHoursPayload(BaseModel):
    mon: list[DailyWindow] = Field(default_factory=list)
    tue: list[DailyWindow] = Field(default_factory=list)
    wed: list[DailyWindow] = Field(default_factory=list)
    thu: list[DailyWindow] = Field(default_factory=list)
    fri: list[DailyWindow] = Field(default_factory=list)
    sat: list[DailyWindow] = Field(default_factory=list)
    sun: list[DailyWindow] = Field(default_factory=list)


class AvailabilityRuleUpsert(BaseModel):
    timezone: str = Field(default="America/New_York", min_length=1, max_length=64)
    weekly_hours: WeeklyHoursPayload


class AvailabilityRuleRead(BaseModel):
    id: str
    timezone: str
    weekly_hours: dict
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AvailabilityBlockCreate(BaseModel):
    start_at: datetime
    end_at: datetime
    type: Literal["busy", "private", "ooo"] = "private"

    @model_validator(mode="after")
    def _validate_order(self) -> "AvailabilityBlockCreate":
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        return self


class AvailabilityBlockRead(BaseModel):
    id: str
    start_at: datetime
    end_at: datetime
    type: str
    created_at: datetime | None = None
