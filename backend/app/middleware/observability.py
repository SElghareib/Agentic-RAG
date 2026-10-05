"""Observability middleware for distributed tracing and request logging

This middleware works in conjunction with the OpenTelemetry instrumentation
configured in app.core.observability to provide comprehensive tracing.
"""

import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from opentelemetry import trace

from app.core.config import settings

logger = logging.getLogger(__name__)

# Get tracer from the global provider (initialized in core.observability)
tracer = trace.get_tracer(__name__)


class ObservabilityMiddleware:
    """
    Middleware for request tracing, latency measurement, and structured logging.
    
    Features:
    - Generates unique trace_id for each request
    - Measures total latency and phase-specific latencies
    - Injects trace_id into response headers
    - Logs structured request/response data
    - Creates OpenTelemetry spans for distributed tracing
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        # Generate trace ID
        trace_id = str(uuid.uuid4())
        
        # Start timing
        start_time = time.time()
        
        # Add trace info to request state
        request.state.trace_id = trace_id
        request.state.start_time = start_time
        
        # Extract user/org info if available (for multi-tenancy tracking)
        request.state.user_id = getattr(request.state, "user_id", None)
        request.state.organization_id = getattr(request.state, "organization_id", None)
        
        # Log request
        logger.info(
            f"Request started",
            extra={
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )
        
        # Execute request with tracing span
        with tracer.start_as_current_span(
            name=f"{request.method} {request.url.path}",
            kind=trace.SpanKind.SERVER,
        ) as span:
            # Set span attributes
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.trace_id", trace_id)
            
            # Add custom attributes for multi-tenancy
            if request.state.user_id:
                span.set_attribute("user.id", request.state.user_id)
            if request.state.organization_id:
                span.set_attribute("organization.id", request.state.organization_id)
            
            try:
                response = await call_next(request)
                
                # Calculate latency
                latency_ms = (time.time() - start_time) * 1000
                
                # Add trace ID to response headers
                response.headers["X-Trace-ID"] = trace_id
                
                # Log response
                logger.info(
                    f"Request completed",
                    extra={
                        "trace_id": trace_id,
                        "status_code": response.status_code,
                        "latency_ms": round(latency_ms, 2),
                    },
                )
                
                # Set span status
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("latency.ms", latency_ms)
                
                return response
                
            except Exception as exc:
                # Calculate latency even for errors
                latency_ms = (time.time() - start_time) * 1000
                
                logger.error(
                    f"Request failed",
                    extra={
                        "trace_id": trace_id,
                        "method": request.method,
                        "path": request.url.path,
                        "latency_ms": round(latency_ms, 2),
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                
                # Record exception in span
                span.record_exception(exc)
                span.set_attribute("error", True)
                span.set_attribute("latency.ms", latency_ms)
                
                raise


def get_trace_id_from_request(request: Request) -> str:
    """Extract trace ID from request"""
    return getattr(request.state, "trace_id", str(uuid.uuid4()))


def log_with_trace(logger_obj: logging.Logger, level: int, message: str, request: Request | None = None, **kwargs):
    """Log a message with trace ID context"""
    if request:
        trace_id = getattr(request.state, "trace_id", "unknown")
    else:
        trace_id = "no-context"
    
    extra = kwargs.get("extra", {})
    extra["trace_id"] = trace_id
    kwargs["extra"] = extra
    
    logger_obj.log(level, f"[{trace_id}] {message}", **kwargs)
