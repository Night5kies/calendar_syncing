import uuid
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ScheduledEvent(Base):
    __tablename__ = "scheduled_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meeting_requests.id", ondelete="CASCADE"),
        index=True,
    )
    slot_start: Mapped[object] = mapped_column(DateTime(timezone=True))
    slot_end: Mapped[object] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_event_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
