"""Document schemas for upload and management"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BaseSchema


class DocumentCreate(BaseModel):
    """Schema for document creation metadata"""

    filename: str
    mime_type: str
    file_size_bytes: int
    file_hash: str


class DocumentUploadResponse(BaseSchema):
    """Response after initiating document upload"""

    id: UUID
    filename: str
    status: str
    message: str = "Document uploaded successfully. Processing started."


class DocumentResponse(BaseSchema):
    """Full document response schema"""

    id: UUID
    organization_id: UUID
    uploaded_by: UUID
    filename: str
    file_hash: str
    mime_type: str
    file_size_bytes: int
    chunk_count: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class DocumentListResponse(BaseSchema):
    """Paginated document list response"""

    documents: list[DocumentResponse]
    total: int


class DocumentStatusUpdate(BaseModel):
    """Schema for updating document status (internal use)"""

    status: str
    error_message: Optional[str] = None
    chunk_count: int = 0


class DocumentFilter(BaseModel):
    """Query parameters for filtering documents"""

    status: Optional[str] = None
    mime_type: Optional[str] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
