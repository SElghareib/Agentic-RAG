"""Chunk model with pgvector embedding and full-text search support"""

import uuid
from typing import TYPE_CHECKING, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import Organization


class Chunk(Base):
    """Chunk model representing a text segment from a document with embeddings"""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        comment="Page numbers, section headers, bounding boxes, etc.",
    )
    # BGE-M3 uses 1024 dimensions; configurable via settings
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(dim=1024))
    embedding_norm: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Pre-computed L2 norm for faster cosine similarity",
    )
    # Generated tsvector column for full-text search (BM25-style)
    keywords: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        back_populates="chunks",
    )
    organization: Mapped["Organization"] = relationship(
        back_populates="documents",
    )

    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_org_id", "organization_id"),
        # GIN index for full-text search
        Index("ix_chunks_keywords", "keywords", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Chunk {self.chunk_index} of Document {self.document_id}>"
