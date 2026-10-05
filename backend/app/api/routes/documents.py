"""Document upload, management, and status endpoints"""

import hashlib
import logging
import uuid
from io import BytesIO
from typing import Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_organization_id_from_request
from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.document import (
    DocumentFilter,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.tasks.ingestion_task import process_document_task

logger = logging.getLogger(__name__)

router = APIRouter()


def calculate_file_hash(file_content: bytes) -> str:
    """Calculate SHA256 hash of file content for deduplication"""
    return hashlib.sha256(file_content).hexdigest()


async def validate_file(file: UploadFile) -> bytes:
    """Validate uploaded file and return its content"""
    # Check MIME type
    if file.content_type not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {settings.ALLOWED_MIME_TYPES}",
        )
    
    # Read file content
    content = await file.read()
    
    # Check file size
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB}MB",
        )
    
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded",
        )
    
    return content


@router.post("/", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,  # Will be injected
):
    """
    Upload a document for processing
    
    Accepts PDF, Markdown, TXT, and DOCX files.
    Returns immediately with document ID; processing happens asynchronously.
    Use GET /documents/{id} to check processing status.
    """
    from sqlalchemy import select
    
    # Validate and read file
    try:
        content = await validate_file(file)
    except HTTPException:
        raise
    
    # Calculate hash for deduplication
    file_hash = calculate_file_hash(content)
    
    # Check for duplicate
    result = await db.execute(
        select(Document).where(
            Document.file_hash == file_hash,
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.READY,
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        logger.info(f"Duplicate file detected: {file.filename}")
        return DocumentUploadResponse(
            id=existing.id,
            filename=existing.filename,
            status=existing.status,
            message="Document already exists and is ready.",
        )
    
    # Create document record
    document = Document(
        organization_id=organization_id,
        uploaded_by=current_user.id,
        filename=file.filename,
        file_hash=file_hash,
        mime_type=file.content_type,
        file_size_bytes=len(content),
        status=DocumentStatus.PROCESSING,
    )
    
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    # Save file to storage (local for now, can be S3 later)
    storage_path = f"/tmp/documents/{organization_id}/{document.id}_{file.filename}"
    async with aiofiles.open(storage_path, "wb") as f:
        await f.write(content)
    
    logger.info(f"Document uploaded: {document.id} ({file.filename})")
    
    # Queue background processing task
    try:
        # Celery task - fire and forget
        process_document_task.delay(
            str(document.id),
            storage_path,
            str(organization_id),
        )
        logger.info(f"Processing task queued for document: {document.id}")
    except Exception as e:
        logger.error(f"Failed to queue processing task: {e}")
        # Update status to failed
        document.status = DocumentStatus.FAILED
        document.error_message = f"Failed to queue processing task: {str(e)}"
        await db.commit()
    
    return DocumentUploadResponse(
        id=document.id,
        filename=document.filename,
        status=document.status,
        message="Document uploaded successfully. Processing started.",
    )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    filter_params: DocumentFilter = Depends(),
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    List all documents for the current organization
    
    Supports filtering by status and MIME type.
    Results are paginated.
    """
    from sqlalchemy import func, select
    
    # Build query
    query = select(Document).where(Document.organization_id == organization_id)
    
    # Apply filters
    if filter_params.status:
        query = query.where(Document.status == filter_params.status)
    if filter_params.mime_type:
        query = query.where(Document.mime_type == filter_params.mime_type)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Apply pagination
    query = query.offset(filter_params.skip).limit(filter_params.limit)
    query = query.order_by(Document.created_at.desc())
    
    result = await db.execute(query)
    documents = result.scalars().all()
    
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(doc) for doc in documents],
        total=total,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """Get details of a specific document"""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Delete a document and all its chunks
    
    This action is irreversible. All associated chunks will be deleted.
    """
    from sqlalchemy import select
    
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    # Delete document (chunks will cascade delete)
    await db.delete(document)
    await db.commit()
    
    logger.info(f"Document deleted: {document_id}")
    
    return None


@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Reprocess a failed document
    
    Resets status to 'processing' and queues the ingestion task again.
    Useful when document processing fails due to transient errors.
    """
    from sqlalchemy import select
    
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    if document.status != DocumentStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed documents can be reprocessed",
        )
    
    # Reset status
    document.status = DocumentStatus.PROCESSING
    document.error_message = None
    await db.commit()
    
    # Re-queue processing task
    try:
        storage_path = f"/tmp/documents/{organization_id}/{document_id}_{document.filename}"
        process_document_task.delay(
            str(document_id),
            storage_path,
            str(organization_id),
        )
        logger.info(f"Reprocessing task queued for document: {document_id}")
    except Exception as e:
        logger.error(f"Failed to queue reprocessing task: {e}")
        document.status = DocumentStatus.FAILED
        document.error_message = f"Failed to queue reprocessing task: {str(e)}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue reprocessing: {str(e)}",
        )
    
    return document
