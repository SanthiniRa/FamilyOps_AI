from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from app.db.database import get_db
from app.db.models import AgentRun, Task, CalendarEvent, GroceryList, GroceryItem, Reminder, Memory, MealPlan, FamilyMember, PantryItem
from app.agents.orchestrator import orchestrator
from app.services.pantry_service import pantry_service

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)


async def _fetch_db_context(db: AsyncSession) -> Dict[str, Any]:
    """Pre-fetch relevant household data to give the LLM real context."""
    now = datetime.utcnow()
    week_ahead = now + timedelta(days=7)

    # Tasks
    tasks_result = await db.execute(select(Task).order_by(Task.created_at.desc()).limit(20))
    tasks = tasks_result.scalars().all()

    # Upcoming calendar events
    events_result = await db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.start_time >= now, CalendarEvent.start_time <= week_ahead)
        .order_by(CalendarEvent.start_time.asc()).limit(10)
    )
    events = events_result.scalars().all()

    # Pending reminders
    reminders_result = await db.execute(
        select(Reminder).where(Reminder.status == "pending")
        .order_by(Reminder.remind_at.asc()).limit(10)
    )
    reminders = reminders_result.scalars().all()

    # Active grocery lists with items
    lists_result = await db.execute(
        select(GroceryList).where(GroceryList.status == "active").limit(5)
    )
    grocery_lists = lists_result.scalars().all()
    grocery_data = []
    for gl in grocery_lists:
        items_result = await db.execute(select(GroceryItem).where(GroceryItem.list_id == gl.id))
        items = items_result.scalars().all()
        grocery_data.append({
            "name": gl.name, "store": gl.store,
            "items": [{"name": i.name, "checked": i.checked, "quantity": i.quantity} for i in items],
        })

    # Pantry inventory and low stock items
    pantry_result = await db.execute(
        select(PantryItem).order_by(PantryItem.category, PantryItem.name)
    )
    pantry_items = pantry_result.scalars().all()
    low_stock_items = await pantry_service.get_low_stock_items(db)

    # Latest meal plan
    plans_result = await db.execute(
        select(MealPlan).order_by(MealPlan.week_start.desc()).limit(2)
    )
    plans = plans_result.scalars().all()

    # Memories
    memories_result = await db.execute(
        select(Memory).order_by(Memory.created_at.desc()).limit(15)
    )
    memories = memories_result.scalars().all()

    # Family members
    members_result = await db.execute(select(FamilyMember))
    members = members_result.scalars().all()

    return {
        "tasks": [
            {
                "id": t.id, "title": t.title, "status": t.status,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "overdue": bool(t.due_date and t.due_date < now and t.status != "completed"),
            }
            for t in tasks
        ],
        "events": [
            {
                "id": e.id, "title": e.title,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat(),
                "location": e.location,
            }
            for e in events
        ],
        "reminders": [
            {
                "id": r.id, "title": r.title, "body": r.body,
                "remind_at": r.remind_at.isoformat(),
                "status": r.status, "recurrence": r.recurrence,
            }
            for r in reminders
        ],
        "grocery_lists": grocery_data,
        "pantry_items": [
            {
                "name": p.name,
                "quantity": p.quantity,
                "unit": p.unit,
                "category": p.category,
                "min_quantity": p.min_quantity,
            }
            for p in pantry_items
        ],
        "low_stock_pantry": [
            {
                "name": p.name,
                "quantity": p.quantity,
                "unit": p.unit,
                "category": p.category,
                "min_quantity": p.min_quantity,
            }
            for p in low_stock_items
        ],
        "meal_plans": [
            {
                "week_start": p.week_start.isoformat(),
                "meals": p.meals,
                "generated_by_ai": p.generated_by_ai,
                "shopping_list": (p.result or {}).get("shopping_list", []),
            }
            for p in plans
        ],
        "memories": [
            {
                "id": m.id,
                "content": m.content,
                "memory_type": m.memory_type,
                "category": m.memory_type,
                "importance": (m.memory_metadata or {}).get("importance"),
                "tags": (m.memory_metadata or {}).get("tags", []),
            }
            for m in memories
        ],
        "family_members": [
            {
                "id": m.id, "name": m.name, "role": m.role,
                "dietary_restrictions": m.dietary_restrictions or [],
                "preferences": m.preferences or {},
            }
            for m in members
        ],
    }


@router.post("/chat")
async def chat_with_agent(request: AgentRequest, db: AsyncSession = Depends(get_db)):
    import time
    start = time.time()

    run = AgentRun(
        agent_name="orchestrator",
        status="running",
        input_data={"message": request.message, "context": request.context},
    )
    db.add(run)
    await db.flush()

    try:
        # Pre-fetch real household data for the LLM
        db_context = await _fetch_db_context(db)
        merged_context = {**request.context, "db_context": db_context, "db": db}

        result = await orchestrator.run(request.message, merged_context)
        duration_ms = int((time.time() - start) * 1000)

        run.status = result.get("status", "completed")
        run.output_data = {
            "reply": result.get("reply", ""),
            "tools_called": result.get("tools_called", []),
            "resource": result.get("context", {}).get("resource"),
        }
        run.tokens_used = int(result.get("tokens_used") or 0)
        run.duration_ms = duration_ms
        run.completed_at = datetime.utcnow()

        return {
            "run_id": run.id,
            "status": run.status,
            "reply": result.get("reply", ""),
            "resource": result.get("context", {}).get("resource"),
            "result": result,
            "tokens_used": run.tokens_used,
            "duration_ms": duration_ms,
        }
    except Exception as e:
        run.status = "failed"
        run.error = str(e)
        run.completed_at = datetime.utcnow()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", response_model=List[dict])
async def list_agent_runs(
    limit: int = 20,
    agent_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    q = select(AgentRun)
    if agent_name:
        q = q.where(AgentRun.agent_name == agent_name)
    q = q.order_by(AgentRun.started_at.desc()).limit(limit)
    result = await db.execute(q)
    runs = result.scalars().all()
    return [
        {
            "id": r.id, "agent_name": r.agent_name, "workflow_id": r.workflow_id,
            "status": r.status, "tokens_used": r.tokens_used,
            "duration_ms": r.duration_ms, "started_at": r.started_at,
            "completed_at": r.completed_at,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return {
        "id": run.id, "agent_name": run.agent_name, "workflow_id": run.workflow_id,
        "status": run.status, "input_data": run.input_data, "output_data": run.output_data,
        "steps": run.steps, "tokens_used": run.tokens_used,
        "duration_ms": run.duration_ms, "error": run.error,
        "started_at": run.started_at, "completed_at": run.completed_at,
    }


@router.get("/stats")
async def agent_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentRun))
    runs = result.scalars().all()
    return {
        "total_runs": len(runs),
        "by_status": {
            status: sum(1 for r in runs if r.status == status)
            for status in ["running", "completed", "failed"]
        },
        "total_tokens": sum(r.tokens_used or 0 for r in runs),
        "avg_duration_ms": (
            sum(r.duration_ms or 0 for r in runs if r.duration_ms) /
            max(1, sum(1 for r in runs if r.duration_ms))
        ),
    }


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            db_context = await _fetch_db_context(db)
            result = await orchestrator.run(message, {"db_context": db_context, "db": db})
            await websocket.send_json({
                "type": "agent_response",
                "reply": result.get("reply", ""),
                "resource": result.get("context", {}).get("resource"),
                "result": result,
                "timestamp": datetime.utcnow().isoformat(),
            })
    except WebSocketDisconnect:
        pass
