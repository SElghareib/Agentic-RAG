"""Embedding service using local sentence-transformers (BGE-M3)"""

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.services.ingestion.chunker import ChunkData

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Generates embeddings for text chunks using local models.
    
    Uses BGE-M3 model which supports:
    - Dense retrieval (vector similarity)
    - Multi-lingual text
    - Long context (up to 8192 tokens)
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.device = settings.EMBEDDING_DEVICE
        self.batch_size = settings.EMBEDDING_BATCH_SIZE
        
        logger.info(f"Loading embedding model: {self.model_name} on {self.device}")
        
        # Lazy load the model
        self._model: Optional[SentenceTransformer] = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy-load the embedding model"""
        if self._model is None:
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
            )
            logger.info(f"Embedding model loaded successfully")
        return self._model

    async def embed_batch(self, chunks: list[ChunkData]) -> list[ChunkData]:
        """
        Generate embeddings for a batch of chunks.
        
        Args:
            chunks: List of ChunkData objects
        
        Returns:
            Same list with embeddings populated
        """
        if not chunks:
            return []
        
        texts = [chunk.content for chunk in chunks]
        
        logger.info(f"Generating embeddings for {len(texts)} chunks")
        
        # Generate embeddings in batches
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,  # Important for cosine similarity
            convert_to_numpy=True,
        )
        
        # Attach embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding.tolist()
        
        logger.info(f"Generated {len(chunks)} embeddings ({len(embeddings[0])} dimensions)")
        
        return chunks

    async def embed_query(self, query: str) -> list[float]:
        """
        Generate embedding for a single query.
        
        Args:
            query: Search query text
        
        Returns:
            Embedding vector as list of floats
        """
        # BGE-M3 benefits from instruction prefix for retrieval
        query_with_instruction = f"Represent this query for searching relevant documents: {query}"
        
        embedding = self.model.encode(
            query_with_instruction,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        
        return embedding.tolist()

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        """L2 normalize a vector"""
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return (np.array(vector) / norm).tolist()
