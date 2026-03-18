import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class EventCache(Base):
    __tablename__ = "event_cache"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_event_id: Mapped[str] = mapped_column(String(255))
    provider_calendar_id: Mapped[str] = mapped_column(String(255))
    start_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    last_fetched_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    etag: Mapped[str | None] = mapped_column(String(255))
