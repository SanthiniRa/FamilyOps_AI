from dataclasses import dataclass
from email.utils import parseaddr
from typing import Any, List, Mapping, Optional, Sequence

from app.core.config import settings


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def important_email_keywords(raw_keywords: Optional[str] = None) -> List[str]:
    raw = raw_keywords if raw_keywords is not None else settings.important_email_keywords or ""
    return [keyword.strip().lower() for keyword in raw.split(",") if keyword.strip()]


def important_email_senders(raw_senders: Optional[str] = None) -> List[str]:
    raw = raw_senders if raw_senders is not None else settings.important_email_senders or ""
    return [sender.strip().lower() for sender in raw.split(",") if sender.strip()]


def important_email_sender_domains(raw_domains: Optional[str] = None) -> List[str]:
    raw = raw_domains if raw_domains is not None else settings.important_email_sender_domains or ""
    return [domain.strip().lower().lstrip("@") for domain in raw.split(",") if domain.strip()]


def extract_sender_email(sender: Any) -> str:
    _, address = parseaddr(str(sender or ""))
    return address.strip().lower()


def extract_sender_domain(sender: Any) -> str:
    address = extract_sender_email(sender)
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[-1]


def build_email_search_text(
    *,
    subject: Any = "",
    sender: Any = "",
    body_text: Any = "",
    body_html: Any = "",
    attachment_text: Any = "",
    summary: Any = "",
    action_items: Optional[Sequence[Any]] = None,
) -> str:
    action_text: List[str] = []
    for item in action_items or []:
        if isinstance(item, Mapping):
            action_text.extend(
                str(item.get(field, ""))
                for field in ("title", "description")
            )

    parts = [
        _normalize_text(subject),
        _normalize_text(sender),
        _normalize_text(body_text),
        _normalize_text(body_html),
        _normalize_text(attachment_text),
        _normalize_text(summary),
        _normalize_text(" ".join(action_text)),
    ]
    return " ".join(part for part in parts if part)


def matched_important_keywords(
    *,
    subject: Any = "",
    sender: Any = "",
    body_text: Any = "",
    body_html: Any = "",
    attachment_text: Any = "",
    summary: Any = "",
    action_items: Optional[Sequence[Any]] = None,
    raw_keywords: Optional[str] = None,
) -> List[str]:
    text = build_email_search_text(
        subject=subject,
        sender=sender,
        body_text=body_text,
        body_html=body_html,
        attachment_text=attachment_text,
        summary=summary,
        action_items=action_items,
    )
    return [keyword for keyword in important_email_keywords(raw_keywords) if keyword in text]


@dataclass(frozen=True)
class EmailImportance:
    is_important: bool
    score: int
    matched_keywords: List[str]
    subject_keywords: List[str]
    matched_senders: List[str]
    matched_domains: List[str]
    reason: str


def evaluate_email_importance(
    *,
    subject: Any = "",
    sender: Any = "",
    body_text: Any = "",
    body_html: Any = "",
    attachment_text: Any = "",
    summary: Any = "",
    action_items: Optional[Sequence[Any]] = None,
    category: Optional[str] = None,
    raw_keywords: Optional[str] = None,
    raw_senders: Optional[str] = None,
    raw_domains: Optional[str] = None,
) -> EmailImportance:
    keywords = important_email_keywords(raw_keywords)
    senders = important_email_senders(raw_senders)
    domains = important_email_sender_domains(raw_domains)

    subject_text = _normalize_text(subject)
    search_text = build_email_search_text(
        subject=subject,
        sender=sender,
        body_text=body_text,
        body_html=body_html,
        attachment_text=attachment_text,
        summary=summary,
        action_items=action_items,
    )

    matched_keywords = [keyword for keyword in keywords if keyword in search_text]
    subject_keywords = [keyword for keyword in keywords if keyword in subject_text]

    sender_email = extract_sender_email(sender)
    sender_domain = extract_sender_domain(sender)
    matched_senders = [allowlisted for allowlisted in senders if sender_email == allowlisted]
    matched_domains = [allowlisted for allowlisted in domains if sender_domain == allowlisted]

    action_count = len(action_items or [])
    score = (len(matched_keywords) * 10) + (len(subject_keywords) * 5) + (action_count * 3)

    if matched_senders:
        score += 12
    if matched_domains:
        score += 8
    if category in {"task", "calendar"}:
        score += 5

    is_important = bool(
        matched_keywords
        or matched_senders
        or matched_domains
        or action_count > 0
        or category in {"task", "calendar"}
    )

    if matched_senders:
        reason = f"Trusted sender: {matched_senders[0]}"
    elif matched_domains:
        reason = f"Trusted domain: {matched_domains[0]}"
    elif subject_keywords:
        reason = f"Subject matched: {', '.join(subject_keywords[:3])}"
    elif matched_keywords:
        reason = f"Matched keywords: {', '.join(matched_keywords[:3])}"
    elif action_count:
        reason = f"{action_count} action item(s) extracted"
    elif category in {"task", "calendar"}:
        reason = "Actionable email"
    else:
        reason = "Not important"

    return EmailImportance(
        is_important=is_important,
        score=score,
        matched_keywords=matched_keywords,
        subject_keywords=subject_keywords,
        matched_senders=matched_senders,
        matched_domains=matched_domains,
        reason=reason,
    )
