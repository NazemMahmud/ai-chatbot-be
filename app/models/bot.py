import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="My Chatbot")
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str | None] = mapped_column(
        Text, default="You are a helpful assistant."
    )
    welcome_message: Mapped[str | None] = mapped_column(
        Text, default="Hi! How can I help you?"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships — many-to-many with documents via document_bots join table
    documents = relationship(
        "Document",
        secondary="document_bots",
        back_populates="bots",
        lazy="selectin",
    )
