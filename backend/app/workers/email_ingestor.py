from app.db.models import Email
from app.services.email_service import EmailProcessor
from app.core.config import settings
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
        logger.info(
            "email.ingest.found",
            extra={
                "subject": mail["subject"],
                "attachment_count": mail.get("attachment_count", 0),
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
            },
        ))

    await db.commit()
    logger.info("email.ingest.completed")
