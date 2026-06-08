from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.db.database import get_db
from app.db.models import FamilyMember

router = APIRouter(prefix="/family", tags=["family"])


class FamilyMemberCreate(BaseModel):
    name: str
    email: Optional[str] = None
    role: str = "member"
    avatar_url: Optional[str] = None
    preferences: dict = {}
    dietary_restrictions: List[str] = []


class FamilyMemberUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[dict] = None
    dietary_restrictions: Optional[List[str]] = None


@router.get("/members", response_model=List[dict])
async def list_members(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FamilyMember).order_by(FamilyMember.created_at.asc()))
    members = result.scalars().all()
    return [
        {
            "id": m.id, "name": m.name, "email": m.email, "role": m.role,
            "avatar_url": m.avatar_url, "preferences": m.preferences,
            "dietary_restrictions": m.dietary_restrictions, "created_at": m.created_at,
        }
        for m in members
    ]


@router.post("/members", status_code=201)
async def create_member(member: FamilyMemberCreate, db: AsyncSession = Depends(get_db)):
    db_member = FamilyMember(**member.model_dump())
    db.add(db_member)
    await db.flush()
    return {
        "id": db_member.id, "name": db_member.name, "email": db_member.email,
        "role": db_member.role, "created_at": db_member.created_at,
    }


@router.get("/members/{member_id}")
async def get_member(member_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FamilyMember).where(FamilyMember.id == member_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Family member not found")
    return {
        "id": member.id, "name": member.name, "email": member.email,
        "role": member.role, "avatar_url": member.avatar_url,
        "preferences": member.preferences, "dietary_restrictions": member.dietary_restrictions,
    }


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
    return {"id": member.id, "name": member.name, "role": member.role}


@router.delete("/members/{member_id}", status_code=204)
async def delete_member(member_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FamilyMember).where(FamilyMember.id == member_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Family member not found")
    await db.delete(member)
