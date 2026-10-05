"""Vector similarity search using pgvector"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk

logger = logging.getLogger(__name__)


class VectorSearchService:
    """
    Performs vector similarity search using pgvector's cosine distance operator.
    
    Uses the <=> operator which returns the cosine distance (1 - cosine_similarity).
    Lower values indicate higher similarity.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(
        self,
        query_embedding: list[float],
        organization_id: UUID,
        top_k: int = 5,
        document_ids: Optional[list[UUID]] = None,
    ) -> list[tuple[Chunk, float]]:
        """
        Search for similar chunks using vector embedding.
        
        Args:
            query_embedding: Query vector (should be normalized)
            organization_id: Organization UUID for multi-tenancy filtering
            top_k: Number of results to return
            document_ids: Optional list of document IDs to filter
        
        Returns:
            List of (Chunk, score) tuples sorted by similarity (highest first)
        """
        # Build query with cosine distance
        # embedding <=> query_vector returns cosine distance (0 = identical, 2 = opposite)
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        
        stmt = (
            select(Chunk, distance)
            .where(Chunk.organization_id == organization_id)
            .where(Chunk.embedding.isnot(None))
            .order_by(distance)
            .limit(top_k)
        )
        
        # Optional document filter
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        
        result = await self.session.execute(stmt)
        rows = result.all()
        
        # Convert to list of (Chunk, score) tuples
        # Convert distance to similarity score (1 - distance)
        results = [(chunk, 1.0 - float(dist)) for chunk, dist in rows]
        
        logger.info(f"Vector search returned {len(results)} results")
        
        return results
