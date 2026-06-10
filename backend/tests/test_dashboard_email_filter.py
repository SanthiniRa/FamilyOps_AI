import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.routes import dashboard as dashboard_routes  # noqa: E402


def _email(**kwargs):
    defaults = {
        "id": "email-1",
        "subject": "",
        "sender": "",
        "body_text": "",
        "summary": "",
        "category": None,
        "action_items": [],
        "extra_data": {},
        "received_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_matched_email_keywords_uses_subject_body_and_summary(monkeypatch):
    monkeypatch.setattr(
        dashboard_routes.settings,
        "important_email_keywords",
        "urgent,invoice,permission slip",
    )

    email = _email(
        subject="Urgent: permission slip due today",
        body_text="Please review the school form.",
    )

    assert dashboard_routes._matched_email_keywords(email) == ["urgent", "permission slip"]


def test_select_important_emails_filters_and_ranks(monkeypatch):
    monkeypatch.setattr(
        dashboard_routes.settings,
        "important_email_keywords",
        "urgent,invoice,permission slip",
    )

    important_keyword_email = _email(
        id="keyword",
        subject="Urgent invoice due",
        sender="billing@example.com",
        summary="Payment reminder",
    )
    important_action_email = _email(
        id="action",
        subject="School update",
        sender="teacher@example.com",
        category="task",
        action_items=[{"title": "Sign form"}],
    )
    ignored_email = _email(
        id="ignored",
        subject="Weekly newsletter",
        sender="news@example.com",
    )

    important = dashboard_routes._select_important_emails(
        [ignored_email, important_action_email, important_keyword_email]
    )

    assert [item["id"] for item in important] == ["keyword", "action"]
    assert important[0]["matched_keywords"] == ["urgent", "invoice"]
    assert important[1]["reason"] == "1 action item(s) extracted"


def test_email_importance_accepts_trusted_sender_domain(monkeypatch):
    monkeypatch.setattr(
        dashboard_routes.settings,
        "important_email_sender_domains",
        "school.edu,billing.example.com",
    )

    email = _email(
        subject="Weekly newsletter",
        sender="School Office <office@school.edu>",
        body_text="Nothing pressing here",
    )

    importance = dashboard_routes._email_importance(email)

    assert importance.is_important
    assert importance.matched_domains == ["school.edu"]
    assert importance.reason == "Trusted domain: school.edu"
