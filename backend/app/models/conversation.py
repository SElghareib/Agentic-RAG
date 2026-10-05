"""Conversation and Message models for chat history"""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User, Organization


class Conversation(Base):
    """Conversation model representing a chat session"""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        back_populates="conversations",
    )
    user: Mapped["User"] = relationship(
        back_populates="conversations",
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.title or 'Untitled'}>"


class Message(Base):
    """Message model representing a single chat message"""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="user, assistant, or system",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[Optional[list[dict]]] = mapped_column(
        JSONB,
        comment="List of {chunk_id, text, score, document_id} for grounding",
    )
    metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        comment="Token usage, model info, latency metrics",
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
    )

    __table_args__ = (
        # Index for ordering messages by creation time
        Index("ix_messages_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Message {self.role}: {self.content[:50]}...>"
