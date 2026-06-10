from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.database import get_db
from app.db.models import FamilyMember, User, UserRole, gen_uuid


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    family_member_id: Optional[str] = None
    family_member_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def _serialize_user(user: User) -> UserResponse:
    family_member = getattr(user, "family_member", None)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        is_active=True if user.is_active is None else bool(user.is_active),
        is_verified=False if user.is_verified is None else bool(user.is_verified),
        family_member_id=user.family_member_id,
        family_member_name=family_member.name if family_member else None,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


def _role_value(user: User) -> str:
    role = getattr(user, "role", None)
    if hasattr(role, "value"):
        return role.value
    if role is None:
        return UserRole.MEMBER.value
    return str(role)


async def _load_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(
        select(User)
        .options(selectinload(User.family_member))
        .where(User.email == email.lower().strip())
    )
    return result.scalar_one_or_none()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = request.email.lower().strip()
    existing_user = await _load_user_by_email(db, email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    family_member = None
    family_member_result = await db.execute(select(FamilyMember).where(FamilyMember.email == email))
    family_member = family_member_result.scalar_one_or_none()
    if family_member is None:
        full_name = request.full_name or email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
        family_member = FamilyMember(
            name=full_name,
            email=email,
            role=UserRole.MEMBER.value,
        )
        db.add(family_member)
        await db.flush()
        if not family_member.id:
            family_member.id = gen_uuid()

    user = User(
        email=email,
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        role=UserRole.MEMBER,
        family_member_id=family_member.id if family_member else None,
        is_active=True,
        is_verified=False,
    )
    if family_member:
        user.family_member = family_member

    db.add(user)
    await db.flush()
    if not user.id:
        user.id = gen_uuid()
    await db.refresh(user)

    access_token = create_access_token(
        user.id,
        extra_claims={
            "email": user.email,
            "role": _role_value(user),
            "family_member_id": user.family_member_id,
        },
    )

    return TokenResponse(access_token=access_token, user=_serialize_user(user))


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await _load_user_by_email(db, request.email)
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.is_active is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(
        user.id,
        extra_claims={
            "email": user.email,
            "role": _role_value(user),
            "family_member_id": user.family_member_id,
        },
    )

    return TokenResponse(access_token=access_token, user=_serialize_user(user))


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _serialize_user(current_user)
