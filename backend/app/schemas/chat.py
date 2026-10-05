"""Chat schemas for conversation and message handling"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema
from app.schemas.retrieval import Citation


class MessageCreate(BaseModel):
    """Schema for creating a new message"""

    content: str = Field(..., min_length=1, max_length=10000)
    role: str = Field(default="user", pattern="^(user|assistant|system)$")


class MessageResponse(BaseSchema):
    """Message response schema"""

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    citations: Optional[list[Citation]] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime


class ChatRequest(BaseModel):
    """Standard chat request (non-streaming)"""

    query: str = Field(..., min_length=1, max_length=1000)
    conversation_id: Optional[UUID] = None
    document_ids: Optional[list[UUID]] = None
    top_k: int = Field(default=5, ge=1, le=20)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=100, le=8192)


class ChatResponse(BaseModel):
    """Standard chat response"""

    answer: str
    conversation_id: UUID
    message_id: UUID
    citations: list[Citation]
    model: str
    token_usage: dict[str, int]
    latency_ms: float


class StreamChunk(BaseModel):
    """Server-Sent Event chunk for streaming responses"""

    type: str  # "start", "token", "citation", "end", "error"
    data: Optional[str | dict] = None
    event_id: Optional[str] = None


class ConversationCreate(BaseModel):
    """Schema for creating a new conversation"""

    title: Optional[str] = Field(None, max_length=200)
    document_ids: Optional[list[UUID]] = None


class ConversationResponse(BaseSchema):
    """Conversation response schema"""

    id: UUID
    organization_id: UUID
    user_id: UUID
    title: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    message_count: int = 0


class ConversationListResponse(BaseModel):
    """Paginated conversation list"""

    conversations: list[ConversationResponse]
    total: int


class QueryRewriteRequest(BaseModel):
    """Request for query rewriting in multi-turn conversations"""

    current_query: str
    conversation_history: list[dict[str, str]]  # [{role, content}]


class QueryRewriteResponse(BaseModel):
    """Rewritten query response"""

    original_query: str
    rewritten_query: str
    explanation: Optional[str] = None
