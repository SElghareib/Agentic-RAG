"""Retrieval endpoints for hybrid search debugging and testing"""

import logging
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_organization_id_from_request
from app.models.user import User
from app.schemas.retrieval import (
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    ChunkResponse,
)
from app.services.ingestion.embedder import EmbeddingService
from app.services.retrieval.hybrid_search import HybridSearchService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/search", response_model=RetrievalResponse)
async def search(
    request: RetrievalRequest,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Perform hybrid search across indexed documents
    
    Combines vector similarity search with keyword (BM25) search using
    Reciprocal Rank Fusion (RRF) to produce ranked results.
    
    Useful for debugging retrieval quality before integrating with LLM.
    """
    start_time = time.time()
    
    # Generate query embedding
    embedder = EmbeddingService()
    try:
        query_embedding = await embedder.embed_query(request.query)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate query embedding: {str(e)}",
        )
    
    # Perform hybrid search
    hybrid_search = HybridSearchService(db)
    try:
        results = await hybrid_search.search(
            query=request.query,
            query_embedding=query_embedding,
            organization_id=organization_id,
            top_k=request.top_k,
            vector_weight=request.vector_weight,
            document_ids=request.document_ids,
        )
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )
    
    # Format results
    formatted_results = []
    for rank, item in enumerate(results, start=1):
        chunk = item["chunk"]
        formatted_results.append(RetrievalResult(
            chunk=ChunkResponse(
                id=chunk.id,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                document_id=chunk.document_id,
                metadata=chunk.metadata,
            ),
            hybrid_score=item["hybrid_score"],
            rank=rank,
        ))
    
    total_time_ms = (time.time() - start_time) * 1000
    
    logger.info(
        f"Search completed: {len(formatted_results)} results in {total_time_ms:.2f}ms"
    )
    
    return RetrievalResponse(
        query=request.query,
        results=formatted_results,
        total_time_ms=total_time_ms,
        vector_results_count=len(results),
        keyword_results_count=len(results),  # Simplified; actual counts from individual searches
    )


@router.get("/chunks/{chunk_id}")
async def get_chunk(
    chunk_id: UUID,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """Get a specific chunk by ID"""
    from sqlalchemy import select
    from app.models.chunk import Chunk
    
    result = await db.execute(
        select(Chunk).where(
            Chunk.id == chunk_id,
            Chunk.organization_id == organization_id,
        )
    )
    chunk = result.scalar_one_or_none()
    
    if not chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found",
        )
    
    return {
        "id": chunk.id,
        "content": chunk.content,
        "chunk_index": chunk.chunk_index,
        "document_id": chunk.document_id,
        "metadata": chunk.metadata,
    }
