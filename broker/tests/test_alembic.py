import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_all_tables_present(pg_url: str) -> None:
    expected = {"users", "hosts", "reservations", "sessions", "tokens", "audit_logs"}
    engine = create_async_engine(pg_url, future=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            tables = {row.tablename for row in result}
            assert expected.issubset(tables), f"missing: {expected - tables}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reservation_overlap_constraint_blocks(pg_url: str) -> None:
    """EXCLUDE GIST 제약 회귀 — 동일 호스트의 시간 겹침 INSERT가 거부되어야."""
    engine = create_async_engine(pg_url, future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO users (external_id, provider, display_name, role)
                    VALUES ('u1', 'mock', 'User One', 'user')
                    ON CONFLICT DO NOTHING
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO hosts (hostname, display_name)
                    VALUES ('host-overlap-test', 'Overlap Test Host')
                    ON CONFLICT DO NOTHING
                    """
                )
            )
            user_id = (
                await conn.execute(
                    text("SELECT id FROM users WHERE external_id = 'u1' AND provider = 'mock'")
                )
            ).scalar_one()
            host_id = (
                await conn.execute(
                    text("SELECT id FROM hosts WHERE hostname = 'host-overlap-test'")
                )
            ).scalar_one()

            await conn.execute(
                text(
                    """
                    INSERT INTO reservations (user_id, host_id, time_range, status)
                    VALUES (:u, :h,
                            tstzrange('2026-06-01 10:00+09', '2026-06-01 11:00+09', '[)'),
                            'CONFIRMED')
                    """
                ),
                {"u": user_id, "h": host_id},
            )

        # 겹치는 시간으로 INSERT 시도 → 제약 위반 예외
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        INSERT INTO reservations (user_id, host_id, time_range, status)
                        VALUES (:u, :h,
                                tstzrange('2026-06-01 10:30+09', '2026-06-01 11:30+09', '[)'),
                                'CONFIRMED')
                        """
                    ),
                    {"u": user_id, "h": host_id},
                )
    finally:
        await engine.dispose()
