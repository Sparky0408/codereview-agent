"""Database session management.

Provides the engine and async session maker for SQLAlchemy.
"""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.debug)

async_session = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)
