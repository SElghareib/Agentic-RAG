"""Database engine and session management with OpenTelemetry instrumentation"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# Instrument SQLAlchemy for OpenTelemetry
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Instrument the sync engine for telemetry (used by Alembic)
sync_engine = engine.sync_engine
SQLAlchemyInstrumentor().instrument(engine=sync_engine)

# Async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models"""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions (use outside of FastAPI dependencies)"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database connection and run health check"""
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        print("✓ Database connection established")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        raise


async def close_db() -> None:
    """Close database connections"""
    await engine.dispose()
