from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.core.auth import get_optional_current_user
from app.core.ownership import get_owner_family_member_id, with_owner_metadata
from app.db.database import get_db
from app.db.models import Reminder, User
from app.events.bus import event_bus

router = APIRouter(prefix="/reminders", tags=["reminders"])


class ReminderCreate(BaseModel):
    title: str
    body: Optional[str] = None
    remind_at: datetime
    recurrence: Optional[str] = None
    member_id: Optional[str] = None
    channel: str = "app"


class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    remind_at: Optional[datetime] = None
    status: Optional[str] = None
    recurrence: Optional[str] = None


@router.get("", response_model=List[dict])
@router.get("/", response_model=List[dict])
async def list_reminders(
    status: Optional[str] = Query(None),
    member_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)

    q = select(Reminder)
    if status:
        q = q.where(Reminder.status == status)
    if owner_family_member_id:
        q = q.where(
            or_(
                Reminder.member_id.is_(None),
                Reminder.member_id == owner_family_member_id,
            )
        )
    elif member_id:
        q = q.where(Reminder.member_id == member_id)
    q = q.order_by(Reminder.remind_at.asc())
    result = await db.execute(q)
    reminders = result.scalars().all()
    return [
        {
            "id": r.id, "title": r.title, "body": r.body,
            "remind_at": r.remind_at, "recurrence": r.recurrence,
            "member_id": r.member_id, "channel": r.channel,
            "status": r.status, "created_at": r.created_at,
        }
        for r in reminders
    ]


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_reminder(
    reminder: ReminderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)
    reminder_data = reminder.model_dump()
    if owner_family_member_id:
        reminder_data["member_id"] = owner_family_member_id
        reminder_data["extra_data"] = with_owner_metadata(reminder_data.get("extra_data"), owner_family_member_id)

    db_reminder = Reminder(**reminder_data)
    db.add(db_reminder)
    await db.flush()
    await event_bus.publish("reminder.created", {
        "reminder_id": db_reminder.id,
        "title": db_reminder.title,
        "remind_at": str(db_reminder.remind_at),
    })
    await db.commit()
    await db.refresh(db_reminder)
    return {
        "id": db_reminder.id, "title": db_reminder.title,
        "remind_at": db_reminder.remind_at, "status": db_reminder.status,
    }


@router.get("/{reminder_id}")
@router.get("/{reminder_id}/")
async def get_reminder(
    reminder_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)
    result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if owner_family_member_id and reminder.member_id not in (None, owner_family_member_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {
        "id": reminder.id, "title": reminder.title, "body": reminder.body,
        "remind_at": reminder.remind_at, "recurrence": reminder.recurrence,
        "member_id": reminder.member_id, "channel": reminder.channel,
        "status": reminder.status, "created_at": reminder.created_at,
    }


@router.patch("/{reminder_id}")
@router.patch("/{reminder_id}/")
async def update_reminder(
    reminder_id: str,
    update: ReminderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)
    result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if owner_family_member_id and reminder.member_id not in (None, owner_family_member_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(reminder, field, value)
    await db.commit()
    return {"id": reminder.id, "title": reminder.title, "status": reminder.status}


@router.delete("/{reminder_id}", status_code=204)
@router.delete("/{reminder_id}/", status_code=204)
async def delete_reminder(
    reminder_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)
    result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if owner_family_member_id and reminder.member_id not in (None, owner_family_member_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    await db.delete(reminder)
    await db.commit()


@router.get("/upcoming/today")
@router.get("/upcoming/today/")
async def upcoming_today(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    from datetime import date
    owner_family_member_id = get_owner_family_member_id(current_user)
    today = datetime.combine(date.today(), datetime.min.time())
    tomorrow = today + __import__('datetime').timedelta(days=1)
    q = select(Reminder).where(
        Reminder.remind_at >= today,
        Reminder.remind_at < tomorrow,
        Reminder.status == "pending"
    )
    if owner_family_member_id:
        q = q.where(
            (Reminder.member_id.is_(None)) | (Reminder.member_id == owner_family_member_id)
        )
    result = await db.execute(q)
    reminders = result.scalars().all()
    return [
        {"id": r.id, "title": r.title, "remind_at": r.remind_at, "channel": r.channel}
        for r in reminders
    ]
