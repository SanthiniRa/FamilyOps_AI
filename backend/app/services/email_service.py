from imap_tools import MailBox

class EmailProcessor:
def __init__(self, email_user: str, email_password: str):
    self.email_user = email_user
    self.email_password = email_password

# ✅ FIXED: simple generator (NOT async)
def fetch_emails(self):
    with MailBox("imap.gmail.com").login(self.email_user, self.email_password) as mailbox:
        for msg in mailbox.fetch():
            yield {
                "message_id": msg.message_id,
                "subject": msg.subject or "",
                "sender": msg.from_,
                "body_text": msg.text or "",
                "received_at": msg.date,
            }

import json
import google.generativeai as genai

# configure once (put in __init__ ideally)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

class EmailProcessor:

    async def extract_action_items(self, email_body: str):

        prompt = f"""
You are an AI assistant that extracts actionable tasks from emails.

Return ONLY valid JSON in this format:
{{
  "actions": [
    {{
      "text": "task description",
      "due_date": null
    }}
  ],
  "is_payment": true/false
}}

Email:
{email_body}
"""

        model = genai.GenerativeModel("gemini-1.5-flash")

        response = model.generate_content(prompt)

        try:
            data = json.loads(response.text)
        except Exception:
            # fallback safety parsing
            return {
                "actions": [],
                "is_payment": self.detect_payment_emails("", email_body)
            }

        return data

# ✅ keyword detection
def detect_payment_emails(self, subject: str, body: str) -> bool:
    keywords = [
        "invoice", "bill", "payment due",
        "school", "hospital", "statement", "fee"
    ]
    text = (subject + " " + body).lower()
    return any(k in text for k in keywords)