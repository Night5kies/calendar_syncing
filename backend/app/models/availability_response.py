import uuid
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AvailabilityResponse(Base):
    __tablename__ = "availability_responses"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        index=True,
    )
    availability: Mapped[dict] = mapped_column(JSONB, default=dict)
    source: Mapped[str] = mapped_column(String(32), default="link")
    responded_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
