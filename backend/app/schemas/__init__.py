"""Pydantic schemas package for API validation"""

from app.schemas.common import (
    BaseSchema,
    ErrorDetail,
    HealthCheck,
    PaginatedResponse,
    PaginationParams,
)
from app.schemas.auth import (
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    OrganizationCreate,
    OrganizationResponse,
)
from app.schemas.document import (
    DocumentResponse,
    DocumentUploadResponse,
    DocumentListResponse,
    DocumentFilter,
)
from app.schemas.retrieval import (
    RetrievalRequest,
    RetrievalResponse,
    ChunkResponse,
    Citation,
)
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    MessageResponse,
    ConversationResponse,
    StreamChunk,
)

__all__ = [
    # Common
    "BaseSchema",
    "ErrorDetail",
    "HealthCheck",
    "PaginatedResponse",
    "PaginationParams",
    # Auth
    "Token",
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "OrganizationCreate",
    "OrganizationResponse",
    # Document
    "DocumentResponse",
    "DocumentUploadResponse",
    "DocumentListResponse",
    "DocumentFilter",
    # Retrieval
    "RetrievalRequest",
    "RetrievalResponse",
    "ChunkResponse",
    "Citation",
    # Chat
    "ChatRequest",
    "ChatResponse",
    "MessageResponse",
    "ConversationResponse",
    "StreamChunk",
]
