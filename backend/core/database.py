import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Use DATABASE_URL env for Postgres in prod, fall back to local SQLite
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./meetiq.db"
)

# Postgres URLs from Railway/Render sometimes start with "postgres://" — fix it
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}
else:
    connect_args = {}

from sqlalchemy import event

engine = create_async_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

# SQLite: Enable WAL mode for better concurrency (prevents most deadlocks/locks)
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables on startup."""
    async with engine.begin() as conn:
        # Import all models so they are registered on the Base metadata
        import models.recording  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency — yields a DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session
