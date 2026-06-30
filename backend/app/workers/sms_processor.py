"""
SMS Appointment Processor
Reads an SmsMessage from the DB, uses Gemini AI to detect if it's an
appointment/medical SMS, extracts structured details, then creates Tasks
and CalendarEvents automatically.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.db.models import SmsMessage, Task, CalendarEvent
from app.tools.mcp_tools import MCPTools

tools = MCPTools()

# ── keyword hints that flag an SMS as appointment-related ──────────────────
_APPT_KEYWORDS = (
    "appointment",
    "appt",
    "scheduled",
    "reminder",
    "confirm",
    "dr.",
    "dr ",
    "doctor",
    "clinic",
    "hospital",
    "dentist",
    "dental",
    "optician",
    "pharmacy",
    "physio",
    "therapist",
    "surgeon",
    "specialist",
    "checkup",
    "check-up",
    "follow-up",
    "followup",
    "consultation",
    "scan",
    "x-ray",
    "blood test",
    "lab",
    "vaccine",
    "vaccination",
    "prescription",
    "referral",
)


def _looks_like_appointment(body: str) -> bool:
    lower = body.lower()
    return any(kw in lower for kw in _APPT_KEYWORDS)


def _build_prompt(body: str, from_number: str, received_at: str) -> str:
    return f"""You are a household assistant that reads SMS messages and extracts appointment information.

Analyse this SMS and return a JSON object only — no extra text.

SMS from: {from_number}
Received: {received_at}
Message:
\"\"\"{body}\"\"\"

Return this exact JSON shape:
{{
  "is_appointment": true | false,
  "doctor_or_clinic": "string or null",
  "appointment_date": "YYYY-MM-DDTHH:MM:SS or null (use current year if not specified)",
  "appointment_end": "YYYY-MM-DDTHH:MM:SS or null (default 30 min after start if unknown)",
  "location": "string or null",
  "purpose": "brief description e.g. Annual checkup, Dental cleaning",
  "task_title": "short imperative e.g. Attend dental appointment on Tue 3 Jul",
  "task_description": "one-sentence summary for the family task list",
  "calendar_title": "short calendar title e.g. Dentist – Dr Smith",
  "needs_confirmation": true | false
}}

Rules:
- Set is_appointment to false if the SMS is a marketing message, OTP, or clearly not medical.
- If the date/time cannot be determined leave appointment_date null.
- Never include PII beyond what is already in the SMS.
"""


async def _call_gemini(prompt: str) -> Optional[Dict[str, Any]]:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        llm = ChatGoogleGenerativeAI(
            model=settings.google_model,
            google_api_key=settings.google_api_key,
            temperature=0,
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        raw = raw[start:end] if start >= 0 and end > start else raw
        return json.loads(raw)
    except Exception as exc:
        logger.error("sms.gemini.failed", error=str(exc), exc_info=True)
        return None


async def process_single_sms(sms: SmsMessage, db: AsyncSession) -> None:
    """Extract appointment info and persist tasks / calendar events."""

    received_at = (sms.created_at or datetime.now(timezone.utc)).isoformat()
    prompt = _build_prompt(sms.body, sms.from_number, received_at)
    data = await _call_gemini(prompt)

    if data is None:
        # Gemini unavailable — fall back to keyword match only
        sms.is_appointment = _looks_like_appointment(sms.body)
        sms.processed = True
        sms.processed_at = datetime.now(timezone.utc)
        db.add(sms)
        await db.commit()
        return

    is_appointment: bool = bool(data.get("is_appointment", False))
    sms.is_appointment = is_appointment
    sms.extracted_data = data

    tasks_created: List[str] = []
    events_created: List[str] = []

    if is_appointment:
        # ── Task ──────────────────────────────────────────────────────────
        task_payload = {
            "title": data.get("task_title") or f"Appointment SMS from {sms.from_number}",
            "description": data.get("task_description") or sms.body[:300],
            "priority": "high",
            "extra_data": {
                "source": "sms",
                "sms_id": sms.id,
                "from_number": sms.from_number,
            },
        }
        if data.get("appointment_date"):
            task_payload["due_date"] = data["appointment_date"]

        try:
            result = await tools.create_task(task_payload)
            tasks_created.append(result.get("task_id", ""))
            logger.info("sms.task.created", task_id=result.get("task_id"), sms_id=sms.id)
        except Exception as exc:
            logger.error("sms.task.create.failed", error=str(exc), sms_id=sms.id)

        # ── Calendar event ────────────────────────────────────────────────
        if data.get("appointment_date"):
            try:
                start_dt = datetime.fromisoformat(data["appointment_date"])
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)

                end_str = data.get("appointment_end")
                if end_str:
                    end_dt = datetime.fromisoformat(end_str)
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                else:
                    end_dt = start_dt + timedelta(minutes=30)

                event_payload = {
                    "title": data.get("calendar_title") or task_payload["title"],
                    "description": data.get("purpose") or sms.body[:300],
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                    "location": data.get("location"),
                    "extra_data": {
                        "source": "sms",
                        "sms_id": sms.id,
                        "from_number": sms.from_number,
                        "color": "red",
                    },
                }
                result = await tools.create_event(event_payload)
                events_created.append(result.get("event_id", ""))
                logger.info("sms.event.created", event_id=result.get("event_id"), sms_id=sms.id)
            except Exception as exc:
                logger.error("sms.event.create.failed", error=str(exc), sms_id=sms.id)

    sms.tasks_created = tasks_created
    sms.events_created = events_created
    sms.processed = True
    sms.processed_at = datetime.now(timezone.utc)
    db.add(sms)
    await db.commit()
    logger.info(
        "sms.processed",
        sms_id=sms.id,
        is_appointment=is_appointment,
        tasks=len(tasks_created),
        events=len(events_created),
    )


async def process_pending_sms(db: AsyncSession) -> None:
    """Process all unprocessed SMS messages (called at startup or on demand)."""
    result = await db.execute(
        select(SmsMessage).where(SmsMessage.processed.is_(False))
    )
    messages = result.scalars().all()
    if not messages:
        return
    logger.info("sms.batch.start", count=len(messages))
    for sms in messages:
        try:
            await process_single_sms(sms, db)
        except Exception as exc:
            logger.error("sms.batch.item.failed", sms_id=sms.id, error=str(exc))
