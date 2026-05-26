from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from app.db.database import get_db
from app.db.models import AgentRun
from app.agents.orchestrator import orchestrator

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    message: str
    context: Dict[str, Any] = {}


class AgentRunResponse(BaseModel):
    id: str
    agent_name: str
    status: str
    input_data: Dict
    output_data: Dict
    tokens_used: int
    duration_ms: Optional[int]
    started_at: datetime


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
        result = await orchestrator.run(request.message, request.context)
        duration_ms = int((time.time() - start) * 1000)

        run.status = result.get("status", "completed")
        run.output_data = result
        run.duration_ms = duration_ms
        run.completed_at = datetime.utcnow()

        return {
            "run_id": run.id,
            "status": run.status,
            "result": result,
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
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            result = await orchestrator.run(message)
            await websocket.send_json({
                "type": "agent_response",
                "result": result,
                "timestamp": datetime.utcnow().isoformat(),
            })
    except WebSocketDisconnect:
        pass
