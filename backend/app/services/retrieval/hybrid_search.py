"""Hybrid search combining vector and keyword results using Reciprocal Rank Fusion (RRF)"""

import asyncio
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.services.retrieval.vector_search import VectorSearchService
from app.services.retrieval.keyword_search import KeywordSearchService

logger = logging.getLogger(__name__)


class HybridSearchService:
    """
    Combines vector and keyword search results using Reciprocal Rank Fusion (RRF).
    
    RRF Formula: score(d) = Σ 1 / (k + rank_i(d))
    
    Where:
    - k is a constant (typically 60) that dampens the effect of outliers
    - rank_i(d) is the rank of document d in result list i
    
    This approach:
    - Balances semantic similarity (vector) with exact matching (keyword)
    - Is parameter-free (no need to tune weights)
    - Handles cases where one method fails but the other succeeds
    """

    def __init__(self, session: AsyncSession, rrf_k: int = 60):
        self.session = session
        self.rrf_k = rrf_k
        
        self.vector_search = VectorSearchService(session)
        self.keyword_search = KeywordSearchService(session)

    async def search(
        self,
        query: str,
        query_embedding: list[float],
        organization_id: UUID,
        top_k: int = 5,
        vector_weight: float = 0.5,
        document_ids: Optional[list[UUID]] = None,
    ) -> list[dict]:
        """
        Perform hybrid search combining vector and keyword results.
        
        Args:
            query: Original search query (for keyword search)
            query_embedding: Query embedding vector (for vector search)
            organization_id: Organization UUID for filtering
            top_k: Final number of results to return
            vector_weight: Weight for vector search (1-weight for keyword)
            document_ids: Optional document ID filter
            
        Returns:
            List of dicts with chunk data and hybrid scores
        """
        # Run both searches in parallel
        vector_results, keyword_results = await asyncio.gather(
            self.vector_search.search(
                query_embedding=query_embedding,
                organization_id=organization_id,
                top_k=top_k * 2,  # Get more for fusion
                document_ids=document_ids,
            ),
            self.keyword_search.search(
                query=query,
                organization_id=organization_id,
                top_k=top_k * 2,
                document_ids=document_ids,
            ),
            return_exceptions=True,
        )
        
        # Handle exceptions gracefully
        if isinstance(vector_results, Exception):
            logger.error(f"Vector search failed: {vector_results}")
            vector_results = []
        if isinstance(keyword_results, Exception):
            logger.error(f"Keyword search failed: {keyword_results}")
            keyword_results = []
        
        # Apply RRF
        rrf_scores = self._reciprocal_rank_fusion(
            vector_results=vector_results,
            keyword_results=keyword_results,
            vector_weight=vector_weight,
        )
        
        # Sort by RRF score descending
        sorted_chunks = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Build final results
        results = []
        for chunk, score in sorted_chunks[:top_k]:
            results.append({
                "chunk": chunk,
                "hybrid_score": score,
                "content": chunk.content,
                "metadata": chunk.metadata,
                "document_id": chunk.document_id,
            })
        
        logger.info(f"Hybrid search returned {len(results)} results")
        
        return results

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[tuple[Chunk, float]],
        keyword_results: list[tuple[Chunk, float]],
        vector_weight: float = 0.5,
    ) -> dict[Chunk, float]:
        """
        Apply Reciprocal Rank Fusion to combine results.
        
        Returns dict mapping Chunk -> RRF score
        """
        from collections import defaultdict
        
        rrf_scores: defaultdict[Chunk, float] = defaultdict(float)
        
        # Process vector results
        for rank, (chunk, _) in enumerate(vector_results, start=1):
            # Weighted RRF score
            score = vector_weight / (self.rrf_k + rank)
            rrf_scores[chunk] += score
        
        # Process keyword results
        keyword_weight = 1.0 - vector_weight
        for rank, (chunk, _) in enumerate(keyword_results, start=1):
            score = keyword_weight / (self.rrf_k + rank)
            rrf_scores[chunk] += score
        
        return dict(rrf_scores)
