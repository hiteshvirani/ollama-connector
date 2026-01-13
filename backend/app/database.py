"""Database connection and session management."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import get_settings


settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


async def get_db() -> AsyncSession:
    """Dependency that provides a database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
