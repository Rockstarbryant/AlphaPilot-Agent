import asyncio
import os

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://alphapilot:alphapilot@127.0.0.1:5432/alphapilot")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    """
    Shared, correctly-isolated DB session fixture. A prior version of this
    fixture (duplicated per-test-file) called session.rollback() after the
    test, but code under test calls db.commit() internally — a commit
    can't be undone by a later rollback, so every test run was leaving real
    rows in the dev database (confirmed: 18 leftover Position rows found
    from repeated test runs before this fix).

    Fix: open one outer transaction per test, bind the session to it with
    join_transaction_mode="create_savepoint" so any commit() the code under
    test issues becomes a SAVEPOINT release instead of a real COMMIT, then
    roll back the outer transaction unconditionally at teardown. This is
    the standard SQLAlchemy pattern for testing code that commits.
    expire_on_commit=False avoids a second issue this surfaced: with the
    default expire-on-commit behavior, accessing an attribute on an object
    after commit() triggers a lazy reload outside the async greenlet
    context this manually-bound session sets up, raising MissingGreenlet.
    """
    from app.db.base import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    connection = await engine.connect()
    outer_transaction = await connection.begin()

    from sqlalchemy.ext.asyncio import AsyncSession
    session = AsyncSession(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False,
    )

    try:
        yield session
    finally:
        await session.close()
        await outer_transaction.rollback()
        await connection.close()
