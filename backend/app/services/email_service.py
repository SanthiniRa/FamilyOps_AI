import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from imap_tools import MailBox, AND
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.observability.langfuse_client import start_ai_trace, end_ai_generation
from app.core.prompt_versioning import prompt_metadata
from app.services.ingest_service import (
    _extract_text_from_docx,
    _extract_text_from_pdf,
    _extract_text_from_txt,
    _extract_text_via_ocr,
)
from app.services.openai_utils import (
    is_openai_model_not_found_error,
    openai_chat_model_candidates,
)


class EmailProcessor:

    def __init__(
        self,
        email_user: str,
        email_password: str,
        imap_host: str | None = None,
        imap_port: int | None = None,
    ):
        self.email_user = email_user
        self.email_password = email_password
        self.imap_host = imap_host or settings.email_imap_host or "imap.gmail.com"
        self.imap_port = imap_port or settings.email_imap_port

        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY"),
            temperature=0,
        )
        self.model_candidates = openai_chat_model_candidates()

    def _build_llm(self, model_name: str) -> ChatOpenAI:
        return ChatOpenAI(
            model=model_name,
            api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY"),
            temperature=0,
        )

    def _should_process_attachment(self, attachment: Any) -> bool:
        content_disposition = str(getattr(attachment, "content_disposition", "") or "").lower()
        filename = str(getattr(attachment, "filename", "") or "").strip()
        content_type = str(getattr(attachment, "content_type", "") or "").lower()

        if filename:
            return True

        if content_disposition == "attachment":
            return True

        return content_type not in {"text/plain", "text/html", "message/rfc822", ""}

    def _attachment_suffix(self, attachment: Any) -> str:
        filename = str(getattr(attachment, "filename", "") or "").strip()
        suffix = Path(filename).suffix.lower()
        if suffix:
            return suffix

        content_type = str(getattr(attachment, "content_type", "") or "").lower()
        mapping = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/msword": ".doc",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "text/csv": ".csv",
            "text/html": ".html",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/tiff": ".tiff",
            "image/bmp": ".bmp",
        }
        return mapping.get(content_type, "")

    async def _extract_attachment_text(self, attachment: Any) -> Dict[str, Any]:
        filename = str(getattr(attachment, "filename", "") or "").strip()
        content_type = str(getattr(attachment, "content_type", "") or "").strip()
        content_disposition = str(getattr(attachment, "content_disposition", "") or "").strip()
        payload = getattr(attachment, "payload", b"") or b""

        record: Dict[str, Any] = {
            "filename": filename,
            "content_type": content_type,
            "content_disposition": content_disposition,
            "size": len(payload),
            "text": "",
        }

        if not payload:
            return record

        suffix = self._attachment_suffix(attachment)
        lowered_type = content_type.lower()

        if lowered_type.startswith("text/") or suffix in {".txt", ".md", ".csv", ".json", ".xml", ".html", ".ics", ".eml"}:
            try:
                text = payload.decode("utf-8", errors="ignore")
            except Exception:
                text = payload.decode(errors="ignore")
            record["text"] = text.strip()
            return record

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin") as tmp:
                tmp.write(payload)
                temp_file = Path(tmp.name)

            if suffix == ".pdf" or lowered_type == "application/pdf":
                pages = await _extract_text_from_pdf(temp_file)
                text = "\n".join(page.get("text", "") for page in pages)
            elif suffix == ".docx" or lowered_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                pages = await _extract_text_from_docx(temp_file)
                text = "\n".join(page.get("text", "") for page in pages)
            elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"} or lowered_type.startswith("image/"):
                pages = await _extract_text_via_ocr(temp_file)
                text = "\n".join(page.get("text", "") for page in pages)
            elif suffix == ".txt":
                pages = await _extract_text_from_txt(temp_file)
                text = "\n".join(page.get("text", "") for page in pages)
            else:
                text = payload.decode("utf-8", errors="ignore")

            record["text"] = text.strip()
            return record
        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    # ============================================================
    # FETCH EMAILS (IMAP)
    # ============================================================
    async def fetch_emails(self):

        today = datetime.now(timezone.utc).date()

        with MailBox(self.imap_host, port=self.imap_port).login(
            self.email_user,
            self.email_password
        ) as mailbox:

            for msg in mailbox.fetch(
                AND(date_gte=today),
                reverse=True
            ):

                msg_date = msg.date.astimezone(timezone.utc).date()

                if msg_date != today:
                    continue

                attachments: List[Dict[str, Any]] = []
                attachment_texts: List[str] = []

                for attachment in getattr(msg, "attachments", []) or []:
                    if not self._should_process_attachment(attachment):
                        continue

                    record = await self._extract_attachment_text(attachment)
                    attachments.append({
                        key: value
                        for key, value in record.items()
                        if key != "text"
                    })

                    text = (record.get("text") or "").strip()
                    if text:
                        attachment_texts.append(
                            f"Attachment: {record.get('filename') or 'unnamed'}\n{text}"
                        )

                attachment_text = "\n\n".join(attachment_texts)
                if attachment_text:
                    attachment_text = attachment_text[:12000]

                yield {
                    "message_id": str(msg.uid),
                    "subject": msg.subject or "",
                    "sender": msg.from_ or "",
                    "body_text": msg.text or "",
                    "body_html": msg.html or "",
                    "received_at": msg.date,
                    "attachments": attachments,
                    "attachment_text": attachment_text,
                    "attachment_count": len(attachments),
                }
    # ============================================================
    # OPENAI EXTRACTION (FIXED + STRICT JSON)
    # ============================================================
    async def extract_action_items(self, email_body: str, attachment_text: str = ""):
        print("inside extract_action_items")
        trace = start_ai_trace(
            "email.action_items",
            input={"email_body": email_body, "attachment_text": attachment_text},
            metadata={
                "model": settings.openai_model,
                **prompt_metadata("email.action_items"),
            },
        )
        prompt = f"""
You are an email intelligence system.

Return ONLY valid JSON (no markdown, no backticks).

Schema:
{{
  "actions": [
    {{
      "type": "task",
      "title": "string",
      "description": "string"
    }}
  ],
  "calendar_events": [
    {{
      "title": "string",
      "description": "string",
      "start_time": "ISO-8601 datetime",
      "end_time": "ISO-8601 datetime",
      "location": "string",
      "all_day": false
    }}
  ],
  "is_payment": false
}}

RULES:
- If email contains ANY date → create calendar_event
- If time missing → assume 09:00–10:00
- Always return valid ISO datetime
- School-related emails should produce task items when they ask for a form, RSVP, permission slip, supply, pickup, or deadline action.
- If no events → return empty arrays

EMAIL:
{email_body}

ATTACHMENTS:
{attachment_text or "None"}
"""

        response = None
        last_error = None
        for model_name in self.model_candidates:
            try:
                if model_name != getattr(self.llm, "model_name", None):
                    self.llm = self._build_llm(model_name)
                print(f"Calling OpenAI ({model_name})...")
                response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                end_ai_generation(
                    trace,
                    name="email.action_items",
                    model=model_name,
                    input={"email_body": email_body, "attachment_text": attachment_text},
                    output=response.content,
                    metadata={
                        "model": model_name,
                        **prompt_metadata("email.action_items"),
                    },
                )
                print("OpenAI returned")
                break
            except Exception as e:
                last_error = e
                print("OpenAI error:", repr(e))
                if not is_openai_model_not_found_error(e):
                    end_ai_generation(
                        trace,
                        name="email.action_items",
                        model=model_name,
                        input={"email_body": email_body, "attachment_text": attachment_text},
                        output=None,
                        metadata={
                            "model": model_name,
                            **prompt_metadata("email.action_items"),
                        },
                        level="ERROR",
                        status_message=str(e),
                    )
                    raise

        if response is None:
            assert last_error is not None
            end_ai_generation(
                trace,
                name="email.action_items",
                model=self.model_candidates[0] if self.model_candidates else settings.openai_model,
                input={"email_body": email_body, "attachment_text": attachment_text},
                output=None,
                metadata={
                    "model": self.model_candidates[0] if self.model_candidates else settings.openai_model,
                    **prompt_metadata("email.action_items"),
                },
                level="ERROR",
                status_message=str(last_error),
            )
            raise last_error

        raw = response.content.strip()

        print("OPENAI RESPONSE:")
        print(raw)

        # ========================================================
        # CLEAN JSON (VERY IMPORTANT)
        # ========================================================
        try:
            # remove markdown if exists
            raw = re.sub(r"```json|```", "", raw).strip()

            # extract first JSON block if extra text exists
            start = raw.find("{")
            end = raw.rfind("}") + 1
            raw = raw[start:end]

            return json.loads(raw)

        except Exception as e:
            print("JSON PARSE ERROR:", e)

            return {
                "actions": [],
                "calendar_events": [],
                "is_payment": self.detect_payment_emails("", email_body)
            }

    # ============================================================
    # PAYMENT DETECTION
    # ============================================================
    def detect_payment_emails(self, subject: str, body: str) -> bool:

        keywords = [
            "invoice",
            "bill",
            "payment due",
            "hospital",
            "statement",
            "fee"
        ]

        text = (subject + " " + body).lower()

        return any(keyword in text for keyword in keywords)
