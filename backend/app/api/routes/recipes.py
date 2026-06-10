from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.resilience import enforce_search_rate_limit
from app.services.recipe_search_service import recipe_search_service


router = APIRouter(prefix="/recipes", tags=["recipes"], dependencies=[Depends(enforce_search_rate_limit)])


class RecipeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=10, ge=1, le=20)
    ingredient: Optional[str] = None
    category: Optional[str] = None


@router.post("/search")
async def search_recipes(request: RecipeSearchRequest):
    return await recipe_search_service.search(
        request.query,
        max_results=request.max_results,
        ingredient=request.ingredient,
        category=request.category,
    )
