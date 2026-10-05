"""Evaluation runner for RAG system"""

import json
import logging
import time
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.evals.metrics import EvalResult, RetrievalMetrics, GenerationMetrics, compute_retrieval_metrics
from app.services.generation.rag_service import RAGService
from app.services.ingestion.embedder import EmbeddingService
from app.services.retrieval.hybrid_search import HybridSearchService

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """
    Runs evaluation against a golden dataset.
    
    Usage:
        runner = EvaluationRunner(session, org_id)
        results = await runner.run_evaluation("dataset.json")
        report = runner.generate_report(results)
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.rag_service = RAGService(session)
        self.embedder = EmbeddingService()
    
    async def load_dataset(self, dataset_name: str = "default") -> list[dict]:
        """Load golden dataset from built-in dataset.json"""
        # Use the built-in dataset
        path = Path(__file__).parent / "dataset.json"
        
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        logger.info(f"Loaded {len(data)} evaluation queries from {path}")
        return data
    
    async def evaluate_query(self, query_item: dict, organization_id: UUID) -> EvalResult:
        """
        Evaluate a single query from the dataset.
        
        Args:
            query_item: Dict with query, expected_answer, ground_truth_chunk_ids
            organization_id: Organization to search within
            
        Returns:
            EvalResult with metrics
        """
        start_time = time.time()
        
        query = query_item["query"]
        ground_truth_ids = query_item.get("ground_truth_chunk_ids", [])
        expected_answer = query_item.get("expected_answer", "")
        
        # Run RAG pipeline
        try:
            result = await self.rag_service.generate_response(
                query=query,
                organization_id=organization_id,
                top_k=10,  # Retrieve more for evaluation
            )
            
            retrieved_ids = [str(c.chunk_id) for c in result.citations]
            generated_answer = result.answer
            latency_ms = result.latency_ms
            token_usage = result.token_usage
            
        except Exception as e:
            logger.error(f"Evaluation failed for query '{query}': {e}")
            return EvalResult(
                query_id=query_item.get("id", "unknown"),
                query=query,
                expected_answer=expected_answer,
                ground_truth_chunk_ids=ground_truth_ids,
                retrieved_chunk_ids=[],
                generated_answer="",
                latency_ms=(time.time() - start_time) * 1000,
            )
        
        # Compute retrieval metrics
        retrieval_metrics = compute_retrieval_metrics(
            retrieved=retrieved_ids,
            ground_truth=ground_truth_ids,
        )
        
        return EvalResult(
            query_id=query_item.get("id", "unknown"),
            query=query,
            expected_answer=expected_answer,
            ground_truth_chunk_ids=ground_truth_ids,
            retrieved_chunk_ids=retrieved_ids,
            retrieval_metrics=retrieval_metrics,
            generated_answer=generated_answer,
            latency_ms=latency_ms,
            token_usage=token_usage,
        )
    
    async def run_evaluation(
        self,
        dataset_name: str = "default",
        organization_id: Optional[UUID] = None,
        top_k: int = 5,
    ) -> dict:
        """
        Run evaluation on entire dataset.
        
        Args:
            dataset_name: Name of dataset (currently only "default" supported)
            organization_id: Organization to evaluate within
            top_k: Number of results to retrieve
            
        Returns:
            Dict with run_id and results list
        """
        run_id = str(uuid4())
        dataset = await self.load_dataset(dataset_name)
        
        results = []
        for i, query_item in enumerate(dataset):
            logger.info(f"Evaluating query {i+1}/{len(dataset)}")
            result = await self.evaluate_query(query_item, organization_id)
            results.append(result)
        
        logger.info(f"Evaluation complete: {len(results)} queries processed")
        
        return {
            "run_id": run_id,
            "results": results,
        }
    
    def generate_report(self, results: list[EvalResult]) -> dict:
        """Generate summary report from evaluation results"""
        from app.evals.metrics import aggregate_metrics
        
        aggregated = aggregate_metrics(results)
        
        # Add latency stats
        latencies = [r.latency_ms for r in results if r.latency_ms > 0]
        if latencies:
            aggregated["latency"] = {
                "avg_ms": sum(latencies) / len(latencies),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
            }
        
        return aggregated
    
    def save_results(self, results: list[EvalResult], output_path: str):
        """Save detailed results to JSON file"""
        output = []
        for r in results:
            item = {
                "query_id": r.query_id,
                "query": r.query,
                "expected_answer": r.expected_answer,
                "generated_answer": r.generated_answer,
                "ground_truth_chunk_ids": r.ground_truth_chunk_ids,
                "retrieved_chunk_ids": r.retrieved_chunk_ids,
                "latency_ms": r.latency_ms,
            }
            if r.retrieval_metrics:
                item["retrieval_metrics"] = {
                    "recall_at_k": r.retrieval_metrics.recall_at_k,
                    "precision_at_k": r.retrieval_metrics.precision_at_k,
                    "mrr": r.retrieval_metrics.mrr,
                }
            output.append(item)
        
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"Saved evaluation results to {output_path}")
