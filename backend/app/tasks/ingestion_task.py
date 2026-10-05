"""Document ingestion tasks for async processing"""

import hashlib
import logging
from typing import Optional
from uuid import UUID

from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_context
from app.models.document import Document, DocumentStatus
from app.services.ingestion.parser import DocumentParser
from app.services.ingestion.chunker import TextChunker
from app.services.ingestion.embedder import EmbeddingService

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Base task with database session management"""

    _db_session: Optional[AsyncSession] = None

    @property
    def db_session(self) -> AsyncSession:
        if self._db_session is None:
            raise RuntimeError("Database session not initialized")
        return self._db_session

    def __call__(self, *args, **kwargs):
        # Note: For async tasks, we handle sessions inside the task body
        return super().__call__(*args, **kwargs)


@celery_app.task(base=DatabaseTask, bind=True, max_retries=3)
async def process_document_task(
    self,
    document_id: str,
    file_path: str,
    organization_id: str,
) -> dict:
    """
    Celery task to process a document asynchronously.
    
    Pipeline:
    1. Parse document (extract text)
    2. Chunk text (split into segments)
    3. Generate embeddings (vectorize chunks)
    4. Store in database
    
    Args:
        document_id: UUID of the document record
        file_path: Path to the uploaded file
        organization_id: UUID of the organization
    
    Returns:
        dict with chunk_count and status
    """
    import uuid
    
    doc_uuid = uuid.UUID(document_id)
    org_uuid = uuid.UUID(organization_id)
    
    try:
        async with get_db_context() as session:
            # Fetch document record
            doc = await session.get(Document, doc_uuid)
            if not doc:
                raise ValueError(f"Document {document_id} not found")
            
            # Update status to processing
            doc.status = DocumentStatus.PROCESSING
            await session.flush()
            
            logger.info(f"Processing document: {doc.filename}")
            
            # Step 1: Parse document
            parser = DocumentParser()
            raw_text = await parser.parse(file_path, doc.mime_type)
            
            if not raw_text or len(raw_text.strip()) == 0:
                raise ValueError("Document contains no extractable text")
            
            # Step 2: Chunk text
            chunker = TextChunker()
            chunks_data = await chunker.chunk(raw_text, doc.filename)
            
            logger.info(f"Created {len(chunks_data)} chunks")
            
            # Step 3: Generate embeddings
            embedder = EmbeddingService()
            embedded_chunks = await embedder.embed_batch(chunks_data)
            
            # Step 4: Store chunks in database
            from app.models.chunk import Chunk
            
            for idx, chunk_data in enumerate(embedded_chunks):
                chunk = Chunk(
                    document_id=doc_uuid,
                    organization_id=org_uuid,
                    chunk_index=idx,
                    content=chunk_data.content,
                    metadata=chunk_data.metadata,
                    embedding=chunk_data.embedding,
                    embedding_norm=_compute_norm(chunk_data.embedding),
                )
                session.add(chunk)
            
            # Update document status
            doc.chunk_count = len(embedded_chunks)
            doc.status = DocumentStatus.READY
            doc.error_message = None
            
            await session.flush()
            
            logger.info(f"Successfully processed document {document_id}")
            
            return {
                "document_id": document_id,
                "chunk_count": len(embedded_chunks),
                "status": DocumentStatus.READY,
            }
    
    except Exception as exc:
        # Update document status to failed
        try:
            async with get_db_context() as session:
                doc = await session.get(Document, doc_uuid)
                if doc:
                    doc.status = DocumentStatus.FAILED
                    doc.error_message = str(exc)
                    await session.flush()
        except Exception as update_exc:
            logger.error(f"Failed to update document status: {update_exc}")
        
        logger.error(f"Error processing document {document_id}: {exc}")
        
        # Retry with exponential backoff
        retry_delay = 60 * (2 ** (self.request.retries or 0))
        raise self.retry(exc=exc, countdown=retry_delay)


def _compute_norm(embedding: list[float]) -> float:
    """Compute L2 norm of embedding vector"""
    import math
    return math.sqrt(sum(x * x for x in embedding))


@celery_app.task(bind=True, max_retries=2)
def cleanup_temp_files(self, file_paths: list[str]) -> dict:
    """Clean up temporary uploaded files after processing"""
    import os
    
    deleted = []
    errors = []
    
    for path in file_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                deleted.append(path)
        except Exception as exc:
            errors.append(str(exc))
    
    return {
        "deleted": deleted,
        "errors": errors,
    }
