"""RAG Service orchestrating retrieval, generation, and citation parsing"""

import asyncio
import logging
import re
from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.ingestion.embedder import EmbeddingService
from app.services.retrieval.hybrid_search import HybridSearchService
from app.services.llm.provider import QwenProvider, LLMResponse
from app.services.llm.prompts import PromptTemplates
from app.services.guardrails.safety import GuardrailService
from app.services.memory.history import ConversationHistoryService
from app.services.memory.query_rewriter import QueryRewriterService

logger = logging.getLogger(__name__)


class RAGService:
    """
    Orchestrates the complete RAG pipeline:
    1. Embed query
    2. Retrieve relevant chunks (hybrid search)
    3. Build prompt with context
    4. Call LLM for generation
    5. Parse citations from response
    6. Format final output with source references
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedder = EmbeddingService()
        self.hybrid_search = HybridSearchService(session)
        self.llm_provider = QwenProvider()
        self.guardrails = GuardrailService()
        self.history_service = ConversationHistoryService(session)
        self.query_rewriter = QueryRewriterService()
    
    async def generate_response(
        self,
        query: str,
        organization_id: UUID,
        conversation_id: Optional[UUID] = None,
        document_ids: Optional[list[UUID]] = None,
        top_k: int = 5,
        stream: bool = False,
    ) -> LLMResponse | AsyncGenerator[str, None]:
        """
        Generate RAG-based response to user query.
        
        Args:
            query: User's question
            organization_id: Organization for filtering documents
            conversation_id: Optional conversation ID for multi-turn
            document_ids: Optional specific documents to search
            top_k: Number of chunks to retrieve
            stream: Whether to stream response
            
        Returns:
            LLMResponse or async generator of tokens
        """
        # Step 0: Safety check on input
        safety_result = await self.guardrails.check_input(query)
        if not safety_result.is_safe:
            logger.warning(f"Unsafe input detected: {safety_result.reason}")
            raise ValueError(f"Input failed safety check: {safety_result.reason}")
        
        # Step 1: Handle multi-turn conversation (query rewriting)
        if conversation_id:
            history = await self.history_service.get_messages(
                conversation_id=conversation_id,
                limit=settings.CONVERSATION_HISTORY_LENGTH,
            )
            
            if history and len(history) > 1:
                # Rewrite follow-up question to be standalone
                rewritten_query = await self.query_rewriter.rewrite(
                    query=query,
                    conversation_history=history,
                )
                logger.info(f"Rewrote query: '{query}' -> '{rewritten_query}'")
                query = rewritten_query
        
        # Step 2: Embed the query
        query_embedding = await self.embedder.embed_query(query)
        
        # Step 3: Retrieve relevant chunks via hybrid search
        retrieval_results = await self.hybrid_search.search(
            query=query,
            query_embedding=query_embedding,
            organization_id=organization_id,
            top_k=top_k,
            document_ids=document_ids,
        )
        
        if not retrieval_results:
            logger.warning("No relevant chunks found")
            # Return a graceful response when no context is found
            return LLMResponse(
                content="I don't have enough information in the provided documents to answer this question.",
                token_usage={"prompt_tokens": 0, "completion_tokens": 18, "total_tokens": 18},
                model=settings.QWEN_MODEL,
                finish_reason="stop",
            )
        
        # Step 4: Build context from retrieved chunks
        context_str = PromptTemplates.format_context_chunks(
            chunks=retrieval_results,
            max_chars=settings.RAG_MAX_CONTEXT_CHARS,
        )
        
        # Step 5: Build prompt messages
        system_message = {
            "role": "system",
            "content": PromptTemplates.SYSTEM_PROMPT,
        }
        
        user_message = {
            "role": "user",
            "content": PromptTemplates.build_user_prompt(
                context=context_str,
                question=query,
            ),
        }
        
        # Add conversation history if available
        messages = [system_message]
        if conversation_id and history:
            # Add previous messages (excluding system)
            for msg in history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })
        
        messages.append(user_message)
        
        logger.info(f"Sending {len(messages)} messages to LLM with {len(retrieval_results)} context chunks")
        
        # Step 6: Generate response
        if stream:
            return self._stream_with_citations(messages, retrieval_results)
        else:
            response = await self.llm_provider.generate_with_retry(messages)
            # Parse and enhance with citation metadata
            return self._parse_citations(response, retrieval_results)
    
    async def _stream_with_citations(
        self,
        messages: list[dict],
        retrieval_results: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Stream LLM response token by token"""
        full_response = ""
        
        async for token in self.llm_provider.stream_with_retry(messages):
            full_response += token
            yield token
        
        # Log completion with token usage estimation
        logger.info(f"Streaming completed, total chars: {len(full_response)}")
    
    def _parse_citations(
        self,
        response: LLMResponse,
        retrieval_results: list[dict],
    ) -> LLMResponse:
        """
        Parse citations from response and validate against retrieved chunks.
        
        This method can be extended to:
        - Verify that cited sources actually support the claims
        - Extract structured citation metadata
        - Flag potential hallucinations
        """
        # Extract all [Source N] patterns
        citation_pattern = r"\[Source (\d+)\]"
        citations = re.findall(citation_pattern, response.content)
        
        # Validate citations are within range
        valid_citations = []
        for cite_num in citations:
            idx = int(cite_num) - 1  # Convert to 0-indexed
            if 0 <= idx < len(retrieval_results):
                valid_citations.append(idx + 1)  # Back to 1-indexed
        
        if len(valid_citations) != len(citations):
            logger.warning("Some citations in response don't match retrieved chunks")
        
        # Could add citation metadata to response here
        logger.info(f"Response contains {len(valid_citations)} valid citations")
        
        return response
    
    async def generate_answer_with_sources(
        self,
        query: str,
        organization_id: UUID,
        **kwargs
    ) -> dict:
        """
        Convenience method returning structured response with sources.
        
        Returns dict with:
        - answer: Generated text
        - sources: List of source chunks with scores
        - citations: Mapped citations to chunks
        - metadata: Token usage, latency, etc.
        """
        import time
        start_time = time.time()
        
        response = await self.generate_response(
            query=query,
            organization_id=organization_id,
            stream=False,
            **kwargs
        )
        
        # Perform retrieval again to get sources (could be optimized)
        query_embedding = await self.embedder.embed_query(query)
        retrieval_results = await self.hybrid_search.search(
            query=query,
            query_embedding=query_embedding,
            organization_id=organization_id,
            top_k=kwargs.get("top_k", 5),
        )
        
        # Parse citations
        citation_pattern = r"\[Source (\d+)\]"
        cited_indices = set(int(m) - 1 for m in re.findall(citation_pattern, response.content))
        
        cited_sources = []
        for idx in cited_indices:
            if 0 <= idx < len(retrieval_results):
                cited_sources.append(retrieval_results[idx])
        
        latency_ms = (time.time() - start_time) * 1000
        
        return {
            "answer": response.content,
            "sources": retrieval_results,
            "cited_sources": cited_sources,
            "metadata": {
                "token_usage": response.token_usage,
                "latency_ms": latency_ms,
                "model": response.model,
            }
        }
