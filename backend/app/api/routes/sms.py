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
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.db.database import get_db
from app.db.models import SmsMessage, UploadedImage
from app.services import ingest_service
from app.services.poster_service import PosterVisionService
from app.tools.mcp_tools import MCPTools
from app.workers.sms_processor import process_single_sms

router = APIRouter(prefix="/sms", tags=["sms"])
tools = MCPTools()
poster_service = PosterVisionService()


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
# Apple Shortcuts endpoint
# ─────────────────────────────────────────────────────────────────────────────

class ShortcutPayload(BaseModel):
    text: str
    source: str = "shortcut"
    sender: str = ""
    token: str = ""


@router.get("/shortcut")
async def apple_shortcut_get(
    text: str = Query(..., description="The SMS or WhatsApp message text"),
    source: str = Query("sms"),
    sender: str = Query(""),
    token: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """
    GET version — easiest to use from Apple Shortcuts.
    Just build the URL with text= as a query param. No JSON body needed.

    Shortcut action: Get Contents of URL
      URL: https://<domain>/api/v1/sms/shortcut?source=sms&sender=Doctor&text=<Clipboard>
    """
    expected = settings.sms_webhook_token
    if expected and not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    text = text.strip()
    if not text:
        return {"status": "ignored", "reason": "empty message", "summary": "No message text found"}

    logger.info("sms.shortcut.get.received", source=source, length=len(text))

    sms = SmsMessage(
        from_number=sender or source,
        to_number="shortcut",
        body=text,
        twilio_sid=f"SHORTCUT-{uuid.uuid4().hex}",
        created_at=datetime.now(timezone.utc),
        extra_data={"source": source, "sender": sender},
    )
    db.add(sms)
    await db.flush()
    await db.commit()   # commit base row NOW so it survives any AI error below

    try:
        await process_single_sms(sms, db)
    except Exception as exc:
        logger.error("sms.shortcut.get.process_error", error=str(exc), exc_info=True)
        # refresh so we can still read sms.is_appointment etc that process_single_sms may have set
        try:
            await db.refresh(sms)
        except Exception:
            pass

    if sms.is_appointment:
        data = sms.extracted_data or {}
        who = data.get("doctor_or_clinic") or sender or "appointment"
        when_raw = data.get("appointment_date")
        try:
            when_str = datetime.fromisoformat(when_raw).strftime("%a %-d %b at %-I:%M %p") if when_raw else "date in message"
        except Exception:
            when_str = when_raw or "date in message"
        summary = f"Added: {who} — {when_str}"
    else:
        tasks_count = len(sms.tasks_created or [])
        events_count = len(sms.events_created or [])
        if tasks_count or events_count:
            summary = f"Created {tasks_count} task(s), {events_count} event(s)"
        else:
            summary = "Saved to FamilyOps — no appointment detected"

    return {
        "status": "ok",
        "sms_id": sms.id,
        "is_appointment": sms.is_appointment,
        "tasks_created": len(sms.tasks_created or []),
        "events_created": len(sms.events_created or []),
        "summary": summary,
    }


@router.post("/shortcut")
async def apple_shortcut_webhook(
    payload: ShortcutPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by an Apple Shortcut.  The Shortcut sends whatever text the user
    copied or shared (SMS, WhatsApp, etc.) and FamilyOps processes it with AI.

    Setup instructions are returned from GET /api/v1/sms/shortcut-instructions.

    Accepts JSON:
      { "text": "<message body>", "source": "sms|whatsapp|other",
        "sender": "Dr Smith", "token": "<SMS_WEBHOOK_TOKEN>" }
    """
    expected = settings.sms_webhook_token
    if expected and not hmac.compare_digest(payload.token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    text = payload.text.strip()
    if not text:
        return {"status": "ignored", "reason": "empty message"}

    logger.info("sms.shortcut.received", source=payload.source, length=len(text))

    sms = SmsMessage(
        from_number = payload.sender or payload.source,
        to_number   = "shortcut",
        body        = text,
        twilio_sid  = f"SHORTCUT-{uuid.uuid4().hex}",
        created_at  = datetime.now(timezone.utc),
        extra_data  = {"source": payload.source, "sender": payload.sender},
    )
    db.add(sms)
    await db.flush()

    try:
        await process_single_sms(sms, db)
    except Exception as exc:
        logger.error("sms.shortcut.process_error", error=str(exc), exc_info=True)

    # Build a notification-friendly summary
    if sms.is_appointment:
        data     = sms.extracted_data or {}
        who      = data.get("doctor_or_clinic") or payload.sender or "appointment"
        when_raw = data.get("appointment_date")
        try:
            when_str = datetime.fromisoformat(when_raw).strftime("%a %-d %b at %-I:%M %p") if when_raw else "date in message"
        except Exception:
            when_str = when_raw or "date in message"
        summary = f"✅ Added: {who} — {when_str}"
    else:
        tasks_count  = len(sms.tasks_created or [])
        events_count = len(sms.events_created or [])
        if tasks_count or events_count:
            summary = f"✅ Created {tasks_count} task(s), {events_count} event(s)"
        else:
            summary = "💬 Saved to FamilyOps — no appointment detected"

    return {
        "status":         "ok",
        "sms_id":         sms.id,
        "is_appointment": sms.is_appointment,
        "tasks_created":  len(sms.tasks_created or []),
        "events_created": len(sms.events_created or []),
        "summary":        summary,
    }


@router.post("/shortcut-image")
async def apple_shortcut_image(
    file: UploadFile = File(...),
    source: str = Form("poster"),
    sender: str = Form(""),
    token: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by an Apple Shortcut that shares a poster, flyer, or screenshot.

    The Shortcut should send multipart/form-data with:
      - file: the shared image
      - source: poster | whatsapp | image
      - sender: optional sender label
      - token: optional shared secret
    """
    expected = settings.sms_webhook_token
    if expected and not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    suffix = Path(file.filename or "").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    ocr_text = ""
    analysis: Dict[str, Any] = {}
    img = UploadedImage(
        image_url="",
        storage_path=tmp_path,
        analysis_result={"source": source, "sender": sender},
    )

    try:
        ocr_pages = await ingest_service.extract_text_from_image(Path(tmp_path))
        ocr_text = "\n".join(
            page.get("text", "").strip()
            for page in ocr_pages
            if page.get("text", "").strip()
        ).strip()

        analysis = await poster_service.analyze_poster_text(ocr_text, filename=file.filename)

        img.analysis_result = {
            "source": source,
            "sender": sender,
            "ocr_text": ocr_text,
            "analysis": analysis,
        }
        db.add(img)
        await db.flush()
        await db.commit()
        await db.refresh(img)

        event_id = ""
        task_id = ""

        all_day_date = analysis.get("event_all_day_date")
        start_iso = analysis.get("event_start_iso")
        end_iso = analysis.get("event_end_iso")

        if all_day_date and not (start_iso and end_iso):
            try:
                day = datetime.fromisoformat(all_day_date).replace(tzinfo=timezone.utc)
                start_iso = day.isoformat()
                end_iso = (day + timedelta(days=1) - timedelta(seconds=1)).isoformat()
            except Exception:
                start_iso = None
                end_iso = None

        if start_iso and end_iso:
            try:
                event_result = await tools.create_event({
                    "title": analysis.get("title") or analysis.get("task_title") or "Poster event",
                    "description": analysis.get("description") or analysis.get("summary") or ocr_text[:300],
                    "start_time": start_iso,
                    "end_time": end_iso,
                    "location": analysis.get("location"),
                    "extra_data": {
                        "source": source,
                        "sender": sender,
                        "ocr_text": ocr_text,
                        "uploaded_image_id": img.id,
                    },
                })
                event_id = event_result.get("event_id", "")
            except Exception as exc:
                logger.error("poster.event.create.failed", error=str(exc), exc_info=True)

        task_due_iso = analysis.get("task_due_iso")
        if not task_due_iso and all_day_date:
            try:
                task_due_iso = datetime.fromisoformat(all_day_date).replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                task_due_iso = None

        if task_due_iso or analysis.get("task_title") or analysis.get("title"):
            try:
                task_result = await tools.create_task({
                    "title": analysis.get("task_title") or analysis.get("title") or "Review poster",
                    "description": analysis.get("task_description") or analysis.get("summary") or ocr_text[:300],
                    "priority": "medium",
                    "status": "pending",
                    "due_date": task_due_iso,
                    "tags": ["poster", "image", source],
                    "extra_data": {
                        "source": source,
                        "sender": sender,
                        "ocr_text": ocr_text,
                        "uploaded_image_id": img.id,
                    },
                })
                task_id = task_result.get("task_id", "")
            except Exception as exc:
                logger.error("poster.task.create.failed", error=str(exc), exc_info=True)

        img.analysis_result = {
            **(img.analysis_result or {}),
            "event_id": event_id,
            "task_id": task_id,
        }
        db.add(img)
        await db.commit()

        summary = analysis.get("summary") or "Poster image processed"
        if event_id and task_id:
            summary = f"Created event and task: {summary}"
        elif event_id:
            summary = f"Created calendar event: {summary}"
        elif task_id:
            summary = f"Created task: {summary}"

        return {
            "status": "ok",
            "image_id": img.id,
            "ocr_text": ocr_text,
            "analysis": analysis,
            "event_id": event_id,
            "task_id": task_id,
            "summary": summary,
        }
    except Exception as exc:
        logger.error("poster.image.process_failed", error=str(exc), exc_info=True)
        raise


@router.get("/shortcut-instructions")
async def shortcut_instructions(request: Request):
    """
    Returns step-by-step instructions and a direct Shortcut import link.
    Open this URL in a browser on your iPhone.
    """
    import os
    # Use the public Replit domain when available so mobile shortcuts
    # get the correct externally-reachable URL, not localhost.
    replit_domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if replit_domain:
        base = f"https://{replit_domain}"
    else:
        # fallback: try to derive from the request host header
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        scheme = request.headers.get("x-forwarded-proto", "https")
        base = f"{scheme}://{host}" if host else str(request.base_url).rstrip("/")
    endpoint = f"{base}/api/v1/sms/shortcut"
    token_note = (
        "Set SMS_WEBHOOK_TOKEN in backend/.env, then paste it into the Shortcut's token field."
        if not settings.sms_webhook_token
        else "Your SMS_WEBHOOK_TOKEN is configured — paste it into the Shortcut."
    )

    return {
        "endpoint": endpoint,
        "poster_endpoint": f"{base}/api/v1/sms/shortcut-image",
        "method":   "POST",
        "body_format": {
            "text":   "<the copied/shared message>",
            "source": "sms  or  whatsapp  or  other",
            "sender": "optional — e.g. Dr Smith or School Group",
            "token":  "<your SMS_WEBHOOK_TOKEN or leave blank>",
        },
        "token_note": token_note,
        "iphone_steps": [
            "1. Open the Shortcuts app on your iPhone.",
            "2. Tap '+' to create a new shortcut.",
            "3. Tap 'Add Action' → search 'Text' → choose 'Text' block → type a placeholder (we'll replace this).",
            "4. Add action: 'Get Clipboard' (for copied SMS) OR enable 'Share Sheet' in shortcut settings (for WhatsApp).",
            "5. Add action: search 'URL' → paste: " + endpoint,
            "6. Add action: search 'Get Contents of URL':",
            "   • Method: POST",
            "   • Headers: Content-Type = application/json",
            "   • Body: JSON — add keys: text (Shortcut Input or Clipboard), source (text: sms), sender (text: Dr), token (text: your-token)",
            "7. Add action: 'Show Notification' → Message = result of previous step → key 'summary'.",
            "8. Name the shortcut 'Send to FamilyOps'.",
            "9. For WhatsApp: tap shortcut settings (top) → enable 'Show in Share Sheet' → Types: Text.",
            "10. In WhatsApp: long-press a message → Share → choose 'Send to FamilyOps'.",
            "11. For posters/flyers: create a second shortcut with Share Sheet → Receive: Images and use /api/v1/sms/shortcut-image.",
            "12. Use Request Body = Form and add file=file, source=poster, sender=optional, token=your-token.",
        ],
    }


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
