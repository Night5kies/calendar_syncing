import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class MeetingRequest(Base):
    __tablename__ = "meeting_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    duration_min: Mapped[int] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    event_type: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(255))
    video_link: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    response_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    reminder_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
