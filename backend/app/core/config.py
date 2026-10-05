"""Application configuration using Pydantic Settings"""

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "RAG Assistant"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"  # development, staging, production
    INSTANCE_ID: Optional[str] = None  # Unique instance identifier for tracing

    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "raguser"
    DB_PASSWORD: str = "ragpassword"
    DB_NAME: str = "ragdb"
    DATABASE_URL: str = "postgresql+asyncpg://raguser:ragpassword@localhost:5432/ragdb"

    # Redis (Celery)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Observability (OpenTelemetry/Jaeger)
    OTEL_EXPORTER_ENDPOINT: Optional[str] = "http://jaeger:4317"  # OTLP gRPC endpoint
    OTEL_AUTH_TOKEN: Optional[str] = None

    # Security & Auth
    API_SECRET_KEY: str = "change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # File Upload
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "text/markdown",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    # Embedding Model (Local - BGE-M3)
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_DEVICE: str = "cpu"  # cpu or cuda

    # LLM Configuration (DashScope/Qwen)
    LLM_PROVIDER: str = "dashscope"
    DASHSCOPE_API_KEY: Optional[str] = None
    QWEN_MODEL: str = "qwen-max"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.7
    LLM_TIMEOUT_SECONDS: int = 60

    # RAG Configuration
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    RETRIEVAL_TOP_K: int = 5
    RERANK_TOP_N: int = 3
    HYBRID_SEARCH_ALPHA: float = 0.5  # Weight for vector search (1-alpha for keyword)

    # Conversation Memory
    MEMORY_WINDOW_SIZE: int = 10  # Number of messages to keep in context

    # Evaluation
    GOLDEN_DATASET_PATH: str = "./evals/dataset.json"

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
