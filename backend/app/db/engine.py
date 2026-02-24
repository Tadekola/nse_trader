"""
Database engine and session management for NSE Trader.

Provides:
- Async SQLAlchemy engine (asyncpg)
- Sync engine for Alembic migrations (psycopg2)
- Async session factory
- DB initialization helper
"""

import logging
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import create_engine, Engine, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.core.config import get_settings
from app.db.models import Base

# Allow JSONB columns to work on SQLite (rendered as JSON/TEXT)
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

# BigInteger → INTEGER on SQLite so autoincrement works on PKs
@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(element, compiler, **kw):
    return "INTEGER"

logger = logging.getLogger(__name__)

_async_engine: AsyncEngine | None = None
_sync_engine: Engine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_async_engine() -> AsyncEngine:
    """Get or create the async database engine."""
    global _async_engine
    if _async_engine is None:
        settings = get_settings()
        is_sqlite = "sqlite" in settings.DATABASE_URL
        engine_kwargs = dict(echo=False)
        if not is_sqlite:
            engine_kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)
        _async_engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)
        logger.info("Async database engine created: %s", settings.DATABASE_URL)
    return _async_engine


def get_sync_engine() -> Engine:
    """Get or create the sync database engine (for Alembic)."""
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()
        _sync_engine = create_engine(
            settings.DATABASE_URL_SYNC,
            echo=False,
            pool_pre_ping=True,
        )
    return _sync_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency-injection compatible async session generator."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database schema at app startup.

    In DEV (ENV=dev or AUTO_CREATE_SCHEMA=on): uses Base.metadata.create_all.
    In PRODUCTION: schema is managed by Alembic migrations only.
    Set AUTO_CREATE_SCHEMA=off to disable create_all in any environment.
    """
    env = os.environ.get("ENV", "dev").lower()
    auto_create = os.environ.get("AUTO_CREATE_SCHEMA", "").lower()

    # Explicit override takes precedence
    if auto_create == "off":
        logger.info("AUTO_CREATE_SCHEMA=off — skipping create_all (Alembic-managed)")
        return
    if auto_create == "on" or env == "dev":
        engine = get_async_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified (DEV mode)")
        return

    # Production: do NOT create_all — Alembic manages schema
    logger.info("Production mode — schema managed by Alembic (create_all skipped)")


async def close_db() -> None:
    """Close database connections. Called at app shutdown."""
    global _async_engine, _async_session_factory
    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
        logger.info("Database engine disposed")
