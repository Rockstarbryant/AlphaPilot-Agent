from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# asyncpg's connect() only accepts a limited set of kwargs, but SQLAlchemy
# forwards EVERY query-string param on the URL straight into it. Supabase/
# Neon-style connection strings (meant for psycopg/libpq) commonly include
# `channel_binding` and `sslmode`, which asyncpg rejects with:
#   TypeError: connect() got an unexpected keyword argument 'channel_binding'
# Strip those out here so the same DATABASE_URL works regardless of where
# it was copied from.
_ASYNCPG_UNSUPPORTED_PARAMS = {"channel_binding", "sslmode", "options", "target_session_attrs"}


def _sanitize_database_url(url: str) -> str:
    parts = urlsplit(url)
    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _ASYNCPG_UNSUPPORTED_PARAMS
    ]
    new_query = urlencode(query_pairs)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


# If the connection needs SSL (Supabase/Neon/most managed Postgres do), pass
# it via connect_args instead of the sslmode query param, since asyncpg
# expects ssl=True/context, not sslmode=require.
_connect_args = {}
if "sslmode=require" in settings.database_url or "supabase" in settings.database_url or "neon.tech" in settings.database_url:
    _connect_args["ssl"] = True

engine = create_async_engine(
    _sanitize_database_url(settings.database_url),
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