"""FastAPI application factory with OpenTelemetry instrumentation"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import SlowRateLimiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.routes import chat, conversations, documents, evals, retrieval, auth
from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.observability import init_observability, shutdown_observability
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.rate_limiter import setup_rate_limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown events"""
    
    # Startup
    logger.info("Starting RAG Assistant API...")
    
    # Initialize OpenTelemetry
    init_observability(settings.OTEL_SERVICE_NAME)
    
    # Initialize database
    await init_db()
    
    # Setup rate limiter
    setup_rate_limiter(app)
    
    logger.info(f"✓ {settings.APP_NAME} v{settings.APP_VERSION} started")
    logger.info(f"  Debug mode: {settings.DEBUG}")
    logger.info(f"  API prefix: {settings.API_PREFIX}")
    logger.info(f"  Environment: {settings.ENVIRONMENT}")
    logger.info(f"  Tracing enabled: {bool(settings.OTEL_EXPORTER_ENDPOINT)}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down RAG Assistant API...")
    await close_db()
    shutdown_observability()
    logger.info("✓ Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Production-grade RAG system with hybrid search, multi-tenancy, and observability",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add observability middleware (custom tracing with trace IDs)
    app.add_middleware(ObservabilityMiddleware)
    
    # Register exception handlers
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Global exception handler for unhandled errors"""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
            },
        )
    
    # Include routers
    app.include_router(auth.router, prefix=f"{settings.API_PREFIX}/auth", tags=["Authentication"])
    app.include_router(documents.router, prefix=f"{settings.API_PREFIX}/documents", tags=["Documents"])
    app.include_router(retrieval.router, prefix=f"{settings.API_PREFIX}/retrieval", tags=["Retrieval"])
    app.include_router(chat.router, prefix=f"{settings.API_PREFIX}/chat", tags=["Chat"])
    app.include_router(conversations.router, prefix=f"{settings.API_PREFIX}/conversations", tags=["Conversations"])
    app.include_router(evals.router, prefix=f"{settings.API_PREFIX}/evals", tags=["Evaluation"])
    
    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
        }
    
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint"""
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
        }
    
    return app


# Create app instance
app = create_app()
