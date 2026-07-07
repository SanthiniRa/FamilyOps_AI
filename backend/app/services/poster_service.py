from __future__ import annotations

import json
from typing import Any, Dict

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import logger
from app.observability.langfuse_client import get_langfuse, start_ai_trace, end_ai_generation


langfuse = get_langfuse()


class PosterVisionService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key or None)

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"raw": raw}

    def _fallback(self, ocr_text: str, filename: str | None = None) -> Dict[str, Any]:
        lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
        title = lines[0] if lines else (filename or "Poster reminder")
        summary = " ".join(lines[:3])[:240] if lines else "Poster text could not be fully read"
        return {
            "title": title[:120],
            "description": ocr_text[:500],
            "event_all_day_date": None,
            "event_start_iso": None,
            "event_end_iso": None,
            "task_title": title[:120],
            "task_description": summary,
            "task_due_iso": None,
            "location": None,
            "summary": summary,
            "raw_text": ocr_text,
        }

    async def analyze_poster_text(self, ocr_text: str, filename: str | None = None) -> Dict[str, Any]:
        text = (ocr_text or "").strip()
        if not text:
            return self._fallback("", filename)

        if not settings.openai_api_key:
            return self._fallback(text, filename)

        prompt = f"""You read OCR text from a flyer or poster and extract a family reminder.

Return JSON only with these keys:
- title: concise event title
- description: one or two sentence summary
- location: location or null
- event_all_day_date: YYYY-MM-DD when a date is present but no time, else null
- event_start_iso: full ISO datetime if the poster includes a time, else null
- event_end_iso: full ISO datetime if the poster includes a time, else null
- task_title: short reminder title
- task_description: plain-language reminder for the family
- task_due_iso: ISO datetime if there is a specific date/time to remind on, else null
- summary: short human readable summary

Rules:
- If the poster only shows a date and not a time, set event_all_day_date and leave event_start_iso/event_end_iso null.
- If the poster shows both date and time, fill event_start_iso and event_end_iso.
- If there is no actionable date, leave the date/time fields null and still summarize the poster.
- Prefer concise titles for a household task list.

Filename: {filename or "unknown"}
OCR text:
\"\"\"{text}\"\"\"
"""

        trace = start_ai_trace(
            "vision.poster_text",
            input={"filename": filename, "ocr_text": text},
            metadata={"model": settings.openai_model},
        )

        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            end_ai_generation(
                trace,
                name="vision.poster_text",
                model=settings.openai_model,
                input={"filename": filename, "ocr_text": text},
                output=None,
                metadata={"feature": "analyze_poster_text"},
                level="ERROR",
                status_message=str(exc),
            )
            logger.error("poster.ai.failed", error=str(exc), exc_info=True)
            return self._fallback(text, filename)

        raw = response.choices[0].message.content or "{}"
        payload = self._parse_json(raw)
        normalized = {
            "title": payload.get("title") or (filename or "Poster reminder"),
            "description": payload.get("description") or text[:500],
            "event_all_day_date": payload.get("event_all_day_date"),
            "event_start_iso": payload.get("event_start_iso"),
            "event_end_iso": payload.get("event_end_iso"),
            "task_title": payload.get("task_title") or (filename or "Poster reminder"),
            "task_description": payload.get("task_description") or payload.get("description") or text[:240],
            "task_due_iso": payload.get("task_due_iso"),
            "location": payload.get("location"),
            "summary": payload.get("summary") or text[:240],
            "raw_text": text,
            "raw": raw,
        }

        end_ai_generation(
            trace,
            name="vision.poster_text",
            model=settings.openai_model,
            input={"filename": filename, "ocr_text": text},
            output=raw,
            usage=response.usage.model_dump() if response.usage else None,
            metadata={"feature": "analyze_poster_text"},
        )

        return normalized
