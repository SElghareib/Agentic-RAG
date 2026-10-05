"""RequestTrace and EvaluationRun models for observability and debugging"""

import uuid
from typing import Optional
from datetime import datetime

from sqlalchemy import Float, Integer, String, Text, DateTime, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RequestTrace(Base):
    """RequestTrace model for tracking request latency and metrics"""

    __tablename__ = "request_traces"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    trace_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Latency metrics (in milliseconds)
    latency_total_ms: Mapped[Optional[float]] = mapped_column(Float)
    latency_retrieval_ms: Mapped[Optional[float]] = mapped_column(Float)
    latency_llm_ms: Mapped[Optional[float]] = mapped_column(Float)
    
    # RAG-specific metrics
    retrieval_scores: Mapped[Optional[list[dict]]] = mapped_column(
        JSONB,
        comment="Scores from hybrid search for each retrieved chunk",
    )
    token_usage: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        comment="{prompt_tokens, completion_tokens, total_tokens}",
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<RequestTrace {self.trace_id} - {self.endpoint} ({self.status_code})>"


class EvaluationRun(Base):
    """EvaluationRun model for storing RAG evaluation results"""

    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    dataset_name: Mapped[str] = mapped_column(String, nullable=False)
    
    # Aggregate metrics
    recall_at_k: Mapped[Optional[float]] = mapped_column(Float)
    precision_at_k: Mapped[Optional[float]] = mapped_column(Float)
    mrr: Mapped[Optional[float]] = mapped_column(Float)
    ndcg: Mapped[Optional[float]] = mapped_column(Float)
    
    # Query counts
    total_queries: Mapped[Optional[int]] = mapped_column(Integer)
    successful_queries: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Latency stats (stored as JSONB for flexibility)
    latency_stats: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Detailed results (optional, can be large)
    detailed_results: Mapped[Optional[list[dict]]] = mapped_column(JSONB)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<EvaluationRun {self.run_id} - {self.dataset_name}>"

