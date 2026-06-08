from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pantry_service import pantry_service
from app.db.models import Task, Reminder
from sqlalchemy import select


class DailyFamilyBriefingService:
    """
    Orchestrates daily household intelligence summary.
    """

    # ======================================================
    # PUBLIC ENTRY POINT
    # ======================================================
    async def generate_briefing(
        self,
        db: AsyncSession,
        email_service=None,
        calendar_service=None,
        bill_service=None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:

        # 1. EMAILS
        emails = await self._get_emails(email_service, user_id)

        # 2. CALENDAR
        calendar = await self._get_calendar(calendar_service, user_id)

        # 3. PANTRY
        pantry = await pantry_service.get_items(db)

        # 4. TASKS
        tasks = await self._get_tasks(db)

        # 5. BILLS
        bills = await self._get_bills(bill_service, user_id)

        # ================================
        # PROCESS INSIGHTS
        # ================================
        important_reminders = self._extract_important(tasks, emails, calendar)
        meal_suggestions = self._generate_meal_suggestions(pantry)
        summary_text = self._build_natural_summary(
            emails, calendar, pantry, tasks, bills
        )

        return {
            "summary": summary_text,
            "data": {
                "emails": emails,
                "calendar": calendar,
                "pantry": [
                    {
                        "name": i.name,
                        "quantity": i.quantity,
                        "unit": i.unit
                    }
                    for i in pantry
                ],
                "tasks": [
                    {
                        "title": t.title,
                        "status": t.status,
                        "due_date": t.due_date
                    }
                    for t in tasks
                ],
                "bills": bills,
            },
            "important_reminders": important_reminders,
            "meal_recommendations": meal_suggestions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # ======================================================
    # DATA COLLECTION LAYERS
    # ======================================================

    async def _get_emails(self, email_service, user_id):
        if not email_service:
            return []
        try:
            return await email_service.get_recent_emails(user_id=user_id)
        except Exception:
            return []

    async def _get_calendar(self, calendar_service, user_id):
        if not calendar_service:
            return []
        try:
            return await calendar_service.get_today_events(user_id=user_id)
        except Exception:
            return []

    async def _get_tasks(self, db: AsyncSession):
        result = await db.execute(
            select(Task).where(Task.status != "completed")
        )
        return result.scalars().all()

    async def _get_bills(self, bill_service, user_id):
        if not bill_service:
            return []
        try:
            return await bill_service.get_due_bills(user_id=user_id)
        except Exception:
            return []

    # ======================================================
    # INSIGHT ENGINE
    # ======================================================

    def _extract_important(self, tasks, emails, calendar) -> List[str]:
        important = []

        # urgent tasks
        for t in tasks:
            if getattr(t, "priority", None) == "high":
                important.append(f"High priority task: {t.title}")

        # calendar conflicts
        if len(calendar) > 5:
            important.append("Busy schedule today with multiple events")

        # email alerts
        for e in emails:
            if "urgent" in str(e).lower():
                important.append("Urgent email requires attention")

        return important

    def _generate_meal_suggestions(self, pantry) -> List[str]:
        pantry_items = {i.name for i in pantry}

        suggestions = []

        if "eggs" in pantry_items:
            suggestions.append("Egg-based breakfast options available")

        if "rice" in pantry_items:
            suggestions.append("Rice-based meals possible for lunch/dinner")

        if not suggestions:
            suggestions.append("Consider simple pantry-based meals today")

        return suggestions

    def _build_natural_summary(self, emails, calendar, pantry, tasks, bills) -> str:
        return f"""
Good morning 👋

You have {len(emails)} new emails and {len(calendar)} scheduled events today.

There are {len(tasks)} pending tasks and {len(bills)} upcoming bills.

Your pantry has {len(pantry)} items available for meals today.

Overall, your day looks {"busy" if len(calendar) > 3 else "light"} with a focus on task completion and household management.
""".strip()