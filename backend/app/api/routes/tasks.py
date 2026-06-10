from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from enum import Enum

from app.core.auth import get_optional_current_user
from app.core.ownership import get_owner_family_member_id, with_owner_metadata
from app.db.database import get_db
from app.db.models import Task
from app.events.bus import event_bus
from app.db.models import User

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ============================================================
# ENUMS
# ============================================================

class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in-progress"
    completed = "completed"


class TaskPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# ============================================================
# SCHEMAS
# ============================================================

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.pending
    priority: TaskPriority = TaskPriority.medium
    due_date: Optional[datetime] = None
    assignee_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[datetime] = None
    assignee_id: Optional[str] = None
    tags: Optional[List[str]] = None


class TaskResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    status: str
    priority: str
    due_date: Optional[datetime]
    assignee_id: Optional[str]
    created_by: Optional[str] = None
    tags: List[str]
    agent_generated: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _apply_owner_scope(query, owner_family_member_id: Optional[str]):
    if owner_family_member_id:
        query = query.where(
            or_(
                Task.created_by.is_(None),
                Task.created_by == owner_family_member_id,
            )
        )
    return query


# ============================================================
# TASK STATS
# IMPORTANT:
# Must be BEFORE /{task_id}
# ============================================================

@router.get("/stats/summary")
async def task_stats(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)

    query = select(Task)
    query = _apply_owner_scope(query, owner_family_member_id)
    result = await db.execute(query)
    tasks = result.scalars().all()

    stats = {
        "total": len(tasks),
        "by_status": {},
        "by_priority": {},
        "overdue": 0,
        "agent_generated": 0,
    }

    now = datetime.now(timezone.utc)

    for t in tasks:

        stats["by_status"][t.status] = (
            stats["by_status"].get(t.status, 0) + 1
        )

        stats["by_priority"][t.priority] = (
            stats["by_priority"].get(t.priority, 0) + 1
        )

        if t.agent_generated:
            stats["agent_generated"] += 1

        if (
            t.due_date
            and t.due_date < now
            and t.status != TaskStatus.completed
        ):
            stats["overdue"] += 1

    return stats


# ============================================================
# LIST TASKS
# ============================================================

@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    query = select(Task)
    owner_family_member_id = get_owner_family_member_id(current_user)
    query = _apply_owner_scope(query, owner_family_member_id)

    if status:
        query = query.where(Task.status == status)

    if priority:
        query = query.where(Task.priority == priority)

    if assignee_id:
        query = query.where(
            Task.assignee_id == assignee_id
        )

    query = query.order_by(
        Task.created_at.desc()
    )

    result = await db.execute(query)

    return result.scalars().all()


# ============================================================
# CREATE TASK
# ============================================================

@router.post(
    "",
    response_model=TaskResponse,
    status_code=201
)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)
    db_task = Task(
        **task.model_dump(),
        created_by=owner_family_member_id,
        extra_data=with_owner_metadata({}, owner_family_member_id),
    )

    db.add(db_task)

    await db.commit()
    await db.refresh(db_task)

    await event_bus.publish(
        "task.created",
        {
            "task_id": db_task.id,
            "title": db_task.title
        }
    )

    return db_task


# ============================================================
# GET TASK
# ============================================================

@router.get(
    "/{task_id}",
    response_model=TaskResponse
)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)
    query = select(Task).where(Task.id == task_id)
    query = _apply_owner_scope(query, owner_family_member_id)
    result = await db.execute(query)

    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Task not found"
        )

    return task


# ============================================================
# UPDATE TASK
# ============================================================

@router.patch(
    "/{task_id}",
    response_model=TaskResponse
)
async def update_task(
    task_id: str,
    task_update: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)
    query = select(Task).where(Task.id == task_id)
    query = _apply_owner_scope(query, owner_family_member_id)
    result = await db.execute(query)

    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Task not found"
        )

    update_data = task_update.model_dump(
        exclude_unset=True
    )

    for field, value in update_data.items():
        setattr(task, field, value)

    task.updated_at = datetime.now(
        timezone.utc
    )

    await db.commit()
    await db.refresh(task)

    if (
        "status" in update_data
        and task.status == TaskStatus.completed
    ):
        await event_bus.publish(
            "task.completed",
            {
                "task_id": task.id
            }
        )

    return task


# ============================================================
# DELETE TASK
# ============================================================

@router.delete(
    "/{task_id}",
    status_code=204
)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    owner_family_member_id = get_owner_family_member_id(current_user)
    query = select(Task).where(Task.id == task_id)
    query = _apply_owner_scope(query, owner_family_member_id)
    result = await db.execute(query)

    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Task not found"
        )

    await db.delete(task)
    await db.commit()

    return
