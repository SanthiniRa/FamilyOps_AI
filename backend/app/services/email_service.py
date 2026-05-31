from imap_tools import MailBox
from app.db.models import Email
import re
from datetime import datetime

class EmailProcessor:
    def __init__(self, email_user: str, email_password: str):
        self.email_user = email_user
        self.email_password = email_password
    
    async def fetch_emails(self):
        """Connect via IMAP and fetch unprocessed emails"""
        with MailBox('imap.gmail.com').login(self.email_user, self.email_password) as mailbox:
            for msg in mailbox.fetch():
                yield {
                    'message_id': msg.message_id,
                    'subject': msg.subject,
                    'sender': msg.from_,
                    'body_text': msg.text,
                    'received_at': msg.date
                }
    
    async def extract_action_items(self, email_body: str) -> list:
        """Use LLM to extract action items"""
        prompt = f"""Extract action items from this email:
        
{email_body}

Return JSON: {{"actions": [...], "due_date": null, "assignee": null, "is_payment": bool}}"""
        # Call your LLM here
        
    async def detect_payment_emails(self, subject: str, body: str) -> bool:
        """Detect school bills, hospital invoices, etc."""
        keywords = ['invoice', 'bill', 'payment due', 'tuition', 'hospital bill', 'statement']
        return any(kw in (subject + body).lower() for kw in keywords)
