from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.resilience import enforce_search_rate_limit
from app.services.web_search_service import web_search_service


router = APIRouter(prefix="/web", tags=["web-search"], dependencies=[Depends(enforce_search_rate_limit)])


class WebSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: Optional[int] = Field(default=None, ge=1, le=10)
    fetch_pages: bool = True


@router.post("/search")
async def search_web(request: WebSearchRequest):
    return await web_search_service.search(
        request.query,
        max_results=request.max_results,
        fetch_pages=request.fetch_pages,
    )
