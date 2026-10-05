"""Evaluation endpoints for running RAG quality assessments"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_organization_id_from_request
from app.models.user import User
from app.schemas.common import BaseSchema
from app.evals.runner import EvaluationRunner
from app.evals.metrics import EvaluationMetrics

logger = logging.getLogger(__name__)

router = APIRouter()


class EvalRunRequest(BaseSchema):
    """Request to trigger an evaluation run"""
    
    dataset_name: str = "default"
    top_k: int = 5


class EvalRunResponse(BaseSchema):
    """Response from an evaluation run"""
    
    run_id: str
    status: str
    metrics_summary: dict | None = None


class EvalMetricsResponse(BaseSchema):
    """Detailed evaluation metrics"""
    
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg: float
    total_queries: int
    successful_queries: int


@router.post("/run", response_model=EvalRunResponse)
async def run_evaluation(
    request: EvalRunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Trigger a RAG evaluation run against the golden dataset
    
    This runs the full RAG pipeline on predefined test queries and
    computes retrieval and generation quality metrics.
    
    Results are stored for later analysis.
    """
    from sqlalchemy import select
    
    try:
        # Initialize runner
        runner = EvaluationRunner(db)
        
        # Run evaluation synchronously (for MVP; could be async task)
        logger.info(f"Starting evaluation run: {request.dataset_name}")
        
        eval_data = await runner.run_evaluation(
            dataset_name=request.dataset_name,
            organization_id=organization_id,
            top_k=request.top_k,
        )
        
        # Compute aggregate metrics
        metrics = EvaluationMetrics()
        summary = metrics.compute_aggregate_metrics(eval_data["results"])
        
        # Store evaluation run in database
        from app.models.observability import EvaluationRun
        
        eval_run = EvaluationRun(
            id=uuid4(),
            run_id=eval_data["run_id"],
            organization_id=organization_id,
            dataset_name=request.dataset_name,
            recall_at_k=summary.get("recall_at_k"),
            precision_at_k=summary.get("precision_at_k"),
            mrr=summary.get("mrr"),
            ndcg=summary.get("ndcg"),
            total_queries=len(eval_data["results"]),
            successful_queries=sum(1 for r in eval_data["results"] if r.retrieved_chunk_ids),
            latency_stats=summary.get("latency"),
        )
        
        db.add(eval_run)
        await db.commit()
        
        logger.info(f"Evaluation completed: {summary}")
        
        return EvalRunResponse(
            run_id=eval_data["run_id"],
            status="completed",
            metrics_summary=summary,
        )
        
    except FileNotFoundError as e:
        logger.error(f"Dataset not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{request.dataset_name}' not found",
        )
    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {str(e)}",
        )


@router.get("/metrics", response_model=EvalMetricsResponse)
async def get_latest_metrics(
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Get the latest evaluation metrics
    
    Returns aggregate metrics from the most recent evaluation run.
    """
    from sqlalchemy import select
    from app.models.observability import EvaluationRun
    
    # Get latest evaluation run
    result = await db.execute(
        select(EvaluationRun)
        .where(EvaluationRun.organization_id == organization_id)
        .order_by(EvaluationRun.created_at.desc())
        .limit(1)
    )
    
    eval_run = result.scalar_one_or_none()
    
    if not eval_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No evaluation runs found. Run an evaluation first.",
        )
    
    return EvalMetricsResponse(
        recall_at_k=eval_run.recall_at_k or 0.0,
        precision_at_k=eval_run.precision_at_k or 0.0,
        mrr=eval_run.mrr or 0.0,
        ndcg=eval_run.ndcg or 0.0,
        total_queries=eval_run.total_queries or 0,
        successful_queries=eval_run.successful_queries or 0,
    )


@router.get("/history")
async def get_evaluation_history(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    organization_id: UUID = Depends(get_organization_id_from_request),
    db: AsyncSession = None,
):
    """
    Get history of evaluation runs
    
    Returns metadata about past evaluation runs for trend analysis.
    """
    from sqlalchemy import select
    from app.models.observability import EvaluationRun
    
    result = await db.execute(
        select(EvaluationRun)
        .where(EvaluationRun.organization_id == organization_id)
        .order_by(EvaluationRun.created_at.desc())
        .limit(limit)
    )
    
    runs = result.scalars().all()
    
    return {
        "runs": [
            {
                "run_id": str(run.id),
                "created_at": run.created_at,
                "dataset_name": run.dataset_name,
                "recall_at_k": run.recall_at_k,
                "precision_at_k": run.precision_at_k,
                "mrr": run.mrr,
                "total_queries": run.total_queries,
            }
            for run in runs
        ],
        "total": len(runs),
    }
