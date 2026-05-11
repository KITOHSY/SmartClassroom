import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_select_one(pg_url: str) -> None:
    engine = create_async_engine(pg_url, future=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 AS v"))
            row = result.one()
            assert row.v == 1
    finally:
        await engine.dispose()
