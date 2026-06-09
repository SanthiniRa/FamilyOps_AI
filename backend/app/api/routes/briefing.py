from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.daily_briefing_service import DailyFamilyBriefingService

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/daily")
async def daily_briefing(
    db: AsyncSession = Depends(get_db),
):
    service = DailyFamilyBriefingService()
    return await service.generate_briefing(db)