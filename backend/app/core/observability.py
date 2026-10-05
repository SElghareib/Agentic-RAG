"""
OpenTelemetry Configuration and Instrumentation

Sets up distributed tracing for FastAPI, SQLAlchemy, Redis, Celery, and HTTP clients.
Exports traces to Jaeger/Tempo via OTLP.
"""

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.core.config import settings


class OpenTelemetryConfig:
    """Centralized OpenTelemetry configuration and initialization."""
    
    def __init__(self):
        self.tracer_provider: Optional[TracerProvider] = None
        self.tracer: Optional[trace.Tracer] = None
        self._initialized = False
    
    def initialize(self, app_name: str = "rag-backend") -> None:
        """
        Initialize OpenTelemetry with all instrumentations.
        
        Args:
            app_name: Name of the service for trace identification
        """
        if self._initialized:
            return
        
        # Create resource with service metadata
        resource = Resource.create({
            SERVICE_NAME: app_name,
            SERVICE_VERSION: "1.0.0",
            "deployment.environment": settings.ENVIRONMENT,
            "service.instance.id": settings.INSTANCE_ID or os.getenv("HOSTNAME", "unknown"),
        })
        
        # Set up trace provider with B3 propagation (Jaeger/Zipkin compatible)
        self.tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(self.tracer_provider)
        
        # Add span processors
        self._add_span_processors()
        
        # Get tracer instance
        self.tracer = trace.get_tracer(__name__)
        
        # Instrument all libraries
        self._instrument_libraries()
        
        self._initialized = True
        print(f"✅ OpenTelemetry initialized for '{app_name}'")
    
    def _add_span_processors(self) -> None:
        """Configure span exporters based on environment."""
        
        # Always add console exporter for local development
        if settings.ENVIRONMENT == "development":
            self.tracer_provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
        
        # Add OTLP exporter for production (Jaeger/Tempo)
        if settings.OTEL_EXPORTER_ENDPOINT:
            otlp_exporter = OTLPSpanExporter(
                endpoint=settings.OTEL_EXPORTER_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {settings.OTEL_AUTH_TOKEN}"
                } if settings.OTEL_AUTH_TOKEN else {}
            )
            self.tracer_provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )
            print(f"📡 OTLP exporter configured: {settings.OTEL_EXPORTER_ENDPOINT}")
    
    def _instrument_libraries(self) -> None:
        """Apply instrumentation to all supported libraries."""
        
        # FastAPI instrumentation
        FastAPIInstrumentor.instrument_app(
            None,  # Will be applied in main.py
            tracer_provider=self.tracer_provider,
            excluded_urls="health,ready,metrics"
        )
        
        # SQLAlchemy instrumentation
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            engine=None  # Will auto-detect engines
        )
        
        # Redis instrumentation (for Celery broker/cache)
        RedisInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            capture_statement=True
        )
        
        # HTTPX client instrumentation (for LLM API calls)
        HTTPXClientInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            capture_request_headers=True,
            capture_response_headers=True
        )
        
        # Celery instrumentation (for async tasks)
        CeleryInstrumentor().instrument(
            tracer_provider=self.tracer_provider
        )
    
    def get_tracer(self) -> trace.Tracer:
        """Get the configured tracer instance."""
        if not self._initialized:
            raise RuntimeError("OpenTelemetry not initialized. Call initialize() first.")
        return self.tracer
    
    def inject_context(self, carrier: dict) -> None:
        """Inject current trace context into carrier for downstream services."""
        propagator = TraceContextTextMapPropagator()
        propagator.inject(carrier)
    
    def extract_context(self, carrier: dict) -> Context:
        """Extract trace context from carrier for upstream propagation."""
        propagator = TraceContextTextMapPropagator()
        return propagator.extract(carrier=carrier)
    
    def shutdown(self) -> None:
        """Gracefully shutdown OpenTelemetry and flush pending spans."""
        if self.tracer_provider:
            self.tracer_provider.shutdown()
            self._initialized = False


# Global singleton instance
otel_config = OpenTelemetryConfig()


def get_tracer() -> trace.Tracer:
    """Convenience function to get the global tracer."""
    return otel_config.get_tracer()


def init_observability(app_name: str = "rag-backend") -> None:
    """Initialize observability stack (call once at app startup)."""
    otel_config.initialize(app_name)


def shutdown_observability() -> None:
    """Shutdown observability stack (call once at app shutdown)."""
    otel_config.shutdown()
