"""Retrieval schemas for search and hybrid query results"""

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema


class RetrievalRequest(BaseModel):
    """Request schema for retrieval endpoint"""

    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: Optional[list[UUID]] = None
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)


class ChunkMetadata(BaseSchema):
    """Chunk metadata schema"""

    page_number: Optional[int] = None
    section: Optional[str] = None
    bounding_box: Optional[dict[str, float]] = None


class ChunkResponse(BaseSchema):
    """Chunk data in retrieval results"""

    id: UUID
    content: str
    chunk_index: int
    document_id: UUID
    metadata: Optional[dict[str, Any]] = None


class RetrievalResult(BaseModel):
    """Single retrieval result with scores"""

    chunk: ChunkResponse
    hybrid_score: float
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    rank: int


class RetrievalResponse(BaseModel):
    """Full retrieval response"""

    query: str
    results: list[RetrievalResult]
    total_time_ms: float
    vector_results_count: int
    keyword_results_count: int


class Citation(BaseModel):
    """Citation for LLM response grounding"""

    chunk_id: UUID
    document_id: UUID
    text: str
    score: float
    rank: int
