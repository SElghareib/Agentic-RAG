"""Common Pydantic schemas used across multiple endpoints"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with common configuration"""

    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(BaseModel):
    """Mixin for created_at/updated_at timestamps"""

    created_at: datetime
    updated_at: Optional[datetime] = None


class PaginationParams(BaseModel):
    """Common pagination parameters"""

    skip: int = 0
    limit: int = 20


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper"""

    items: list
    total: int
    skip: int
    limit: int


class ErrorDetail(BaseModel):
    """Error response schema"""

    error: str
    detail: Optional[str] = None


class HealthCheck(BaseModel):
    """Health check response"""

    status: str
    version: Optional[str] = None


# Conversation schemas
class ConversationCreate(BaseModel):
    """Schema for creating a conversation"""

    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MessageResponse(BaseModel):
    """Schema for a message in a conversation"""

    id: UUID
    role: str
    content: str
    citations: Optional[list] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(BaseModel):
    """Schema for a conversation response"""

    id: UUID
    title: str
    user_id: UUID
    organization_id: UUID
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    messages: Optional[list[MessageResponse]] = None
    
    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    """Schema for listing conversations"""

    conversations: list[ConversationResponse]
    total: int
