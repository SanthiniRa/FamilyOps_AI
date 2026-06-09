import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from app.db.database import get_db
from app.db.models import FamilyMember

router = APIRouter(prefix="/family", tags=["family"])


class FamilyMemberCreate(BaseModel):
    name: str
    email: Optional[str] = None
    role: str = "member"
    avatar_url: Optional[str] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)
    dietary_restrictions: List[str] = Field(default_factory=list)


class FamilyMemberUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[dict] = None
    dietary_restrictions: Optional[List[str]] = None


def _parse_json_value(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return fallback
        return parsed if isinstance(parsed, type(fallback)) else fallback

    if isinstance(value, type(fallback)):
        return value

    return fallback


def _serialize_member(member: FamilyMember) -> dict:
    return {
        "id": member.id,
        "name": member.name,
        "email": member.email,
        "role": member.role,
        "avatar_url": member.avatar_url,
        "preferences": _parse_json_value(member.preferences, {}),
        "dietary_restrictions": _parse_json_value(member.dietary_restrictions, []),
        "created_at": member.created_at,
        "updated_at": member.updated_at,
    }


@router.get("/members", response_model=List[dict])
async def list_members(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FamilyMember).order_by(FamilyMember.created_at.asc()))
    members = result.scalars().all()
    return [_serialize_member(m) for m in members]


@router.post("/members", status_code=201)
async def create_member(member: FamilyMemberCreate, db: AsyncSession = Depends(get_db)):
    db_member = FamilyMember(**member.model_dump())
    db.add(db_member)
    await db.flush()
    await db.commit()
    await db.refresh(db_member)
    return _serialize_member(db_member)


@router.get("/members/{member_id}")
async def get_member(member_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FamilyMember).where(FamilyMember.id == member_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Family member not found")
    return _serialize_member(member)


@router.patch("/members/{member_id}")
async def update_member(
    member_id: str, update: FamilyMemberUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(FamilyMember).where(FamilyMember.id == member_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Family member not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    member.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(member)
    return _serialize_member(member)


@router.delete("/members/{member_id}", status_code=204)
async def delete_member(member_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FamilyMember).where(FamilyMember.id == member_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Family member not found")
    await db.delete(member)
    await db.commit()
