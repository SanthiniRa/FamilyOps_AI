from imap_tools import MailBox
import os
import json
import google.generativeai as genai


class EmailProcessor:

    def __init__(self, email_user: str, email_password: str):
        self.email_user = email_user
        self.email_password = email_password

        genai.configure(
            api_key=os.getenv("GOOGLE_API_KEY")
        )

    def fetch_emails(self):
        with MailBox("imap.gmail.com").login(
            self.email_user,
            self.email_password
        ) as mailbox:

            for msg in mailbox.fetch():

                yield {
                    "message_id": msg.message_id,
                    "subject": msg.subject or "",
                    "sender": msg.from_,
                    "body_text": msg.text or "",
                    "received_at": msg.date,
                }

    async def extract_action_items(self, email_body: str):

        prompt = f"""
        You are an email extraction system.

        Return ONLY valid JSON.

        {{
          "actions": [],
          "calendar_events": [],
          "is_payment": false
        }}

        RULES:
        - If email contains ANY date, create a calendar_event.
        - If only date exists:
          assume 09:00 AM.
        - If no end time:
          assume +1 hour.

        EMAIL:
        {email_body}
        """

        model = genai.GenerativeModel(
            "gemini-1.5-flash"
        )

        response = model.generate_content(prompt)

        print("GEMINI RESPONSE:")
        print(response.text)

        try:
            raw = response.text.strip()

            if raw.startswith("```"):
                raw = raw.replace("```json", "")
                raw = raw.replace("```", "")
                raw = raw.strip()

            return json.loads(raw)

        except Exception as e:
            print("JSON PARSE ERROR:", e)

            return {
                "actions": [],
                "calendar_events": [],
                "is_payment": self.detect_payment_emails(
                    "",
                    email_body
                )
            }

    def detect_payment_emails(
        self,
        subject: str,
        body: str
    ) -> bool:

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

        return any(
            keyword in text
            for keyword in keywords
        )