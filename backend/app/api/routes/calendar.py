from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.db.database import get_db
from app.db.models import CalendarEvent
from app.events.bus import event_bus

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    all_day: bool = False
    attendees: List[str] = []
    color: Optional[str] = None
    recurrence: Optional[dict] = None


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    color: Optional[str] = None


@router.get("/events", response_model=List[dict])
async def list_events(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    q = select(CalendarEvent)
    if start:
        q = q.where(CalendarEvent.end_time >= start)
    if end:
        q = q.where(CalendarEvent.start_time <= end)
    q = q.order_by(CalendarEvent.start_time.asc())
    result = await db.execute(q)
    events = result.scalars().all()
    return [
        {
            "id": e.id, "title": e.title, "description": e.description,
            "start_time": e.start_time, "end_time": e.end_time,
            "location": e.location, "all_day": e.all_day,
            "attendees": e.attendees, "color": e.color,
            "recurrence": e.recurrence, "created_at": e.created_at,
        }
        for e in events
    ]


@router.post("/events", status_code=201)
async def create_event(event: CalendarEventCreate, db: AsyncSession = Depends(get_db)):
    db_event = CalendarEvent(**event.model_dump())
    db.add(db_event)
    await db.flush()
    await event_bus.publish("calendar.event.created", {
        "event_id": db_event.id, "title": db_event.title,
        "start_time": str(db_event.start_time),
    })
    return {
        "id": db_event.id, "title": db_event.title,
        "start_time": db_event.start_time, "end_time": db_event.end_time,
    }


@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "id": event.id, "title": event.title, "description": event.description,
        "start_time": event.start_time, "end_time": event.end_time,
        "location": event.location, "all_day": event.all_day,
        "attendees": event.attendees, "color": event.color,
    }


@router.patch("/events/{event_id}")
async def update_event(event_id: str, update: CalendarEventUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    event.updated_at = datetime.utcnow()
    return {"id": event.id, "title": event.title}


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(event_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)


@router.get("/events/upcoming/week")
async def upcoming_week(db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    week_end = now + timedelta(days=7)
    q = select(CalendarEvent).where(
        and_(CalendarEvent.start_time >= now, CalendarEvent.start_time <= week_end)
    ).order_by(CalendarEvent.start_time.asc())
    result = await db.execute(q)
    events = result.scalars().all()
    return [
        {"id": e.id, "title": e.title, "start_time": e.start_time,
         "end_time": e.end_time, "location": e.location}
        for e in events
    ]
