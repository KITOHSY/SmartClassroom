"""운영 가드 회귀 — _enforce_production_guards 직접 호출 시나리오."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

_GUARDED_KEYS = ("APP_ENV", "AUTH_PROVIDER", "SESSION_SECRET", "SESSION_COOKIE_SECURE")


def _reset_settings() -> None:
    from broker.app.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_env() -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in _GUARDED_KEYS}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _reset_settings()


def test_production_with_mock_provider_raises() -> None:
    os.environ["APP_ENV"] = "production"
    os.environ["AUTH_PROVIDER"] = "mock"
    os.environ["SESSION_SECRET"] = "32-bytes-strong-secret-for-prod-please"
    os.environ["SESSION_COOKIE_SECURE"] = "true"
    _reset_settings()
    from broker.app.core.config import get_settings
    from broker.app.main import _enforce_production_guards

    with pytest.raises(RuntimeError, match="MockAuthProvider"):
        _enforce_production_guards(get_settings())


def test_production_with_weak_session_secret_raises() -> None:
    os.environ["APP_ENV"] = "production"
    os.environ["AUTH_PROVIDER"] = "cnu_sso"
    os.environ["SESSION_SECRET"] = "change-me"
    os.environ["SESSION_COOKIE_SECURE"] = "true"
    _reset_settings()
    from broker.app.core.config import get_settings
    from broker.app.main import _enforce_production_guards

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        _enforce_production_guards(get_settings())


def test_production_with_insecure_cookie_raises() -> None:
    os.environ["APP_ENV"] = "production"
    os.environ["AUTH_PROVIDER"] = "cnu_sso"
    os.environ["SESSION_SECRET"] = "32-bytes-strong-secret-for-prod-please"
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    _reset_settings()
    from broker.app.core.config import get_settings
    from broker.app.main import _enforce_production_guards

    with pytest.raises(RuntimeError, match="SESSION_COOKIE_SECURE"):
        _enforce_production_guards(get_settings())


def test_development_allows_mock() -> None:
    os.environ["APP_ENV"] = "development"
    os.environ["AUTH_PROVIDER"] = "mock"
    os.environ["SESSION_SECRET"] = "change-me"
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    _reset_settings()
    from broker.app.core.config import get_settings
    from broker.app.main import _enforce_production_guards

    # should not raise
    _enforce_production_guards(get_settings())
