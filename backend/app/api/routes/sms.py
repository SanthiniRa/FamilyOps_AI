"""
Twilio SMS Webhook
Receives inbound SMS via Twilio, stores them, runs the appointment
processor, and replies with a short confirmation.

Twilio POST body fields used:
  MessageSid, From, To, Body
"""

from __future__ import annotations

import hmac
import hashlib
import base64
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.db.database import get_db
from app.db.models import SmsMessage
from app.workers.sms_processor import process_single_sms, _looks_like_appointment

router = APIRouter(prefix="/sms", tags=["sms"])


# ── Twilio signature validation ────────────────────────────────────────────

def _twilio_signature_valid(request: Request, body: bytes, auth_token: str) -> bool:
    """
    Validate the X-Twilio-Signature header so only real Twilio requests
    are accepted.  Returns True when the token is empty (dev mode).
    """
    if not auth_token:
        return True

    url = str(request.url)
    signature = request.headers.get("X-Twilio-Signature", "")

    mac = hmac.new(auth_token.encode("utf-8"), url.encode("utf-8"), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode("utf-8")
    return hmac.compare_digest(expected, signature)


# ── Twilio reply helper ────────────────────────────────────────────────────

def _twiml_response(message: str) -> Response:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{message}</Message>
</Response>"""
    return Response(content=xml, media_type="application/xml")


# ── Webhook endpoint ───────────────────────────────────────────────────────

@router.post("/webhook")
async def twilio_sms_webhook(
    request: Request,
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(""),
    Body: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Twilio posts here whenever someone sends an SMS to your Twilio number.
    Point the Twilio console webhook URL to:
      https://<your-replit-domain>/api/v1/sms/webhook
    """
    raw_body = await request.body()
    if not _twilio_signature_valid(request, raw_body, settings.twilio_auth_token):
        logger.warning("sms.webhook.invalid_signature", from_number=From)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    # De-duplicate: ignore if this Twilio SID was already stored
    existing = await db.execute(
        select(SmsMessage).where(SmsMessage.twilio_sid == MessageSid)
    )
    if existing.scalar_one_or_none():
        logger.info("sms.webhook.duplicate", sid=MessageSid)
        return _twiml_response("")

    logger.info("sms.webhook.received", from_number=From, sid=MessageSid)

    sms = SmsMessage(
        from_number=From,
        to_number=To,
        body=Body,
        twilio_sid=MessageSid,
        created_at=datetime.now(timezone.utc),
    )
    db.add(sms)
    await db.flush()

    # Run AI processor inline (fast enough for a webhook response window)
    try:
        await process_single_sms(sms, db)
    except Exception as exc:
        logger.error("sms.webhook.processing_error", error=str(exc), exc_info=True)

    # Build a friendly reply
    if sms.is_appointment:
        data = sms.extracted_data or {}
        who = data.get("doctor_or_clinic") or "your appointment"
        when = data.get("appointment_date")
        if when:
            try:
                dt = datetime.fromisoformat(when)
                when_str = dt.strftime("%-d %b at %-I:%M %p")
            except Exception:
                when_str = when
        else:
            when_str = "the date/time mentioned"
        reply = (
            f"Got it! I've added a task and calendar event for {who} on {when_str}. "
            "Check your FamilyOps dashboard."
        )
    else:
        reply = "SMS received. No appointment found — message saved to FamilyOps."

    return _twiml_response(reply)


# ── List stored SMS ───────────────────────────────────────────────────────

@router.get("/messages")
async def list_sms_messages(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    appointments_only: bool = False,
):
    """Return stored SMS messages (most recent first)."""
    q = select(SmsMessage).order_by(SmsMessage.created_at.desc()).limit(limit)
    if appointments_only:
        q = q.where(SmsMessage.is_appointment.is_(True))
    result = await db.execute(q)
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "from_number": m.from_number,
            "body": m.body,
            "is_appointment": m.is_appointment,
            "processed": m.processed,
            "extracted_data": m.extracted_data,
            "tasks_created": m.tasks_created,
            "events_created": m.events_created,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


# ── Manual test endpoint ──────────────────────────────────────────────────

@router.post("/test")
async def test_sms_processing(
    body: str,
    from_number: str = "+10000000000",
    db: AsyncSession = Depends(get_db),
):
    """
    Dev-only: inject a fake SMS and run it through the processor.
    Useful for testing without a Twilio account.
    """
    sms = SmsMessage(
        from_number=from_number,
        to_number=settings.twilio_phone_number or "test",
        body=body,
        twilio_sid=f"TEST-{datetime.now(timezone.utc).timestamp()}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(sms)
    await db.flush()
    await process_single_sms(sms, db)
    return {
        "sms_id": sms.id,
        "is_appointment": sms.is_appointment,
        "extracted": sms.extracted_data,
        "tasks_created": sms.tasks_created,
        "events_created": sms.events_created,
    }
