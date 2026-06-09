import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.email_graph import _extract_fallback_tasks


def test_school_email_fallback_creates_task():
    email = {
        "subject": "School permission slip due Friday",
        "sender": "noreply@school.edu",
        "body_text": "Please sign and return the permission slip by Friday.",
    }

    tasks = _extract_fallback_tasks(email)

    assert tasks, "Expected at least one task for an actionable school email"
    assert tasks[0]["type"] == "task"
    assert "permission slip" in tasks[0]["title"].lower() or "sign" in tasks[0]["description"].lower()


def test_school_attachment_text_creates_task():
    email = {
        "subject": "Weekly update",
        "sender": "noreply@school.edu",
        "body_text": "Please see the attached file.",
        "attachment_text": "Permission slip due Friday. Please sign and return by tomorrow.",
    }

    tasks = _extract_fallback_tasks(email)

    assert tasks, "Expected attachment text to create at least one task"
    assert tasks[0]["type"] == "task"
    assert "permission" in tasks[0]["title"].lower() or "sign" in tasks[0]["description"].lower()
