"""Document model for tracking uploaded files"""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.user import User, Organization


class DocumentStatus:
    """Document processing statuses"""

    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    """Document model representing an uploaded file"""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)  # SHA256
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(
        String,
        default=DocumentStatus.PROCESSING,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[Optional[dict]] = mapped_column(comment="Additional document metadata")

    # Relationships
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    organization: Mapped["Organization"] = relationship(
        back_populates="documents",
    )
    uploaded_by_user: Mapped["User"] = relationship(
        back_populates="documents",
        foreign_keys=[uploaded_by],
    )

    __table_args__ = (
        Index("ix_documents_org_status", "organization_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Document {self.filename} ({self.status})>"
