"""Chat endpoints for RAG-powered conversations with streaming support"""

import json
import logging
import time
from typing import AsyncGenerator
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_organization_id_from_request
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Citation,
    StreamChunk,
)
from app.services.generation.rag_service import RAGService
from app.services.memory.history import ConversationHistoryService
from app.services.memory.query_rewriter import QueryRewriterService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Send a message and receive a grounded AI response
    
    Retrieves relevant context from uploaded documents and generates
    a citation-backed answer using Qwen LLM.
    """
    start_time = time.time()
    
    # Initialize services
    rag_service = RAGService(db)
    history_service = ConversationHistoryService(db)
    rewriter = QueryRewriterService(db)
    
    try:
        # Get conversation history if conversation_id provided
        history = []
        if request.conversation_id:
            history = await history_service.get_messages(
                conversation_id=request.conversation_id,
                limit=10,
            )
        
        # Rewrite query if we have history (for multi-turn conversations)
        rewritten_query = request.query
        if history:
            try:
                rewritten_query = await rewriter.rewrite_query(
                    current_query=request.query,
                    conversation_history=history,
                )
                logger.info(f"Query rewritten: '{request.query}' -> '{rewritten_query}'")
            except Exception as e:
                logger.warning(f"Query rewriting failed, using original: {e}")
        
        # Execute RAG pipeline
        result = await rag_service.generate_response(
            query=rewritten_query,
            organization_id=organization_id,
            document_ids=request.document_ids,
            top_k=request.top_k,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            conversation_history=history,
        )
        
        # Save messages to conversation
        conversation_id = request.conversation_id or uuid4()
        user_message_id = uuid4()
        assistant_message_id = uuid4()
        
        # Format citations for storage
        citations_data = [
            {
                "chunk_id": str(c.chunk_id),
                "document_id": str(c.document_id),
                "text": c.text,
                "score": c.score,
                "rank": c.rank,
            }
            for c in result.citations
        ]
        
        await history_service.add_messages(
            conversation_id=conversation_id,
            messages=[
                {
                    "id": user_message_id,
                    "role": "user",
                    "content": request.query,
                },
                {
                    "id": assistant_message_id,
                    "role": "assistant",
                    "content": result.answer,
                    "citations": citations_data,
                    "metadata": {
                        "token_usage": result.token_usage,
                        "model": result.model,
                        "rewritten_query": rewritten_query,
                    },
                },
            ],
            organization_id=organization_id,
            user_id=current_user.id,
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        return ChatResponse(
            answer=result.answer,
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            citations=result.citations,
            model=result.model,
            token_usage=result.token_usage,
            latency_ms=latency_ms,
        )
        
    except Exception as e:
        logger.error(f"Chat generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {str(e)}",
        )


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Stream a RAG-powered response using Server-Sent Events (SSE)
    
    Returns tokens as they are generated by the LLM for a responsive UX.
    Content-Type: text/event-stream
    """
    
    async def generate_stream() -> AsyncGenerator[str, None]:
        start_time = time.time()
        event_id = str(uuid4())
        
        try:
            # Send start event
            yield f"data: {json.dumps({'type': 'start', 'event_id': event_id})}\n\n"
            
            # Initialize services
            rag_service = RAGService(db)
            history_service = ConversationHistoryService(db)
            
            # Get conversation history
            history = []
            if request.conversation_id:
                history = await history_service.get_messages(
                    conversation_id=request.conversation_id,
                    limit=10,
                )
            
            # Use original query (no rewriting in stream mode for simplicity)
            rewritten_query = request.query
            
            # Stream the response
            full_answer = ""
            citations = []
            
            async for chunk in rag_service.stream_response(
                query=rewritten_query,
                organization_id=organization_id,
                document_ids=request.document_ids,
                top_k=request.top_k,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                conversation_history=history,
            ):
                if chunk["type"] == "token":
                    full_answer += chunk["data"]
                    yield f"data: {json.dumps({'type': 'token', 'data': chunk['data']})}\n\n"
                elif chunk["type"] == "citation":
                    citations.append(chunk["data"])
                    yield f"data: {json.dumps({'type': 'citation', 'data': chunk['data']})}\n\n"
                elif chunk["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'data': chunk['data']})}\n\n"
                    return
            
            # Send end event with metadata
            latency_ms = (time.time() - start_time) * 1000
            yield f"data: {json.dumps({\n    'type': 'end',\n    'latency_ms': latency_ms,\n    'citations_count': len(citations)\n})}\n\n"
            
            # Save to conversation history (async, non-blocking)
            if request.conversation_id:
                try:
                    conversation_id = request.conversation_id
                    await history_service.add_messages(
                        conversation_id=conversation_id,
                        messages=[
                            {
                                "role": "user",
                                "content": request.query,
                            },
                            {
                                "role": "assistant",
                                "content": full_answer,
                                "citations": citations,
                            },
                        ],
                        organization_id=organization_id,
                        user_id=current_user.id,
                    )
                except Exception as e:
                    logger.error(f"Failed to save conversation history: {e}")
            
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
