import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.workers import email_ingestor as worker  # noqa: E402


class FakeResult:
    def first(self):
        return None


class FakeProcessor:
    def __init__(self, mails):
        self._mails = mails

    async def fetch_emails(self):
        for mail in self._mails:
            yield mail


def test_ingest_emails_skips_non_keyword_mail(monkeypatch):
    async def _run():
        mails = [
            {
                "message_id": "1",
                "subject": "Weekly update",
                "sender": "news@example.com",
                "body_text": "Hello family",
                "body_html": "",
                "received_at": object(),
                "attachments": [],
                "attachment_text": "",
                "attachment_count": 0,
            },
            {
                "message_id": "2",
                "subject": "Urgent invoice due",
                "sender": "billing@example.com",
                "body_text": "Please review payment",
                "body_html": "",
                "received_at": object(),
                "attachments": [{"filename": "invoice.pdf"}],
                "attachment_text": "Payment required",
                "attachment_count": 1,
            },
        ]

        db = SimpleNamespace(
            execute=AsyncMock(return_value=FakeResult()),
            add=MagicMock(),
            commit=AsyncMock(),
        )

        monkeypatch.setattr(
            worker,
            "EmailProcessor",
            lambda *args, **kwargs: FakeProcessor(mails),
        )

        await worker.ingest_emails(db, "user@example.com", "password")

        assert db.add.call_count == 1
        stored_email = db.add.call_args.args[0]
        assert stored_email.message_id == "2"
        assert stored_email.extra_data["matched_keywords"] == ["urgent", "invoice", "payment"]
        assert db.commit.await_count == 1

    asyncio.run(_run())


def test_ingest_emails_keeps_trusted_sender_domain(monkeypatch):
    async def _run():
        mails = [
            {
                "message_id": "trusted-1",
                "subject": "Weekly newsletter",
                "sender": "School Office <office@school.edu>",
                "body_text": "Nothing pressing here",
                "body_html": "",
                "received_at": object(),
                "attachments": [],
                "attachment_text": "",
                "attachment_count": 0,
            }
        ]

        db = SimpleNamespace(
            execute=AsyncMock(return_value=FakeResult()),
            add=MagicMock(),
            commit=AsyncMock(),
        )

        monkeypatch.setattr(worker.settings, "important_email_sender_domains", "school.edu")
        monkeypatch.setattr(
            worker,
            "EmailProcessor",
            lambda *args, **kwargs: FakeProcessor(mails),
        )

        await worker.ingest_emails(db, "user@example.com", "password")

        assert db.add.call_count == 1
        stored_email = db.add.call_args.args[0]
        assert stored_email.message_id == "trusted-1"
        assert stored_email.extra_data["matched_keywords"] == []
        assert stored_email.extra_data["matched_domains"] == ["school.edu"]
        assert stored_email.extra_data["importance_reason"] == "Trusted domain: school.edu"

    asyncio.run(_run())
