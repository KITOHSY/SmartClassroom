"""MockAuthProvider — 학번/이름 입력 → 즉시 사용자 식별.

개발/스테이징 전용. `broker.app.main._enforce_production_guards`가
APP_ENV=production일 때 부팅을 차단한다.
"""

from __future__ import annotations

import json

from broker.app.core.auth import UserIdentity
from fastapi import Request


class MockAuthProvider:
    name = "mock"

    async def initiate_login(self, request: Request) -> str:
        return "/api/v1/auth/mock/login"

    async def verify_callback(self, request: Request) -> UserIdentity:
        content_type = (request.headers.get("content-type") or "").lower()
        data: dict[str, str] = {}
        if "application/json" in content_type:
            raw = await request.body()
            try:
                parsed = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                raise ValueError("mock callback JSON 파싱 실패") from exc
            if not isinstance(parsed, dict):
                raise ValueError("mock callback 본문은 JSON object여야 합니다")
            for key, value in parsed.items():
                if isinstance(value, str):
                    data[key] = value
        else:
            form = await request.form()
            for key, value in form.items():
                if isinstance(value, str):
                    data[key] = value

        external_id = data.get("external_id", "").strip()
        display_name = data.get("display_name", "").strip()
        if not external_id or not display_name:
            raise ValueError("external_id, display_name은 둘 다 필수입니다")

        email = data.get("email") or None
        role = data.get("role") or "user"
        if role not in ("user", "admin"):
            raise ValueError(f"role 값이 잘못되었습니다: {role}")

        return UserIdentity(
            external_id=external_id,
            provider=self.name,
            display_name=display_name,
            email=email,
            role=role,
        )

    async def fetch_user_identity(self, token: str) -> UserIdentity:
        raise NotImplementedError(
            "Mock에서는 토큰 기반 식별을 지원하지 않습니다 — verify_callback을 사용하세요."
        )
