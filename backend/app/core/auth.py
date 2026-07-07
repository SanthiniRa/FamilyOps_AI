from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User


ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)
password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@dataclass(slots=True)
class AuthContext:
    auth_type: str
    user: Optional[User] = None

    @property
    def is_user_authenticated(self) -> bool:
        return self.user is not None


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return password_context.verify(plain_password, password_hash)


def create_access_token(subject: str, *, expires_delta: Optional[timedelta] = None, extra_claims: Optional[dict] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _extract_bearer_token(credentials: HTTPAuthorizationCredentials | None) -> Optional[str]:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return None


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    token = _extract_bearer_token(credentials)

    if token:
        if settings.api_bearer_token and token == settings.api_bearer_token:
            return AuthContext(auth_type="api_token")

        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        subject = payload.get("sub")
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject",
                headers={"WWW-Authenticate": "Bearer"},
            )

        result = await db.execute(
            select(User)
            .options(selectinload(User.family_member))
            .where(User.id == subject)
        )
        user = result.scalar_one_or_none()
        if not user or user.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return AuthContext(auth_type="user", user=user)

    if settings.environment == "development" and not settings.api_bearer_token:
        return AuthContext(auth_type="development")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials were not provided",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_auth(
    auth_context: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    return auth_context


async def get_current_user(
    auth_context: AuthContext = Depends(get_auth_context),
) -> User:
    if auth_context.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_context.user


async def get_optional_current_user(
    auth_context: AuthContext = Depends(get_auth_context),
) -> Optional[User]:
    return auth_context.user


# Backwards-compatible alias for the existing protected route dependency.
require_api_token = require_auth
