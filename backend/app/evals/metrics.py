"""Evaluation metrics for RAG system performance"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievalMetrics:
    """Information Retrieval metrics"""
    recall_at_k: dict[int, float] = field(default_factory=dict)
    precision_at_k: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0  # Mean Reciprocal Rank
    ndcg: float = 0.0  # Normalized Discounted Cumulative Gain


@dataclass
class GenerationMetrics:
    """LLM generation quality metrics"""
    relevance_score: float = 0.0  # 1-5 scale
    groundedness_score: float = 0.0  # 1-5 scale
    citation_accuracy: float = 0.0  # 1-5 scale
    hallucination_rate: float = 0.0  # Percentage of unsupported claims


@dataclass
class EvalResult:
    """Complete evaluation result for a single query"""
    query_id: str
    query: str
    expected_answer: str
    ground_truth_chunk_ids: list[str]
    
    # Retrieval results
    retrieved_chunk_ids: list[str]
    retrieval_metrics: Optional[RetrievalMetrics] = None
    
    # Generation results
    generated_answer: str = ""
    generation_metrics: Optional[GenerationMetrics] = None
    
    # Metadata
    latency_ms: float = 0.0
    token_usage: dict = field(default_factory=dict)


def calculate_recall_at_k(retrieved: list[str], ground_truth: list[str], k: int) -> float:
    """Calculate Recall@K: fraction of relevant items retrieved in top-K"""
    if not ground_truth:
        return 0.0
    
    top_k = retrieved[:k]
    relevant_retrieved = len(set(top_k) & set(ground_truth))
    
    return relevant_retrieved / len(ground_truth)


def calculate_precision_at_k(retrieved: list[str], ground_truth: list[str], k: int) -> float:
    """Calculate Precision@K: fraction of retrieved items that are relevant"""
    if not retrieved:
        return 0.0
    
    top_k = retrieved[:k]
    relevant_retrieved = len(set(top_k) & set(ground_truth))
    
    return relevant_retrieved / len(top_k)


def calculate_mrr(retrieved: list[str], ground_truth: list[str]) -> float:
    """Calculate Mean Reciprocal Rank (MRR)"""
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in ground_truth:
            return 1.0 / rank
    
    return 0.0


def compute_retrieval_metrics(
    retrieved: list[str],
    ground_truth: list[str],
    k_values: list[int] = None,
) -> RetrievalMetrics:
    """Compute all retrieval metrics for a query"""
    if k_values is None:
        k_values = [1, 3, 5, 10]
    
    metrics = RetrievalMetrics()
    
    for k in k_values:
        metrics.recall_at_k[k] = calculate_recall_at_k(retrieved, ground_truth, k)
        metrics.precision_at_k[k] = calculate_precision_at_k(retrieved, ground_truth, k)
    
    metrics.mrr = calculate_mrr(retrieved, ground_truth)
    
    return metrics
