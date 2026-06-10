import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.privacy import redact_pii, redact_pii_in_obj


def test_redact_pii_replaces_common_sensitive_values():
    text = "Email me at parent@example.com, call 555-123-4567, or visit 123 Main Street."

    redacted = redact_pii(text)

    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_ADDRESS]" in redacted


def test_redact_pii_in_obj_recurses_through_nested_structures():
    payload = {
        "subject": "School update for parent@example.com",
        "nested": {
            "phone": "555-123-4567",
        },
        "items": ["Contact 555-123-4567", "safe text"],
    }

    redacted = redact_pii_in_obj(payload)

    assert redacted["subject"] == "School update for [REDACTED_EMAIL]"
    assert redacted["nested"]["phone"] == "[REDACTED_PHONE]"
    assert redacted["items"][0] == "Contact [REDACTED_PHONE]"
    assert redacted["items"][1] == "safe text"


def test_strict_mode_redacts_names_and_urls(monkeypatch):
    monkeypatch.setattr(settings, "enable_strict_pii_redaction", True, raising=False)

    text = "My name is John Smith. Visit https://example.com/profile."
    redacted = redact_pii(text, source="test.strict", field="body")

    assert "[REDACTED_NAME]" in redacted
    assert "[REDACTED_URL]" in redacted


def test_redaction_audit_log_writes_jsonl(monkeypatch, tmp_path):
    audit_path = tmp_path / "redactions.jsonl"
    monkeypatch.setattr(settings, "redaction_audit_log_path", str(audit_path), raising=False)

    redact_pii("Contact me at parent@example.com", source="test.audit", field="body")

    assert audit_path.exists()
    line = audit_path.read_text(encoding="utf-8").strip()
    assert line
    assert "parent@example.com" not in line
    assert "test.audit" in line
