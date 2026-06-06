from imap_tools import MailBox
import os
import json
import google.generativeai as genai
import re
from datetime import datetime, timezone, timedelta

from imap_tools import MailBox, AND

class EmailProcessor:

    def __init__(self, email_user: str, email_password: str):
        self.email_user = email_user
        self.email_password = email_password

        print("FINAL IMAP USER:", repr(self.email_user))
        print("FINAL IMAP PASS:", repr(self.email_password))

        genai.configure(
            api_key=os.getenv("GOOGLE_API_KEY")
        )

    # ============================================================
    # FETCH EMAILS (IMAP)
    # ============================================================
    def fetch_emails(self):

        today = datetime.now(timezone.utc).date()

        with MailBox("imap.gmail.com").login(
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

                print(
                    f"TODAY EMAIL: {msg.subject} | "
                    f"{msg.date}"
                )

                yield {
                    "message_id": str(msg.uid),
                    "subject": msg.subject or "",
                    "sender": msg.from_ or "",
                    "body_text": msg.text or "",
                    "received_at": msg.date,
                }
    # ============================================================
    # GEMINI EXTRACTION (FIXED + STRICT JSON)
    # ============================================================
    async def extract_action_items(self, email_body: str):
        print("inside extract_action_items")
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
- If no events → return empty arrays

EMAIL:
{email_body}
"""

        model = genai.GenerativeModel("gemini-2.5-flash")
        try:
            print("Calling Gemini...")
            response = model.generate_content(prompt)
            print("Gemini returned")
        except Exception as e:
            print("Gemini error:", repr(e))
            raise

        raw = response.text.strip()

        print("GEMINI RESPONSE:")
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
            "school",
            "hospital",
            "statement",
            "fee"
        ]

        text = (subject + " " + body).lower()

        return any(keyword in text for keyword in keywords)