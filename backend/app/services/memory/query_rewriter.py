"""Query rewriting for multi-turn conversations"""

import logging
from typing import Optional

from app.models.conversation import Message
from app.services.llm.provider import QwenProvider
from app.services.llm.prompts import PromptTemplates

logger = logging.getLogger(__name__)


class QueryRewriterService:
    """
    Rewrites follow-up questions to be self-contained.
    
    Example:
    - User: "What is hybrid search?"
    - Assistant: "Hybrid search combines vector and keyword..."
    - User: "How does it work?"
    - Rewritten: "How does the hybrid retrieval system work based on the previous context?"
    """
    
    def __init__(self):
        self.llm_provider = QwenProvider()
    
    async def rewrite(
        self,
        query: str,
        conversation_history: list[Message],
    ) -> str:
        """
        Rewrite a follow-up question to be standalone.
        
        Args:
            query: Original follow-up question
            conversation_history: List of previous messages
            
        Returns:
            Rewritten query that is self-contained
        """
        # Format history for prompt
        history_str = PromptTemplates.format_conversation_history(
            messages=[{"role": m.role, "content": m.content} for m in conversation_history],
            max_messages=5,
        )
        
        # Build rewrite prompt
        prompt = PromptTemplates.build_rewrite_prompt(
            history=history_str,
            question=query,
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are a query rewriting assistant. Rewrite follow-up questions to be self-contained and understandable without conversation context. Do not answer the question, only rewrite it. Output ONLY the rewritten question with no additional text.",
            },
            {"role": "user", "content": prompt},
        ]
        
        try:
            response = await self.llm_provider.generate_with_retry(
                messages,
                temperature=0.1,  # Low temperature for consistency
                max_tokens=100,
            )
            
            rewritten = response.content.strip()
            
            # Validate we got a reasonable rewrite
            if len(rewritten) < 5:
                logger.warning(f"Rewrite too short, using original: {rewritten}")
                return query
            
            # Check if rewrite is just the original query
            if rewritten.lower() == query.lower():
                return query
            
            logger.info(f"Successfully rewrote query")
            return rewritten
            
        except Exception as e:
            logger.error(f"Query rewriting failed: {e}")
            # Fallback: return original query
            return query
    
    def _contains_pronoun_reference(self, query: str) -> bool:
        """Check if query contains pronouns that need resolution"""
        pronouns = [
            "it", "they", "them", "its", "their",
            "he", "she", "him", "her",
            "this", "that", "these", "those",
            "the document", "the system", "the feature",
        ]
        
        query_lower = query.lower()
        return any(pronoun in query_lower for pronoun in pronouns)
