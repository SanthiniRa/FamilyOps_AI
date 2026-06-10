from app.db.models import Email
from app.services.email_service import EmailProcessor
from app.core.config import settings
from app.services.email_filter import evaluate_email_importance
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger


async def ingest_emails(db: AsyncSession, user, password):

    processor = EmailProcessor(
        user,
        password,
        imap_host=settings.email_imap_host,
        imap_port=settings.email_imap_port,
    )

    logger.info("email.ingest.starting")
    async for mail in processor.fetch_emails():
        importance = evaluate_email_importance(
            subject=mail.get("subject", ""),
            sender=mail.get("sender", ""),
            body_text=mail.get("body_text", ""),
            body_html=mail.get("body_html", ""),
            attachment_text=mail.get("attachment_text", ""),
            action_items=mail.get("action_items", []),
        )

        if not importance.is_important:
            logger.info(
                "email.ingest.skipped_non_keyword",
                extra={
                    "subject": mail.get("subject"),
                    "sender": mail.get("sender"),
                },
            )
            continue

        logger.info(
            "email.ingest.found",
            extra={
                "subject": mail["subject"],
                "attachment_count": mail.get("attachment_count", 0),
                "matched_keywords": importance.matched_keywords,
                "matched_senders": importance.matched_senders,
                "matched_domains": importance.matched_domains,
                "reason": importance.reason,
            },
        )
        # avoid duplicates
        exists = await db.execute(
            Email.__table__.select().where(
                Email.message_id == mail["message_id"]
            )
        )

        if exists.first():
            continue

        db.add(Email(
            message_id=mail["message_id"],
            subject=mail["subject"],
            sender=mail["sender"],
            body_text=mail["body_text"],
                body_html=mail.get("body_html") or "",
                received_at=mail["received_at"],
                extra_data={
                    "attachments": mail.get("attachments", []),
                    "attachment_text": mail.get("attachment_text", ""),
                    "attachment_count": mail.get("attachment_count", 0),
                    "matched_keywords": importance.matched_keywords,
                    "subject_keywords": importance.subject_keywords,
                    "matched_senders": importance.matched_senders,
                    "matched_domains": importance.matched_domains,
                    "importance_reason": importance.reason,
                    "importance_score": importance.score,
                },
        ))

    await db.commit()
    logger.info("email.ingest.completed")
