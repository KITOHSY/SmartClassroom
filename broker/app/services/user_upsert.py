"""User upsert — Provider 콜백 직후 호출.

(provider, external_id) UNIQUE 제약(uq_users_provider_external) 위에서
PostgreSQL ON CONFLICT DO UPDATE 한 번에 처리. display_name/email은
매 로그인마다 갱신, role/is_active는 보존 — 관리자가 사후 조정한 값을 덮어쓰지 않기 위함.
commit은 호출자 책임.
"""

from __future__ import annotations

from broker.app.core.auth import UserIdentity
from broker.app.domain.user import User
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_user(session: AsyncSession, identity: UserIdentity) -> User:
    stmt = (
        pg_insert(User)
        .values(
            provider=identity.provider,
            external_id=identity.external_id,
            display_name=identity.display_name,
            email=identity.email,
            role=identity.role,
        )
        .on_conflict_do_update(
            constraint="uq_users_provider_external",
            set_={
                "display_name": identity.display_name,
                "email": identity.email,
            },
        )
        .returning(User.id)
    )
    inserted_id = (await session.execute(stmt)).scalar_one()
    user = await session.get(User, inserted_id)
    if user is None:  # 같은 트랜잭션 내 RETURNING 직후엔 항상 존재해야 함
        raise RuntimeError(f"upsert_user 직후 User(id={inserted_id}) 조회 실패")
    return user
