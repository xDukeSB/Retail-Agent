"""
Database session management — supports SQLite and PostgreSQL.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import DatabaseDialect, get_settings

settings = get_settings()


from sqlalchemy import event

def _build_engine():
    url = settings.async_database_url
    if settings.DB_DIALECT == DatabaseDialect.SQLITE:
        engine = create_async_engine(
            url,
            echo=settings.DB_ECHO,
            connect_args={"check_same_thread": False},
            # Remove StaticPool to allow multiple concurrent SQLite connections
        )
        
        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000") # 64MB cache
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            
        return engine
        
    # PostgreSQL — use connection pool
    return create_async_engine(
        url,
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
