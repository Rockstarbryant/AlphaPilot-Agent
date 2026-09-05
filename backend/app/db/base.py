from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings, sanitize_database_url

settings = get_settings()

_connect_args = {}
if "sslmode=require" in settings.database_url or "supabase" in settings.database_url or "neon.tech" in settings.database_url:
    _connect_args["ssl"] = True

engine = create_async_engine(
    sanitize_database_url(settings.database_url),
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session