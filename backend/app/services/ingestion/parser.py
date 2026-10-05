"""Document parser for extracting text from various file formats"""

import logging
import tempfile
from pathlib import Path
from typing import Optional

import aiofiles
from markdown import markdown
from pypdf import PdfReader
from python_docx import Document as DocxDocument

logger = logging.getLogger(__name__)


class DocumentParser:
    """
    Extracts raw text from various document formats.
    
    Supported formats:
    - PDF (via pypdf)
    - Markdown (.md)
    - Plain text (.txt)
    - Word documents (.docx)
    """

    async def parse(self, file_path: str, mime_type: str) -> Optional[str]:
        """
        Parse a document and extract raw text.
        
        Args:
            file_path: Path to the file
            mime_type: MIME type of the file
        
        Returns:
            Extracted text or None if parsing fails
        """
        try:
            if mime_type == "application/pdf":
                return await self._parse_pdf(file_path)
            elif mime_type in ["text/markdown", "text/x-markdown"]:
                return await self._parse_markdown(file_path)
            elif mime_type == "text/plain":
                return await self._parse_text(file_path)
            elif mime_type in [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ]:
                return await self._parse_docx(file_path)
            else:
                # Try plain text as fallback
                logger.warning(f"Unknown MIME type {mime_type}, attempting text parse")
                return await self._parse_text(file_path)
        except Exception as e:
            logger.error(f"Failed to parse document {file_path}: {e}")
            raise

    async def _parse_pdf(self, file_path: str) -> str:
        """Extract text from PDF"""
        text_parts = []
        
        reader = PdfReader(file_path)
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"[Page {page_num + 1}]\n{page_text}")
        
        return "\n\n".join(text_parts)

    async def _parse_markdown(self, file_path: str) -> str:
        """Read markdown file and normalize"""
        async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
            content = await f.read()
        
        # Convert markdown to plain text (optional - could keep markdown)
        # For RAG, keeping markdown structure is often better for chunking
        return content

    async def _parse_text(self, file_path: str) -> str:
        """Read plain text file"""
        async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
            content = await f.read()
        
        return self._normalize_whitespace(content)

    async def _parse_docx(self, file_path: str) -> str:
        """Extract text from Word document"""
        doc = DocxDocument(file_path)
        
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        
        return "\n\n".join(text_parts)

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text"""
        import re
        
        # Replace multiple spaces with single space
        text = re.sub(r" +", " ", text)
        
        # Replace multiple newlines with double newline
        text = re.sub(r"\n\s*\n", "\n\n", text)
        
        return text.strip()
