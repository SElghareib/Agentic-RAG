"""Celery application configuration for async task processing

Integrates with OpenTelemetry for distributed tracing of background tasks.
"""

from celery import Celery
from opentelemetry.instrumentation.celery import CeleryInstrumentor

from app.core.config import settings
from app.core.observability import otel_config


# Create Celery app
celery_app = Celery(
    "rag_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.ingestion_task"],
)

# Configure Celery
celery_app.conf.update(
    # Task serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minutes soft limit
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Rate limiting
    worker_prefetch_multiplier=1,
    
    # Result expiration (1 hour)
    result_expires=3600,
    
    # OpenTelemetry propagation for distributed tracing
    task_send_sent_event=True,
    task_send_created_event=True,
)

# Instrument Celery with OpenTelemetry
# This automatically creates spans for task publishing and execution
CeleryInstrumentor().instrument(
    app=celery_app,
    tracer_provider=otel_config.tracer_provider if otel_config._initialized else None,
)
