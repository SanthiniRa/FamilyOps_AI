from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.resilience import enforce_search_rate_limit
from app.services.weather_service import weather_service


router = APIRouter(prefix="/weather", tags=["weather"], dependencies=[Depends(enforce_search_rate_limit)])


class WeatherSearchRequest(BaseModel):
    location: str = Field(..., min_length=1)
    forecast_days: Optional[int] = Field(default=None, ge=1, le=16)
    country_code: Optional[str] = Field(default=None, min_length=2, max_length=2)


@router.post("/search")
async def search_weather(request: WeatherSearchRequest):
    return await weather_service.search(
        request.location,
        forecast_days=request.forecast_days,
        country_code=request.country_code,
    )
