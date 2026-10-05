"""Conversation history management for multi-turn RAG"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)


class ConversationHistoryService:
    """
    Manages conversation state and message history.
    
    Features:
    - Retrieve last N messages for context window
    - Enforce context limits
    - Store new messages
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_messages(
        self,
        conversation_id: UUID,
        limit: int = 10,
    ) -> list[Message]:
        """
        Retrieve recent messages from a conversation.
        
        Args:
            conversation_id: Conversation UUID
            limit: Maximum number of messages to return
            
        Returns:
            List of Message objects ordered by created_at ascending
        """
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        messages = result.scalars().all()
        
        # Reverse to get chronological order
        return list(reversed(messages))
    
    async def add_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> Message:
        """
        Add a new message to the conversation.
        
        Args:
            conversation_id: Conversation UUID
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata (citations, token usage, etc.)
            
        Returns:
            Created Message object
        """
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )
        
        self.session.add(message)
        await self.session.flush()  # Get ID without committing
        
        logger.debug(f"Added {role} message to conversation {conversation_id}")
        
        return message
    
    async def create_conversation(
        self,
        user_id: UUID,
        organization_id: UUID,
        title: Optional[str] = None,
    ) -> Conversation:
        """
        Create a new conversation.
        
        Args:
            user_id: User UUID
            organization_id: Organization UUID
            title: Optional conversation title
            
        Returns:
            Created Conversation object
        """
        conversation = Conversation(
            user_id=user_id,
            organization_id=organization_id,
            title=title or "New Conversation",
        )
        
        self.session.add(conversation)
        await self.session.flush()
        
        logger.info(f"Created conversation {conversation.id} for user {user_id}")
        
        return conversation
    
    async def get_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Optional[Conversation]:
        """
        Get a conversation by ID (with ownership check).
        
        Args:
            conversation_id: Conversation UUID
            user_id: User UUID for ownership verification
            
        Returns:
            Conversation or None if not found
        """
        query = (
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def list_conversations(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """
        List conversations for a user.
        
        Args:
            user_id: User UUID
            limit: Pagination limit
            offset: Pagination offset
            
        Returns:
            List of Conversation objects
        """
        query = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .offset(offset)
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def delete_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Delete a conversation (cascades to messages).
        
        Args:
            conversation_id: Conversation UUID
            user_id: User UUID for ownership verification
            
        Returns:
            True if deleted, False if not found
        """
        conversation = await self.get_conversation(conversation_id, user_id)
        
        if not conversation:
            return False
        
        await self.session.delete(conversation)
        logger.info(f"Deleted conversation {conversation_id}")
        
        return True
    
    async def update_conversation_title(
        self,
        conversation_id: UUID,
        title: str,
        user_id: UUID,
    ) -> bool:
        """
        Update conversation title.
        
        Returns:
            True if updated, False if not found
        """
        conversation = await self.get_conversation(conversation_id, user_id)
        
        if not conversation:
            return False
        
        conversation.title = title
        conversation.updated_at = None  # Trigger auto-update
        
        logger.info(f"Updated conversation title: {title}")
        
        return True
