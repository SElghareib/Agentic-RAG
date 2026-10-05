"""Text chunking strategies for RAG"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ChunkData:
    """Represents a text chunk with metadata"""

    content: str
    metadata: dict = field(default_factory=dict)
    embedding: Optional[list[float]] = None


class TextChunker:
    """
    Implements chunking strategies for splitting text into segments.
    
    Strategies:
    - Fixed-size: Split by character count with overlap
    - Semantic: Split by markdown headers or paragraph boundaries
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    async def chunk(self, text: str, filename: str = "") -> list[ChunkData]:
        """
        Split text into chunks using semantic-aware strategy.
        
        Args:
            text: Raw text to chunk
            filename: Original filename (used for metadata)
        
        Returns:
            List of ChunkData objects
        """
        # Try semantic chunking first (by headers/sections)
        chunks = self._semantic_chunk(text)
        
        # If semantic chunking produces too few or too large chunks,
        # fall back to fixed-size chunking
        if len(chunks) < 2 or any(len(c.content) > self.chunk_size * 2 for c in chunks):
            logger.info("Falling back to fixed-size chunking")
            chunks = self._fixed_size_chunk(text)
        
        # Add metadata
        for idx, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = idx
            chunk.metadata["filename"] = filename
            chunk.metadata["char_start"] = text.find(chunk.content)
            chunk.metadata["char_end"] = chunk.metadata["char_start"] + len(chunk.content)
        
        # Filter out too-small chunks
        chunks = [c for c in chunks if len(c.content.strip()) >= self.min_chunk_size]
        
        logger.info(f"Created {len(chunks)} chunks from text ({len(text)} chars)")
        return chunks

    def _semantic_chunk(self, text: str) -> list[ChunkData]:
        """Split text by semantic boundaries (headers, sections)"""
        chunks = []
        
        # Split by markdown headers (#, ##, ###, etc.)
        header_pattern = r"(^|\n)(#+\s+.+)"
        matches = list(re.finditer(header_pattern, text, re.MULTILINE))
        
        if not matches:
            # No headers found, try splitting by double newlines
            return self._split_by_paragraphs(text)
        
        # Split by headers
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            
            section = text[start:end].strip()
            if section:
                chunks.append(ChunkData(content=section))
        
        return chunks

    def _split_by_paragraphs(self, text: str) -> list[ChunkData]:
        """Split text by paragraph boundaries"""
        paragraphs = re.split(r"\n\n+", text)
        chunks = []
        
        current_content = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(current_content) + len(para) <= self.chunk_size:
                current_content += "\n\n" + para if current_content else para
            else:
                if current_content:
                    chunks.append(ChunkData(content=current_content))
                current_content = para
        
        if current_content:
            chunks.append(ChunkData(content=current_content))
        
        return chunks

    def _fixed_size_chunk(self, text: str) -> list[ChunkData]:
        """Split text by fixed character count with overlap"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            
            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence-ending punctuation
                sentence_break = max(
                    text.rfind(". ", start, end),
                    text.rfind("! ", start, end),
                    text.rfind("? ", start, end),
                    text.rfind("\n", start, end),
                )
                if sentence_break > start + self.chunk_size // 2:
                    end = sentence_break + 1
            
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(ChunkData(content=chunk_text))
            
            start = end - self.chunk_overlap
        
        return chunks
