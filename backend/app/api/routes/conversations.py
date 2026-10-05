"""Conversation management endpoints"""

import logging
from uuid import UUID, uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.dependencies import get_current_user, get_organization_id_from_request
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.schemas.common import (
    ConversationCreate,
    ConversationResponse,
    ConversationListResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: Optional[ConversationCreate] = None,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Create a new conversation session
    
    Conversations group related messages together for multi-turn dialogues.
    Optionally provide a title; otherwise auto-generated.
    """
    conversation = Conversation(
        id=uuid4(),
        organization_id=organization_id,
        user_id=current_user.id,
        title=request.title if request and request.title else "New Conversation",
        metadata=request.metadata if request and request.metadata else {},
    )
    
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    
    logger.info(f"Conversation created: {conversation.id} by user {current_user.id}")
    
    return conversation


@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    List all conversations for the current user
    
    Results are paginated and ordered by last activity (most recent first).
    """
    # Build query
    query = (
        select(Conversation)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.user_id == current_user.id,
        )
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(query)
    conversations = result.scalars().all()
    
    # Get total count
    count_query = (
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.user_id == current_user.id,
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    return ConversationListResponse(
        conversations=[
            ConversationResponse.model_validate(conv)
            for conv in conversations
        ],
        total=total,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Get a specific conversation with its messages
    
    Returns conversation metadata and all associated messages.
    """
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
            Conversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Delete a conversation and all its messages
    
    This action is irreversible.
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
            Conversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    await db.delete(conversation)
    await db.commit()
    
    logger.info(f"Conversation deleted: {conversation_id}")
    
    return None


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    title: Optional[str] = None,
    metadata: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Update conversation metadata
    
    Can update title and/or custom metadata.
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
            Conversation.user_id == current_user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    if title is not None:
        conversation.title = title
    
    if metadata is not None:
        if conversation.metadata is None:
            conversation.metadata = {}
        conversation.metadata.update(metadata)
    
    await db.commit()
    await db.refresh(conversation)
    
    return conversation


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    conversation_id: UUID,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Get messages for a specific conversation
    
    Returns messages in chronological order (oldest first).
    Supports pagination for long conversations.
    """
    from sqlalchemy.orm import selectinload
    
    # First verify conversation access
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
            Conversation.user_id == current_user.id,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    # Get messages
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    messages = result.scalars().all()
    
    return [MessageResponse.model_validate(msg) for msg in messages]
