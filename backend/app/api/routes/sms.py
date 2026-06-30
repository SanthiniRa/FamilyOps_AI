"""
SMS Webhook — works with free Android SMS forwarder apps.

Supported apps (all free, no fees):
  1. Android SMS Gateway  (play.google.com — search "SMS Gateway Webhooks")
     POST JSON: { "from", "message", "sentStamp", "receivedStamp", "sim" }

  2. SMS Forwarder / MacroDroid / Tasker
     POST JSON or form: any shape — we auto-detect the fields below.

  3. SMS to URL / SMS Bridge
     POST form: from=<number>&text=<body>

  Optional Twilio support also kept for users who already have an account.

Security: set SMS_WEBHOOK_TOKEN in your .env.  Requests must include
  ?token=<SMS_WEBHOOK_TOKEN>  or  Authorization: Bearer <SMS_WEBHOOK_TOKEN>
  Leave blank to disable auth (safe on a private dev server).

Setup (Android SMS Gateway app):
  1. Install "SMS Gateway Webhooks" from Google Play (free).
  2. Open the app → Webhooks → Add Webhook.
  3. URL:  https://<your-replit-domain>/api/v1/sms/incoming?token=<YOUR_TOKEN>
  4. Events: Incoming SMS.  Save.  Done.
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.db.database import get_db
from app.db.models import SmsMessage
from app.workers.sms_processor import process_single_sms

router = APIRouter(prefix="/sms", tags=["sms"])


# ─────────────────────────────────────────────────────────────────────────────
# Auth helper — shared-secret token (optional)
# ─────────────────────────────────────────────────────────────────────────────

def _auth_ok(token_query: Optional[str], authorization: Optional[str]) -> bool:
    expected = settings.sms_webhook_token
    if not expected:
        return True
    candidates = []
    if token_query:
        candidates.append(token_query)
    if authorization:
        candidates.append(authorization.removeprefix("Bearer ").strip())
    return any(hmac.compare_digest(c, expected) for c in candidates)


# ─────────────────────────────────────────────────────────────────────────────
# Body normaliser — handles all the app formats in one place
# ─────────────────────────────────────────────────────────────────────────────

async def _parse_incoming(request: Request) -> Dict[str, Any]:
    """
    Try JSON first, then form-encoded.  Map whichever field names the
    sending app uses onto a standard dict:
      from_number, body, sent_at (ISO string)
    """
    content_type = request.headers.get("content-type", "")
    data: Dict[str, Any] = {}

    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
    else:
        form = await request.form()
        data = dict(form)

    # ── normalise sender ──────────────────────────────────────────────────
    from_number = (
        data.get("from")               # Android SMS Gateway
        or data.get("From")            # Twilio / MacroDroid
        or data.get("sender")
        or data.get("phone")
        or data.get("number")
        or "unknown"
    )

    # ── normalise body ────────────────────────────────────────────────────
    body = (
        data.get("message")            # Android SMS Gateway
        or data.get("Body")            # Twilio
        or data.get("body")
        or data.get("text")
        or data.get("content")
        or data.get("sms")
        or ""
    )

    # ── normalise timestamp ───────────────────────────────────────────────
    raw_ts = data.get("sentStamp") or data.get("receivedStamp") or data.get("timestamp")
    if raw_ts:
        try:
            ts_int = int(raw_ts)
            # epoch millis vs seconds
            if ts_int > 1e10:
                ts_int //= 1000
            sent_at = datetime.fromtimestamp(ts_int, tz=timezone.utc).isoformat()
        except Exception:
            sent_at = datetime.now(timezone.utc).isoformat()
    else:
        sent_at = datetime.now(timezone.utc).isoformat()

    # ── extra fields (Twilio SID, sim slot, etc.) ─────────────────────────
    twilio_sid = data.get("MessageSid") or data.get("SmsSid")
    sim_slot   = data.get("sim") or data.get("simSlot")
    to_number  = data.get("To") or data.get("to") or ""

    return {
        "from_number": str(from_number).strip(),
        "body":        str(body).strip(),
        "sent_at":     sent_at,
        "twilio_sid":  twilio_sid,
        "sim_slot":    sim_slot,
        "to_number":   to_number,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN WEBHOOK  — used by all free apps
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/incoming")
async def incoming_sms(
    request: Request,
    token: Optional[str] = Query(None, description="Shared secret token"),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Universal inbound SMS webhook.

    Point your free SMS forwarder app here:
      https://<your-replit-domain>/api/v1/sms/incoming?token=<YOUR_TOKEN>

    Supported apps (all free):
    • Android SMS Gateway Webhooks (Google Play)
    • SMS Forwarder
    • MacroDroid HTTP action
    • Tasker + HTTP Request plugin
    """
    if not _auth_ok(token, authorization):
        logger.warning("sms.incoming.auth_failed", ip=request.client.host if request.client else "?")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    parsed = await _parse_incoming(request)
    from_number = parsed["from_number"]
    body        = parsed["body"]

    if not body:
        return JSONResponse({"status": "ignored", "reason": "empty body"})

    logger.info("sms.incoming.received", from_number=from_number, length=len(body))

    # De-duplicate by Twilio SID (if present)
    if parsed["twilio_sid"]:
        dup = await db.execute(
            select(SmsMessage).where(SmsMessage.twilio_sid == parsed["twilio_sid"])
        )
        if dup.scalar_one_or_none():
            return JSONResponse({"status": "duplicate"})

    sms = SmsMessage(
        from_number = from_number,
        to_number   = parsed["to_number"],
        body        = body,
        twilio_sid  = parsed["twilio_sid"] or f"auto-{uuid.uuid4().hex[:12]}",
        created_at  = datetime.now(timezone.utc),
        extra_data  = {"sim": parsed["sim_slot"], "sent_at": parsed["sent_at"]},
    )
    db.add(sms)
    await db.flush()

    try:
        await process_single_sms(sms, db)
    except Exception as exc:
        logger.error("sms.incoming.process_error", error=str(exc), exc_info=True)

    return JSONResponse({
        "status":         "ok",
        "sms_id":         sms.id,
        "is_appointment": sms.is_appointment,
        "tasks_created":  len(sms.tasks_created or []),
        "events_created": len(sms.events_created or []),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Legacy Twilio webhook — kept for anyone already using Twilio
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook")
async def twilio_sms_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Twilio-style webhook (optional — only needed if you use Twilio)."""
    parsed = await _parse_incoming(request)
    body   = parsed["body"]
    if not body:
        return Response(content="<Response/>", media_type="application/xml")

    sms = SmsMessage(
        from_number = parsed["from_number"],
        to_number   = parsed["to_number"],
        body        = body,
        twilio_sid  = parsed["twilio_sid"] or f"twilio-{uuid.uuid4().hex[:12]}",
        created_at  = datetime.now(timezone.utc),
    )
    db.add(sms)
    await db.flush()

    try:
        await process_single_sms(sms, db)
    except Exception as exc:
        logger.error("sms.webhook.process_error", error=str(exc), exc_info=True)

    if sms.is_appointment:
        data     = sms.extracted_data or {}
        who      = data.get("doctor_or_clinic") or "your appointment"
        when_raw = data.get("appointment_date")
        try:
            when_str = datetime.fromisoformat(when_raw).strftime("%-d %b at %-I:%M %p") if when_raw else "the time mentioned"
        except Exception:
            when_str = when_raw or "the time mentioned"
        msg = f"Got it! Added task & calendar event for {who} on {when_str}. Check FamilyOps."
    else:
        msg = "SMS received. No appointment detected — saved to FamilyOps."

    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{msg}</Message></Response>'
    return Response(content=xml, media_type="application/xml")


# ─────────────────────────────────────────────────────────────────────────────
# List stored SMS messages
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/messages")
async def list_sms_messages(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    appointments_only: bool = False,
):
    """Return stored SMS (newest first)."""
    q = select(SmsMessage).order_by(SmsMessage.created_at.desc()).limit(limit)
    if appointments_only:
        q = q.where(SmsMessage.is_appointment.is_(True))
    result  = await db.execute(q)
    messages = result.scalars().all()
    return [
        {
            "id":             m.id,
            "from_number":    m.from_number,
            "body":           m.body,
            "is_appointment": m.is_appointment,
            "processed":      m.processed,
            "extracted_data": m.extracted_data,
            "tasks_created":  m.tasks_created,
            "events_created": m.events_created,
            "created_at":     m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Test endpoint — simulate an SMS without any app
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/test")
async def test_sms_processing(
    body: str = Query(..., description="SMS body to test"),
    from_number: str = Query("+10000000000"),
    db: AsyncSession = Depends(get_db),
):
    """
    Inject a fake SMS and run the AI processor.
    Try it at /api/docs without installing any app.

    Example body:
      Reminder: Your appointment with Dr. Patel is on Fri 4 Jul at 10:30 AM.
      City Dental Clinic, 42 Oak St. Reply YES to confirm.
    """
    sms = SmsMessage(
        from_number = from_number,
        to_number   = "test",
        body        = body,
        twilio_sid  = f"TEST-{uuid.uuid4().hex}",
        created_at  = datetime.now(timezone.utc),
    )
    db.add(sms)
    await db.flush()
    await process_single_sms(sms, db)
    return {
        "sms_id":         sms.id,
        "is_appointment": sms.is_appointment,
        "extracted":      sms.extracted_data,
        "tasks_created":  sms.tasks_created,
        "events_created": sms.events_created,
    }
