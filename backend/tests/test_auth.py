import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.security import HTTPAuthorizationCredentials

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.routes.auth import LoginRequest, RegisterRequest, login, me, register  # noqa: E402
from app.core.auth import get_auth_context, hash_password, verify_password  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.models import FamilyMember, User  # noqa: E402


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def test_password_hash_round_trip():
    hashed = hash_password("super-secret")
    assert hashed != "super-secret"
    assert verify_password("super-secret", hashed)
    assert not verify_password("wrong-password", hashed)


def test_register_login_and_me_flow(monkeypatch):
    async def _run():
        monkeypatch.setattr(settings, "secret_key", "test-secret-key")
        monkeypatch.setattr(settings, "api_bearer_token", "")
        monkeypatch.setattr(settings, "environment", "test")

        family_member = FamilyMember(name="Alex", email="alex@example.com", role="member")
        user = User(
            id="user-1",
            email="alex@example.com",
            password_hash=hash_password("strong-pass"),
            full_name="Alex Household",
            role="member",
            family_member_id="family-1",
        )
        user.family_member = family_member

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        db.execute = AsyncMock(
            side_effect=[
                FakeResult(None),
                FakeResult(family_member),
                FakeResult(user),
                FakeResult(user),
            ]
        )

        register_result = await register(
            RegisterRequest(
                email="alex@example.com",
                password="strong-pass",
                full_name="Alex Household",
            ),
            db=db,
        )

        assert register_result.user.email == "alex@example.com"
        assert register_result.user.family_member_name == "Alex"
        assert register_result.user.role == "member"
        assert register_result.access_token

        login_result = await login(
            LoginRequest(
                email="alex@example.com",
                password="strong-pass",
            ),
            db=db,
        )

        assert login_result.user.id == "user-1"
        assert login_result.token_type == "bearer"
        assert login_result.access_token
        assert user.last_login_at is not None

        auth_context = await get_auth_context(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=login_result.access_token,
            ),
            db=db,
        )

        assert auth_context.user is not None
        assert auth_context.user.email == "alex@example.com"
        assert auth_context.auth_type == "user"

        me_result = await me(current_user=auth_context.user)
        assert me_result.email == "alex@example.com"
        assert me_result.family_member_name == "Alex"

    asyncio.run(_run())


def test_get_auth_context_accepts_shared_api_token(monkeypatch):
    async def _run():
        monkeypatch.setattr(settings, "secret_key", "test-secret-key")
        monkeypatch.setattr(settings, "api_bearer_token", "shared-token")
        monkeypatch.setattr(settings, "environment", "production")

        db = MagicMock()
        db.execute = AsyncMock()

        auth_context = await get_auth_context(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="shared-token",
            ),
            db=db,
        )

        assert auth_context.user is None
        assert auth_context.auth_type == "api_token"

    asyncio.run(_run())


def test_register_bootstraps_family_member_when_missing(monkeypatch):
    async def _run():
        monkeypatch.setattr(settings, "secret_key", "test-secret-key")
        monkeypatch.setattr(settings, "api_bearer_token", "")
        monkeypatch.setattr(settings, "environment", "test")

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock(side_effect=[FakeResult(None), FakeResult(None)])

        result = await register(
            RegisterRequest(
                email="new@example.com",
                password="strong-pass",
                full_name="New Family Member",
            ),
            db=db,
        )

        added_types = [type(call.args[0]).__name__ for call in db.add.call_args_list]
        assert "FamilyMember" in added_types
        assert "User" in added_types
        assert result.user.family_member_name == "New Family Member"
        assert result.user.family_member_id is not None

    asyncio.run(_run())
