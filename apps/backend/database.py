"""
Database setup — SQLite with SQLAlchemy async engine.
Local-first: SQLite is the source of truth.
"""
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# Ensure data directory exists
Path(settings.DB_DIR).mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.BACKEND_DEBUG,
    connect_args={"check_same_thread": False, "timeout": 15},
)

from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    if hasattr(dbapi_connection, "execute"):
        dbapi_connection.execute("PRAGMA journal_mode=WAL;")
        dbapi_connection.execute("PRAGMA synchronous=NORMAL;")
        dbapi_connection.execute("PRAGMA busy_timeout=5000;")

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables on startup."""
    # Import all models so Base knows about them
    import models.camera   # noqa: F401
    import models.track    # noqa: F401
    import models.event    # noqa: F401
    import models.analytics  # noqa: F401
    import models.user     # noqa: F401
    import models.store    # noqa: F401
    import models.transaction # noqa: F401
    import models.cloud    # noqa: F401
    import models.transaction_intelligence  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """Dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
