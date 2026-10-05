"""Keyword search using PostgreSQL full-text search (tsvector/tsquery)"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk

logger = logging.getLogger(__name__)


class KeywordSearchService:
    """
    Performs keyword search using PostgreSQL full-text search.
    
    Uses tsvector/tsquery with ts_rank for scoring.
    Excellent for exact matches, error codes, acronyms, and technical terms.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(
        self,
        query: str,
        organization_id: UUID,
        top_k: int = 5,
        document_ids: Optional[list[UUID]] = None,
    ) -> list[tuple[Chunk, float]]:
        """
        Search for chunks using full-text search.
        
        Args:
            query: Search query string
            organization_id: Organization UUID for multi-tenancy filtering
            top_k: Number of results to return
            document_ids: Optional list of document IDs to filter
        
        Returns:
            List of (Chunk, score) tuples sorted by relevance (highest first)
        """
        # Sanitize query for tsquery
        # Replace special characters that might break tsquery
        sanitized_query = self._sanitize_tsquery(query)
        
        if not sanitized_query:
            logger.warning("Empty or invalid query for keyword search")
            return []
        
        # Build tsquery
        # Use plainto_tsquery for natural language queries
        # or websearch_to_tsquery for more flexible parsing
        tsquery = func.websearch_to_tsquery("english", sanitized_query)
        
        # Build query with ranking
        rank = func.ts_rank(Chunk.keywords, tsquery).label("rank")
        
        stmt = (
            select(Chunk, rank)
            .where(Chunk.organization_id == organization_id)
            .where(Chunk.keywords.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(top_k)
        )
        
        # Optional document filter
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        
        result = await self.session.execute(stmt)
        rows = result.all()
        
        # Convert to list of (Chunk, score) tuples
        results = [(chunk, float(rank)) for chunk, rank in rows]
        
        logger.info(f"Keyword search returned {len(results)} results for query: {query[:50]}")
        
        return results

    def _sanitize_tsquery(self, query: str) -> str:
        """
        Sanitize query for PostgreSQL tsquery.
        
        Removes operators and special characters that could break parsing.
        """
        import re
        
        # Remove common tsquery operators
        operators = ["&", "|", "!", "(", ")", ":", "'", "<->"]
        sanitized = query
        for op in operators:
            sanitized = sanitized.replace(op, " ")
        
        # Remove extra whitespace
        sanitized = " ".join(sanitized.split())
        
        return sanitized


# Import func here to avoid circular imports
from sqlalchemy import func
