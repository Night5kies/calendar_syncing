import uuid
from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class MeetingRequest(Base):
    __tablename__ = "meeting_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(200))
    duration_min: Mapped[int] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    window_start: Mapped[str] = mapped_column(String(32))  # keep simple for now; upgrade to timestamptz
    window_end: Mapped[str] = mapped_column(String(32))
    constraints: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
