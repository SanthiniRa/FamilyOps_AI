from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import logger


EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"
)
ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.'\- ]{2,80}\s+"
    r"(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|way|boulevard|blvd|place|pl|terrace|ter)\b",
    re.I,
)
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
URL_RE = re.compile(r"\bhttps?://[^\s<>()]+|\bwww\.[^\s<>()]+", re.I)
DOB_RE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
UK_POSTCODE_RE = re.compile(
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b",
    re.I,
)
LABELLED_NAME_RE = re.compile(
    r"\b(?:my name is|name is|full name is|student is|child is|parent is|recipient is|sender is)\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
    re.I,
)
HONORIFIC_NAME_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b"
)

SENSITIVE_KEY_MARKERS = {
    "name": "[REDACTED_NAME]",
    "full_name": "[REDACTED_NAME]",
    "first_name": "[REDACTED_NAME]",
    "last_name": "[REDACTED_NAME]",
    "display_name": "[REDACTED_NAME]",
    "child_name": "[REDACTED_NAME]",
    "student_name": "[REDACTED_NAME]",
    "parent_name": "[REDACTED_NAME]",
    "email": "[REDACTED_EMAIL]",
    "sender": "[REDACTED_EMAIL]",
    "recipient": "[REDACTED_EMAIL]",
    "phone": "[REDACTED_PHONE]",
    "mobile": "[REDACTED_PHONE]",
    "address": "[REDACTED_ADDRESS]",
    "street_address": "[REDACTED_ADDRESS]",
    "dob": "[REDACTED_DOB]",
    "date_of_birth": "[REDACTED_DOB]",
    "birth_date": "[REDACTED_DOB]",
    "postcode": "[REDACTED_POSTCODE]",
    "postal_code": "[REDACTED_POSTCODE]",
}


def _luhn_check(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if len(digits) < 13:
        return False

    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _normalize_sensitive_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def _append_redaction_audit(entry: dict[str, Any]) -> None:
    audit_path = (getattr(settings, "redaction_audit_log_path", "") or "").strip()
    if audit_path:
        try:
            path = Path(audit_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except Exception as exc:
            logger.warning("privacy.redaction_audit_write_failed", error=str(exc), path=audit_path)


def _log_redaction_event(
    *,
    source: str | None,
    field: str | None,
    path: str | None,
    strict: bool,
    counts: dict[str, int],
) -> None:
    if not counts:
        return

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source or "unknown",
        "field": field or "",
        "path": path or "",
        "strict_mode": strict,
        "counts": counts,
    }
    logger.info("privacy.redaction", **entry)
    _append_redaction_audit(entry)


def _redact_text_value(
    text: str,
    *,
    source: str | None = None,
    field: str | None = None,
    path: str | None = None,
    strict: bool | None = None,
) -> str:
    if not getattr(settings, "enable_pii_redaction", True):
        return text

    strict_mode = getattr(settings, "enable_strict_pii_redaction", False) if strict is None else strict

    redacted = text
    counts: dict[str, int] = {}

    def sub(pattern: re.Pattern[str], replacement: str, label: str) -> None:
        nonlocal redacted
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            counts[label] = counts.get(label, 0) + count

    sub(EMAIL_RE, "[REDACTED_EMAIL]", "email")
    sub(SSN_RE, "[REDACTED_SSN]", "ssn")
    sub(PHONE_RE, "[REDACTED_PHONE]", "phone")
    sub(IP_RE, "[REDACTED_IP]", "ip")
    sub(ADDRESS_RE, "[REDACTED_ADDRESS]", "address")
    sub(URL_RE, "[REDACTED_URL]", "url")
    sub(DOB_RE, "[REDACTED_DOB]", "dob")
    sub(UK_POSTCODE_RE, "[REDACTED_POSTCODE]", "postcode")

    def replace_card(match: re.Match[str]) -> str:
        candidate = match.group(0)
        if _luhn_check(candidate):
            counts["card"] = counts.get("card", 0) + 1
            return "[REDACTED_CARD]"
        return candidate

    redacted = CARD_RE.sub(replace_card, redacted)

    if strict_mode:
        def replace_name(match: re.Match[str]) -> str:
            return "[REDACTED_NAME]"

        redacted, name_count = LABELLED_NAME_RE.subn(replace_name, redacted)
        if name_count:
            counts["name"] = counts.get("name", 0) + name_count

        redacted, honorific_count = HONORIFIC_NAME_RE.subn("[REDACTED_NAME]", redacted)
        if honorific_count:
            counts["name"] = counts.get("name", 0) + honorific_count

    _log_redaction_event(
        source=source,
        field=field,
        path=path,
        strict=strict_mode,
        counts=counts,
    )
    return redacted


def redact_pii(text: Any, *, source: str | None = None, field: str | None = None, path: str | None = None) -> Any:
    if not isinstance(text, str):
        return text

    return _redact_text_value(text, source=source, field=field, path=path)


def redact_pii_in_obj(value: Any, *, source: str | None = None, path: str = "") -> Any:
    if not getattr(settings, "enable_pii_redaction", True):
        return value

    if isinstance(value, str):
        return redact_pii(value, source=source, path=path)

    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_name = str(key)
            normalized_key = _normalize_sensitive_key(key_name)
            next_path = f"{path}.{key_name}" if path else key_name
            if getattr(settings, "enable_strict_pii_redaction", False) and normalized_key in SENSITIVE_KEY_MARKERS:
                marker = SENSITIVE_KEY_MARKERS[normalized_key]
                original = redact_pii(item, source=source, field=key_name, path=next_path)
                if original != item:
                    redacted[key] = marker
                    _log_redaction_event(
                        source=source,
                        field=key_name,
                        path=next_path,
                        strict=True,
                        counts={normalized_key: 1},
                    )
                    continue
                redacted[key] = marker
                _log_redaction_event(
                    source=source,
                    field=key_name,
                    path=next_path,
                    strict=True,
                    counts={normalized_key: 1},
                )
                continue
            redacted[key] = redact_pii_in_obj(item, source=source, path=next_path)
        return redacted

    if isinstance(value, tuple):
        return tuple(redact_pii_in_obj(item, source=source, path=f"{path}[{idx}]") for idx, item in enumerate(value))

    if isinstance(value, list):
        return [redact_pii_in_obj(item, source=source, path=f"{path}[{idx}]") for idx, item in enumerate(value)]

    if isinstance(value, set):
        return {redact_pii_in_obj(item, source=source, path=f"{path}[]") for item in value}

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_pii_in_obj(item, source=source, path=f"{path}[{idx}]") for idx, item in enumerate(value)]

    return value
