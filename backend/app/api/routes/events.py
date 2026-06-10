from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.resilience import enforce_search_rate_limit
from app.services.event_search_service import event_search_service


router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(enforce_search_rate_limit)])


class EventSearchRequest(BaseModel):
    query: Optional[str] = None
    location: Optional[str] = None
    postal_code: Optional[str] = None
    radius_miles: Optional[int] = Field(default=None, ge=1, le=100)
    family_friendly: bool = True
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    max_results: int = Field(default=10, ge=1, le=20)


@router.post("/search")
async def search_events(request: EventSearchRequest):
    return await event_search_service.search(
        query=request.query,
        location=request.location,
        postal_code=request.postal_code,
        radius_miles=request.radius_miles,
        family_friendly=request.family_friendly,
        start_date=request.start_date,
        end_date=request.end_date,
        max_results=request.max_results,
    )
